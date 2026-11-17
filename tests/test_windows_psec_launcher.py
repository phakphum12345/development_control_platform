from __future__ import annotations

import ctypes
import io
import os
import unittest
from pathlib import Path

from tools.local_runner_agent.windows_psec_launcher import (
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION,
    WindowsPsecError,
    WindowsPsecLauncher,
    WindowsPsecProcess,
    _apply_sandbox_profile_environment,
    _environment_block,
    _require_app_container_token,
    _resume_after_filesystem_authorization,
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
            "LOCALAPPDATA": r"C:\Users\host\AppData\Local",
            "USERPROFILE": r"C:\Users\host",
        }
        scratch = Path(r"C:\DCP\scratch")
        _apply_sandbox_profile_environment(environment, scratch)
        self.assertEqual(environment["LOCALAPPDATA"], str(scratch))
        self.assertEqual(environment["USERPROFILE"], str(scratch))
        self.assertEqual(environment["TEMP"], str(scratch))
        self.assertEqual(environment["TMP"], str(scratch))
        block = _environment_block(environment)
        self.assertIn(f"LOCALAPPDATA={scratch}\x00", "".join(block))

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

    def test_close_can_retry_partial_handle_release_after_job_drain(self):
        class FlakyKernel(FakeKernel32):
            def __init__(self):
                super().__init__(active_processes=0)
                self.fail_job_close_once = True
                self.CloseHandle = FakeFunction(self.close_handle)

            def close_handle(self, handle):
                if handle == 202 and self.fail_job_close_once:
                    self.fail_job_close_once = False
                    return 0
                self.closed.append(handle)
                return 1

        kernel = FlakyKernel()
        psec = FakePsecDll()
        stdout = io.BytesIO()
        process = WindowsPsecProcess(
            kernel32=kernel,
            process_handle=101,
            job_handle=202,
            psec_dll=psec,
            psec_handle=303,
            stdout=stdout,
            pid=404,
            args=("python.exe", "--version"),
        )

        with self.assertRaisesRegex(WindowsPsecError, "resource close failed"):
            process.close()

        self.assertTrue(process._drained)
        self.assertIsNone(process._process_handle)
        self.assertEqual(process._job_handle, 202)
        self.assertIsNone(process._psec_handle)

        process.close()
        self.assertTrue(process._closed)
        self.assertIsNone(process._job_handle)
        self.assertEqual(kernel.closed, [101, 202])
        self.assertEqual(psec.closed, [303])

    def test_close_retains_handles_until_job_object_is_drained(self):
        class StubbornKernel(FakeKernel32):
            def terminate_job(self, job, exit_code):
                self.terminated.append((job, exit_code))
                return 1

        kernel = StubbornKernel(active_processes=1)
        psec = FakePsecDll()
        stdout = io.BytesIO()
        process = WindowsPsecProcess(
            kernel32=kernel,
            process_handle=101,
            job_handle=202,
            psec_dll=psec,
            psec_handle=303,
            stdout=stdout,
            pid=404,
            args=("python.exe", "--version"),
        )

        with self.assertRaisesRegex(WindowsPsecError, "did not drain"):
            process.close(timeout=0.01)

        self.assertFalse(process._closed)
        self.assertFalse(stdout.closed)
        self.assertEqual(kernel.closed, [])
        self.assertEqual(psec.closed, [])
        self.assertEqual(kernel.terminated, [(202, 1)])

        kernel.active_processes = 0
        process.close(timeout=0.1)
        self.assertTrue(process._closed)
        self.assertTrue(stdout.closed)
        self.assertEqual(len(kernel.closed), 2)
        self.assertEqual(psec.closed, [303])

    def test_filesystem_acl_is_verified_before_resume_and_handles_close_after_resume(self):
        events = []

        class Authorization:
            evidence = {"state": "DACL_VERIFIED", "handle_relative": True, "effective_access": "NOT_TESTED"}

            def close(self):
                events.append("close")

        class Manager:
            def apply(self, workspace, scratch, package_sid):
                events.append(("apply", workspace, scratch, package_sid))
                return Authorization()

        class Kernel:
            def ResumeThread(self, thread_handle):
                events.append(("resume", thread_handle))
                return 1

        previous, evidence = _resume_after_filesystem_authorization(
            Kernel(), 101, Manager(), "C:/job/workspace", "C:/job/scratch",
            "S-1-15-2-123-456",
        )
        self.assertEqual(previous, 1)
        self.assertEqual(evidence["state"], "DACL_VERIFIED")
        self.assertEqual(events[0][0], "apply")
        self.assertEqual(events[1], ("resume", 101))
        self.assertEqual(events[2], "close")

    def test_filesystem_acl_failure_prevents_resume(self):
        events = []

        class Manager:
            def apply(self, workspace, scratch, package_sid):
                events.append("apply")
                raise WindowsPsecError("ACL verification failed")

        class Kernel:
            def ResumeThread(self, thread_handle):
                events.append("resume")
                return 1

        with self.assertRaisesRegex(WindowsPsecError, "ACL verification failed"):
            _resume_after_filesystem_authorization(
                Kernel(), 101, Manager(), "C:/job/workspace", "C:/job/scratch",
                "S-1-15-2-123-456",
            )
        self.assertEqual(events, ["apply"])

    def test_unexpected_initial_suspend_count_fails_and_closes_acl_handles(self):
        events = []

        class Authorization:
            evidence = {"state": "VERIFIED"}

            def close(self):
                events.append("close")

        class Manager:
            def apply(self, workspace, scratch, package_sid):
                events.append("apply")
                return Authorization()

        class Kernel:
            def ResumeThread(self, thread_handle):
                events.append("resume")
                return 0

        with self.assertRaisesRegex(WindowsPsecError, "suspend count"):
            _resume_after_filesystem_authorization(
                Kernel(), 101, Manager(), "C:/job/workspace", "C:/job/scratch",
                "S-1-15-2-123-456",
            )
        self.assertEqual(events, ["apply", "resume", "close"])

    def test_process_retains_read_only_token_diagnostics(self):
        kernel = FakeKernel32(active_processes=1)
        evidence = {
            "state": "PASS",
            "captured_before_resume": True,
            "is_app_container": True,
            "user_sid": "S-1-5-21-test",
        }
        process = WindowsPsecProcess(
            kernel32=kernel,
            process_handle=101,
            job_handle=202,
            psec_dll=FakePsecDll(),
            psec_handle=303,
            stdout=io.BytesIO(),
            pid=404,
            args=("python.exe", "--version"),
            token_diagnostics=evidence,
        )
        self.assertIs(process.token_diagnostics, evidence)
        process.close()

    @staticmethod
    def _captured_app_container_token():
        return {
            "state": "CAPTURED",
            "captured_before_resume": True,
            "is_app_container": True,
            "app_container_sid": "S-1-15-2-123-456",
            "user_sid": "S-1-5-21-1-2-3-1001",
            "integrity_sid": "S-1-16-4096",
            "elevation_type": 1,
            "groups": [{"sid": "S-1-5-32-545", "attributes": 4}],
            "capabilities": [],
        }

    def test_app_container_token_validation_accepts_complete_identity(self):
        token = self._captured_app_container_token()
        self.assertIs(_require_app_container_token(token), token)

    def test_app_container_token_validation_rejects_incomplete_identity(self):
        token = self._captured_app_container_token()
        token.pop("capabilities")
        with self.assertRaisesRegex(WindowsPsecError, "incomplete"):
            _require_app_container_token(token)

    def test_app_container_token_validation_rejects_non_app_container(self):
        token = self._captured_app_container_token()
        token["is_app_container"] = False
        with self.assertRaisesRegex(WindowsPsecError, "not an AppContainer"):
            _require_app_container_token(token)

    def test_app_container_token_validation_rejects_invalid_package_sid(self):
        token = self._captured_app_container_token()
        token["app_container_sid"] = "S-1-15-2-not-a-sid"
        with self.assertRaisesRegex(WindowsPsecError, "Package SID is invalid"):
            _require_app_container_token(token)

    def test_app_container_token_validation_rejects_non_package_sid(self):
        token = self._captured_app_container_token()
        token["app_container_sid"] = "S-1-5-21-1-2-3-1001"
        with self.assertRaisesRegex(WindowsPsecError, "Package SID is invalid"):
            _require_app_container_token(token)

    def test_app_container_token_validation_rejects_package_sid_without_identity_subauthority(self):
        token = self._captured_app_container_token()
        token["app_container_sid"] = "S-1-15-2"
        with self.assertRaisesRegex(WindowsPsecError, "Package SID is invalid"):
            _require_app_container_token(token)

    def test_app_container_token_validation_rejects_out_of_range_sid_subauthority(self):
        token = self._captured_app_container_token()
        token["app_container_sid"] = "S-1-15-2-4294967296"
        with self.assertRaisesRegex(WindowsPsecError, "Package SID is invalid"):
            _require_app_container_token(token)

    def test_app_container_token_validation_rejects_unknown_elevation_type(self):
        token = self._captured_app_container_token()
        token["elevation_type"] = 4
        with self.assertRaisesRegex(WindowsPsecError, "elevation type is invalid"):
            _require_app_container_token(token)

    def test_app_container_token_validation_requires_pre_resume_capture(self):
        token = self._captured_app_container_token()
        token["captured_before_resume"] = False
        with self.assertRaisesRegex(WindowsPsecError, "before resume"):
            _require_app_container_token(token)

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
