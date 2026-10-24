import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = (ROOT / "Start-DCP-Dashboard.ps1").read_text(encoding="utf-8-sig")
STOP = (ROOT / "Stop-DCP-Dashboard.ps1").read_text(encoding="utf-8-sig")
OPEN_CMD = (ROOT / "Open-DCP-Dashboard.cmd").read_text(encoding="utf-8-sig")
STOP_CMD = (ROOT / "Stop-DCP-Dashboard.cmd").read_text(encoding="utf-8-sig")
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8-sig")


class DashboardLauncherContractTests(unittest.TestCase):
    def test_launchers_are_project_relative_and_localhost_only(self):
        self.assertIn("[System.IO.Path]::GetFullPath($PSScriptRoot)", START)
        self.assertIn("[System.IO.Path]::GetFullPath($PSScriptRoot)", STOP)
        self.assertIn("127.0.0.1", START)
        self.assertIn("127.0.0.1", STOP)
        self.assertIn("ValidateRange(1, 65535)", START)
        self.assertIn("ValidateRange(1, 65535)", STOP)

    def test_start_verifies_served_content_before_reuse(self):
        self.assertIn("Test-DcpResponseMatchesDashboard", START)
        self.assertIn("Get-FileHash -LiteralPath $indexFile -Algorithm SHA256", START)
        self.assertIn("LocalAddress -ne '127.0.0.1'", START)
        self.assertIn("refusing to use or stop it", START)

    def test_start_uses_atomic_record_and_records_process_creation(self):
        self.assertIn("processCreatedAtUtc", START)
        self.assertIn("Move-Item -LiteralPath $tempRecord -Destination $pidFile", START)
        self.assertIn("STALE_RECORD_BACKED_UP", START)

    def test_stop_requires_exact_process_and_listener_ownership(self):
        self.assertIn("Test-DcpServerCommand -Process $process", STOP)
        self.assertIn("processCreatedAtUtc", STOP)
        self.assertIn("recorded PID does not exclusively own port", STOP)
        self.assertIn("stale record preserved as", STOP)

    def test_cmd_wrappers_use_script_relative_paths_and_exact_exit_code(self):
        self.assertIn("%~dp0Start-DCP-Dashboard.ps1", OPEN_CMD)
        self.assertIn("%~dp0Stop-DCP-Dashboard.ps1", STOP_CMD)
        self.assertIn('if "%RC%"=="4" goto :not_owned', STOP_CMD)

    def test_local_python_cache_and_temp_harness_are_ignored(self):
        self.assertIn("__pycache__/", GITIGNORE)
        self.assertIn("*.py[cod]", GITIGNORE)
        self.assertIn(".dcp-test-8001/", GITIGNORE)


if __name__ == "__main__":
    unittest.main(verbosity=2)