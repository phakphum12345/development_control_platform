"""Regression contract for the historical Local Runner entry point."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "Start-DCP-Local-Runner.ps1").read_text(encoding="utf-8-sig")


class LegacyLocalRunnerLauncherContractTests(unittest.TestCase):
    def test_legacy_entry_point_keeps_its_own_supported_parameters(self):
        for parameter in (
            "$WorkerId",
            "$EnableExecution",
            "$Once",
            "$TrustedRepository",
        ):
            with self.subTest(parameter=parameter):
                self.assertIn(parameter, SCRIPT)

    def test_legacy_entry_point_keeps_safe_enrollment_and_explicit_execution(self):
        self.assertIn("'DCP\\runner-tokens.json'", SCRIPT)
        self.assertIn("http://127.0.0.1:18790/healthz", SCRIPT)
        self.assertIn("'--enroll-only'", SCRIPT.lower())
        self.assertIn("Execution requires at least one explicit -TrustedRepository", SCRIPT)
        self.assertIn("tools.runner_agent.agent", SCRIPT)
        self.assertIn("DCP_RUNNER_TRUSTED_REPOSITORIES", SCRIPT)

    def test_legacy_entry_point_restores_process_environment(self):
        self.assertIn("[Environment]::GetEnvironmentVariable", SCRIPT)
        self.assertIn("[Environment]::SetEnvironmentVariable", SCRIPT)
        self.assertIn("finally", SCRIPT)

    def test_legacy_entry_point_does_not_depend_on_gateway_wrapper(self):
        self.assertNotIn("Start-DCP-Gateway-Runner.ps1", SCRIPT)
        self.assertNotIn("@PSBoundParameters", SCRIPT)


if __name__ == "__main__":
    unittest.main()
