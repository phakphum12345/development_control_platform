from __future__ import annotations

import contextlib
import io
import os
import unittest
from unittest import mock

from tools.local_runner_agent import windows_psec_host_acceptance as host


class WindowsPsecHostAcceptanceTests(unittest.TestCase):
    def test_paths_overlap_detects_denied_parent_and_child(self):
        self.assertTrue(
            host._paths_overlap(
                r"C:\\Users\\phakp\\AppData\\Local\\Temp\\job",
                r"C:\\Users\\phakp",
            )
        )
        self.assertFalse(
            host._paths_overlap(r"D:\\DCP-PSEC-Acceptance", r"C:\\Users\\phakp")
        )

    def test_embedded_policy_payload_is_valid_python(self):
        compile(host._read_only_network_payload(), "<psec-host-policy-payload>", "exec")

    def test_embedded_payload_captures_child_token_evidence(self):
        payload = host._read_only_network_payload()
        for marker in (
            "whoami.exe",
            '"/all"',
            "subprocess.run",
            "shell=False",
            'result["child_token"]',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, payload)

    def test_filesystem_acl_diagnostic_is_read_only(self):
        dacl = mock.Mock(returncode=0, stdout="DACL evidence", stderr="")
        descriptor = mock.Mock(
            returncode=0,
            stdout='{"owner":"HOST\\\\user","dacl_protected":true,"sddl":"D:PAI"}',
            stderr="",
        )
        with mock.patch.dict(os.environ, {"SYSTEMROOT": r"C:\Windows"}):
            with mock.patch.object(host.Path, "is_file", return_value=True):
                with mock.patch.object(
                    host.subprocess, "run", side_effect=[dacl, descriptor]
                ) as run:
                    result = host._filesystem_acl(host.Path(r"C:\DCP\workspace"))

        self.assertEqual(result["state"], "CAPTURED")
        self.assertEqual(result["stdout"], "DACL evidence")
        self.assertEqual(result["security_descriptor"]["state"], "CAPTURED")
        self.assertTrue(result["security_descriptor"]["dacl_protected"])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args.args[0][0],
            str(host.Path(r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
        )
        self.assertEqual(len(run.call_args.args[0]), 5)
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["check"], False)
        self.assertEqual(
            run.call_args.kwargs["env"]["DCP_PSEC_ACL_PATH"],
            r"C:\DCP\workspace",
        )

    def test_non_windows_host_reports_blocked_without_loading_psec(self):
        if os.name == "nt":
            self.skipTest("Windows host executes the native acceptance harness")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = host.main()
        self.assertEqual(code, 2)
        self.assertIn('"state": "BLOCKED"', output.getvalue())


    def test_app_container_profile_probe_reports_path_and_matching_child_environment(self):
        import ctypes
        import tempfile
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            buffer = ctypes.create_unicode_buffer(directory)
            freed = []

            def get_folder(package_sid, output):
                self.assertEqual(package_sid, "S-1-15-2-123-456")
                ctypes.cast(output, ctypes.POINTER(ctypes.c_wchar_p))[0] = ctypes.cast(
                    buffer, ctypes.c_wchar_p
                )
                return 0

            def co_task_mem_free(pointer):
                freed.append(pointer.value)

            userenv = SimpleNamespace(GetAppContainerFolderPath=get_folder)
            ole32 = SimpleNamespace(CoTaskMemFree=co_task_mem_free)
            token = {"environment": {"LOCALAPPDATA": directory}}
            with mock.patch.object(
                ctypes, "WinDLL", side_effect=lambda name, **kwargs: (
                    userenv if name == "userenv.dll" else ole32
                ), create=True
            ):
                with mock.patch.object(
                    host, "_filesystem_acl", return_value={"state": "CAPTURED", "sddl": "D:PAI"}
                ) as acl:
                    result = host._app_container_profile_evidence(
                        "S-1-15-2-123-456", token
                    )

        self.assertEqual(result["state"], "CAPTURED")
        self.assertEqual(result["path"], directory)
        self.assertTrue(result["directory_exists"])
        self.assertTrue(result["child_localappdata_matches"])
        self.assertEqual(result["acl"]["sddl"], "D:PAI")
        acl.assert_called_once()
        self.assertEqual(len(freed), 1)

    def test_app_container_profile_probe_reports_environment_mismatch(self):
        import ctypes
        import tempfile
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            buffer = ctypes.create_unicode_buffer(directory)

            def get_folder(package_sid, output):
                ctypes.cast(output, ctypes.POINTER(ctypes.c_wchar_p))[0] = ctypes.cast(
                    buffer, ctypes.c_wchar_p
                )
                return 0

            userenv = SimpleNamespace(GetAppContainerFolderPath=get_folder)
            ole32 = SimpleNamespace(CoTaskMemFree=lambda pointer: None)
            with mock.patch.object(
                ctypes, "WinDLL", side_effect=lambda name, **kwargs: (
                    userenv if name == "userenv.dll" else ole32
                ), create=True
            ):
                with mock.patch.object(
                    host, "_filesystem_acl", return_value={"state": "CAPTURED"}
                ):
                    result = host._app_container_profile_evidence(
                        "S-1-15-2-123-456",
                        {"environment": {"LOCALAPPDATA": directory + r"\\Other"}},
                    )

        self.assertEqual(result["state"], "CAPTURED")
        self.assertFalse(result["child_localappdata_matches"])

    def test_app_container_profile_probe_preserves_hresult_failure(self):
        import ctypes
        from types import SimpleNamespace

        userenv = SimpleNamespace(
            GetAppContainerFolderPath=lambda package_sid, output: -2147024894
        )
        ole32 = SimpleNamespace(CoTaskMemFree=lambda pointer: None)
        with mock.patch.object(
            ctypes, "WinDLL", side_effect=lambda name, **kwargs: (
                userenv if name == "userenv.dll" else ole32
            ), create=True
        ):
            result = host._app_container_profile_evidence(
                "S-1-15-2-123-456", {"environment": {}}
            )

        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(result["hresult"], "0x80070002")

    def test_app_container_profile_probe_rejects_missing_package_sid(self):
        import ctypes

        with mock.patch.object(ctypes, "WinDLL", create=True) as win_dll:
            result = host._app_container_profile_evidence("", {})
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(win_dll.call_count, 0)


if __name__ == "__main__":
    unittest.main()
