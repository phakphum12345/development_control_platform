from __future__ import annotations

import ctypes
import io
import os
import unittest

from tools.local_runner_agent.windows_psec_launcher import (
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION,
    WindowsPsecError,
    WindowsPsecLauncher,
    WindowsPsecProcess,
    _apply_sandbox_profile_environment,
    _environment_block,
)


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class FakeKernel32:
    def __init__(self, *, active_processes=1, exit_code=0):
        self.active_processes = active_processes
        self.exit_code = exit_code
        self.terminated = []
        self.closed = []
        self.QueryInformationJobObject = FakeFunction(self.query_job)
        self.GetExitCodeProcess = FakeFunction(self.get_exit_code)
        self.TerminateJobObject = FakeFunction(self.terminate_job)
        self.CloseHandle = FakeFunction(lambda handle: self.closed.append(handle) or 1)

    def query_job(self, job, info_class, output, size, returned):
        info = ctypes.cast(
            output, ctypes.POINTER(JOBOBJECT_BASIC_ACCOUNTING_INFORMATION)
        ).contents
        info.ActiveProcesses = self.active_processes
        return 1

    @staticmethod
    def get_exit_code(process, output):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_uint32))[0] = 0
        return 1

    def terminate_job(self, job, exit_code):
        self.terminated.append((job, exit_code))
        self.active_processes = 0
        return 1


class FakePsecDll:
    def __init__(self):
        self.closed = []
        self.CloseProcessSecurityEnvironment = FakeFunction(
            lambda handle: self.closed.append(handle) or None
        )


class WindowsPsecLauncherUnitTests(unittest.TestCase):
    def test_environment_block_is_sorted_and_double_null_terminated(self):
        block = _environment_block({"zeta": "2", "Alpha": "1"})
        values = "".join(block)
        self.assertTrue(values.startswith("Alpha=1\x00zeta=2\x00\x00"))

    def test_sandbox_profile_environment_keeps_local_app_data_in_scratch(self):
        environment = {
            "LOCALAPPDATA": r"C:\\Users\\host\\AppData\\Local",
            "USERPROFILE": r"C:\\Users\\host",
        }
        scratch = __import__("pathlib").Path(r"C:\\DCP\\scratch")
        _apply_sandbox_profile_environment(environment, scratch)
        self.assertEqual(environment["LOCALAPPDATA"], str(scratch))
        self.assertEqual(environment["USERPROFILE"], str(scratch))
        self.assertEqual(environment["TEMP"], str(scratch))
        self.assertEqual(environment["TMP"], str(scratch))

    def test_environment_block_rejects_duplicate_names_case_insensitively(self):
        with self.assertRaisesRegex(WindowsPsecError, "duplicate"):
            _environment_block({"Path": "A", "PATH": "B"})

    def test_environment_block_rejects_invalid_keys_and_values(self):
        with self.assertRaisesRegex(WindowsPsecError, "invalid"):
            _environment_block({"BAD=KEY": "value"})
        with self.assertRaisesRegex(WindowsPsecError, "invalid"):
            _environment_block({"GOOD": "bad\x00value"})

    def test_launcher_is_blocked_off_windows(self):
        if os.name == "nt":
            self.skipTest("Windows host uses the real PSEC capability probe")
        with self.assertRaisesRegex(WindowsPsecError, "only on Windows"):
            WindowsPsecLauncher()

    def test_process_poll_tracks_all_job_processes_not_only_root(self):
        kernel = FakeKernel32(active_processes=2, exit_code=0)
        process = WindowsPsecProcess(
            kernel32=kernel,
            process_handle=101,
            job_handle=202,
            psec_dll=FakePsecDll(),
            psec_handle=303,
            stdout=io.BytesIO(),
            pid=404,
            args=("python.exe", "--version"),
        )
        self.assertIsNone(process.poll())
        kernel.active_processes = 0
        self.assertEqual(process.poll(), 0)
        self.assertEqual(process.wait(timeout=0.1), 0)
        process.close()
        self.assertEqual(len(kernel.closed), 2)

    def test_process_termination_uses_job_object(self):
        kernel = FakeKernel32(active_processes=1)
        process = WindowsPsecProcess(
            kernel32=kernel,
            process_handle=101,
            job_handle=202,
            psec_dll=FakePsecDll(),
            psec_handle=303,
            stdout=io.BytesIO(),
            pid=404,
            args=("python.exe", "--version"),
        )
        process.terminate_tree()
        self.assertEqual(kernel.terminated, [(202, 1)])
        self.assertEqual(process.poll(), 0)
        process.close()
        self.assertEqual(len(kernel.closed), 2)


if __name__ == "__main__":
    unittest.main()
