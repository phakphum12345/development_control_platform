"""Compatibility contract for the historical Local Runner PowerShell entry point."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "Start-DCP-Local-Runner.ps1").read_text(encoding="utf-8-sig")


class LegacyLocalRunnerLauncherContractTests(unittest.TestCase):
    def test_legacy_launcher_forwards_supported_parameters_to_unified_runner(self):
        self.assertIn("Start-DCP-Gateway-Runner.ps1", SCRIPT)
        self.assertIn("@PSBoundParameters", SCRIPT)
        self.assertIn("$WorkerId", SCRIPT)
        self.assertIn("$EnableExecution", SCRIPT)
        self.assertIn("$Once", SCRIPT)
        self.assertIn("$TrustedRepository", SCRIPT)
        self.assertIn("$TrustedLocalProject", SCRIPT)


if __name__ == "__main__":
    unittest.main()
