"""Safety and configuration tests for the local Playwright smoke tester."""
import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.browser_test import BrowserTestError, StaticWebPlaywrightTester
from tools.local_runner_agent.workspace import WorkspaceManager


class StaticWebPlaywrightTesterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspaces = WorkspaceManager(self.root / "workspaces")
        self.job_id = "12345678-1234-4234-8234-123456789abc"
        self.worker_id = "runner-browser-test"
        self.workspace = self.workspaces.create(self.job_id, self.worker_id)
        (self.workspace / "source").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_browser_execution_is_disabled_by_default(self):
        tester = StaticWebPlaywrightTester(self.workspaces)
        with self.assertRaisesRegex(BrowserTestError, "disabled"):
            tester.run(self.job_id, self.worker_id)
        self.assertFalse((self.workspace / "source" / ".dcp-test-results").exists())

    def test_results_directory_is_created_private_and_only_once(self):
        results = StaticWebPlaywrightTester._results_directory(self.workspace)
        self.assertTrue(results.is_dir())
        with self.assertRaisesRegex(BrowserTestError, "already exists"):
            StaticWebPlaywrightTester._results_directory(self.workspace)

    def test_results_directory_rejects_symlink(self):
        source = self.workspace / "source"
        target = self.root / "outside"
        target.mkdir()
        try:
            (source / ".dcp-test-results").symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation is unavailable on this host")
        with self.assertRaisesRegex(BrowserTestError, "unsafe"):
            StaticWebPlaywrightTester._results_directory(self.workspace)

    def test_real_chromium_smoke_creates_screenshots_report_and_evidence(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                if not Path(playwright.chromium.executable_path).is_file():
                    self.skipTest("Playwright Chromium is not installed on this host")
        except ImportError:
            self.skipTest("Python Playwright is not installed on this host")

        output = self.workspace / "source" / "dist"
        output.mkdir()
        (output / "index.html").write_text(
            '<!doctype html><html lang="en"><head><title>DCP Browser Fixture</title>'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '</head><body><main><h1>Browser fixture is ready</h1></main></body></html>',
            encoding="utf-8",
        )
        tester = StaticWebPlaywrightTester(
            self.workspaces, enabled=True, timeout_ms=10000,
        )
        result = tester.run(self.job_id, self.worker_id)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(len(result["screenshots"]), 3)
        self.assertTrue(result["artifact_path"].is_file())
        report = self.workspace / "source" / ".dcp-test-results" / "report.json"
        self.assertTrue(report.is_file())
        self.assertIn('"status": "PASS"', report.read_text(encoding="utf-8"))

    def test_timeout_is_bounded(self):
        for value in (True, 0, 999, 60001):
            with self.subTest(timeout=value), self.assertRaises(ValueError):
                StaticWebPlaywrightTester(self.workspaces, enabled=True, timeout_ms=value)


if __name__ == "__main__":
    unittest.main()
