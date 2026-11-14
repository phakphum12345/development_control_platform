from __future__ import annotations

import contextlib
import io
import os
import unittest

from tools.local_runner_agent import windows_psec_host_acceptance as host


class WindowsPsecHostAcceptanceTests(unittest.TestCase):
    def test_embedded_policy_payload_is_valid_python(self):
        compile(host._read_only_network_payload(), "<psec-host-policy-payload>", "exec")

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
