"""Windows launcher contract for the unified local Runner Agent."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "Start-DCP-Gateway-Runner.ps1").read_text(encoding="utf-8-sig")


class UnifiedLocalRunnerLauncherContractTests(unittest.TestCase):
    def test_launcher_uses_the_unified_local_runner_agent(self):
        self.assertIn("-m tools.local_runner_agent", SCRIPT)
        self.assertNotIn("-m tools.runner_agent.agent", SCRIPT)
        self.assertIn("DCP_RUNNER_WORKER_ID", SCRIPT)
        self.assertIn("DCP_RUNNER_EXECUTION_ENABLED = '1'", SCRIPT)

    def test_launcher_requires_explicit_trusted_sources_for_execution(self):
        self.assertIn("[string[]]$TrustedRepository = @()", SCRIPT)
        self.assertIn("[string[]]$TrustedLocalProject = @()", SCRIPT)
        self.assertIn("at least one explicit -TrustedRepository or -TrustedLocalProject", SCRIPT)
        self.assertIn("Trusted Local Project IDs must be unique", SCRIPT)

    def test_launcher_selects_offline_once_or_supervised_modes(self):
        self.assertIn("@('--enroll-only')", SCRIPT)
        self.assertIn("@('--once')", SCRIPT)
        self.assertIn("@('--serve')", SCRIPT)
        self.assertIn("DCP_RUNNER_WORKSPACE_ROOT", SCRIPT)

    def test_launcher_does_not_enable_playwright_implicitly(self):
        self.assertIn("Remove-Item Env:DCP_RUNNER_PLAYWRIGHT_ENABLED", SCRIPT)
        self.assertIn("Remove-Item Env:DCP_RUNNER_CAPABILITIES", SCRIPT)


if __name__ == "__main__":
    unittest.main()
