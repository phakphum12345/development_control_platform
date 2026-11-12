"""Real Chromium acceptance for the fixed local static-app test plan."""
import importlib.util
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

from tools.local_runner_agent.browser_test import StaticWebPlaywrightTester
from tools.local_runner_agent.workspace import WorkspaceManager


def _chromium_ready():
    if importlib.util.find_spec("playwright") is None:
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).is_file()
    except Exception:
        return False


@unittest.skipUnless(_chromium_ready(), "Python Playwright and Chromium are optional Runner prerequisites")
class StaticWebPlaywrightAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspaces = WorkspaceManager(self.root / "workspaces")
        self.job_id = str(uuid.uuid4())
        self.worker_id = "playwright-acceptance"
        self.workspaces.create(self.job_id, self.worker_id)
        self.output = self.workspaces.get(self.job_id, self.worker_id) / "source" / "dist"
        self.output.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_static_app_is_opened_in_sandboxed_chromium_at_three_viewports(self):
        (self.output / "index.html").write_text(
            "<!doctype html><html lang='en'><head><meta name='viewport' "
            "content='width=device-width,initial-scale=1'><title>Sample App</title>"
            "</head><body><main><h1>Local preview</h1><button>Continue</button>"
            "<a href='/next'>Next</a></main></body></html>",
            encoding="utf-8",
        )
        tester = StaticWebPlaywrightTester(self.workspaces, enabled=True)
        result = tester.run(self.job_id, self.worker_id)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual([row["name"] for row in result["screenshots"]],
                         ["mobile", "tablet", "desktop"])
        artifact = self.root / "workspaces" / self.job_id / ".dcp-artifacts" / "web-test-results.zip"
        self.assertTrue(artifact.is_file())
        with zipfile.ZipFile(artifact) as archive:
            names = set(archive.namelist())
        self.assertEqual(names, {
            "report.json", "viewport-mobile.png", "viewport-tablet.png", "viewport-desktop.png"
        })

    def test_external_network_requests_are_blocked_and_fail_the_report(self):
        (self.output / "index.html").write_text(
            "<!doctype html><html lang='en'><head><meta name='viewport' "
            "content='width=device-width,initial-scale=1'><title>Blocked external</title>"
            "<script src='https://example.invalid/tracker.js'></script>"
            "</head><body><h1>Local only</h1></body></html>",
            encoding="utf-8",
        )
        tester = StaticWebPlaywrightTester(self.workspaces, enabled=True)
        result = tester.run(self.job_id, self.worker_id)
        self.assertEqual(result["status"], "FAIL")
        self.assertGreaterEqual(result["blocked_external_request_count"], 1)


if __name__ == "__main__":
    unittest.main()
