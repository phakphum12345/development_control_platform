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
        completed = mock.Mock(returncode=0, stdout="DACL evidence", stderr="")
        with mock.patch.dict(os.environ, {"SYSTEMROOT": r"C:\\Windows"}):
            with mock.patch.object(host.Path, "is_file", return_value=True):
                with mock.patch.object(host.subprocess, "run", return_value=completed) as run:
                    result = host._filesystem_acl(host.Path(r"C:\\DCP\\workspace"))

        self.assertEqual(result["state"], "CAPTURED")
        self.assertEqual(result["stdout"], "DACL evidence")
        command = run.call_args.args[0]
        self.assertEqual(command[0], r"C:\\Windows\\System32\\icacls.exe")
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["check"], False)

    def test_non_windows_host_reports_blocked_without_loading_psec(self):
        if os.name == "nt":
            self.skipTest("Windows host executes the native acceptance harness")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = host.main()
        self.assertEqual(code, 2)
        self.assertIn('"state": "BLOCKED"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
