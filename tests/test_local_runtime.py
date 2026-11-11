"""Runtime manager tests using real loopback HTTP and process lifecycle."""
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from tools.local_runner_agent.workspace import WorkspaceManager
from tools.local_runner_agent.runtime import RuntimeManager, RuntimeErrorDCP


class RuntimeManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job = str(uuid.uuid4())
        self.worker = "runtime-test"
        self.workspaces = WorkspaceManager(self.root / "workspaces")
        self.workspace = self.workspaces.create(self.job, self.worker)
        self.dist = self.workspace / "source" / "dist"
        self.dist.mkdir(parents=True)
        (self.dist / "index.html").write_text("<h1>DCP Preview</h1>", encoding="utf-8")
        (self.dist / "app.js").write_text("window.ready = true", encoding="utf-8")
        self.manager = RuntimeManager(self.workspaces, startup_timeout_seconds=5)

    def tearDown(self):
        for row in self.manager.list_for_job(self.job, self.worker):
            # Session tokens are intentionally not included in list output.
            runtime = self.manager._runtimes[row["runtime_id"]]
            self.manager.stop(row["runtime_id"], runtime.token)
        self.temp.cleanup()

    def test_starts_real_loopback_preview_and_stops_process(self):
        started = self.manager.start_static(self.job, self.worker)
        self.assertEqual(started["state"], "running")
        self.assertEqual(started["bind_host"], "127.0.0.1")
        self.assertTrue(1024 < started["port"] < 65536)
        import urllib.request
        with urllib.request.urlopen(started["url"], timeout=2) as response:
            body = response.read()
            self.assertEqual(response.status, 200)
        self.assertIn(b"DCP Preview", body)
        self.assertEqual(self.manager.status(started["runtime_id"], started["session_token"])["state"], "running")
        stopped = self.manager.stop(started["runtime_id"], started["session_token"])
        self.assertEqual(stopped["state"], "stopped")
        with self.assertRaises(RuntimeErrorDCP):
            self.manager.status(started["runtime_id"], started["session_token"])

    def test_requires_valid_session_token_for_status_logs_and_stop(self):
        started = self.manager.start_static(self.job, self.worker)
        with self.assertRaises(RuntimeErrorDCP):
            self.manager.status(started["runtime_id"], "wrong-token")
        with self.assertRaises(RuntimeErrorDCP):
            self.manager.logs(started["runtime_id"], "wrong-token")
        with self.assertRaises(RuntimeErrorDCP):
            self.manager.stop(started["runtime_id"], "wrong-token")

    def test_rejects_symlinked_or_missing_build_output(self):
        (self.dist / "index.html").unlink()
        (self.root / "outside.html").write_text("outside", encoding="utf-8")
        try:
            (self.dist / "index.html").symlink_to(self.root / "outside.html")
        except OSError:
            self.skipTest("Symlink creation is unavailable on this host")
        with self.assertRaises(RuntimeErrorDCP):
            self.manager.start_static(self.job, self.worker)

    def test_runtime_limit_and_expiry(self):
        manager = RuntimeManager(self.workspaces, max_active=1, session_ttl_seconds=60)
        first = manager.start_static(self.job, self.worker)
        with self.assertRaises(RuntimeErrorDCP):
            manager.start_static(self.job, self.worker)
        manager._runtimes[first["runtime_id"]].expires_at = time.monotonic() - 1
        self.assertEqual(manager.reap_expired(), 1)
        self.assertEqual(manager.list_for_job(self.job, self.worker), [])

    def test_runtime_is_bound_to_existing_workspace_and_job(self):
        with self.assertRaises(RuntimeErrorDCP):
            self.manager.start_static(str(uuid.uuid4()), self.worker)


if __name__ == "__main__":
    unittest.main()
