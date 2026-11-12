import unittest
import uuid

from tools.cloud_gateway.preview import AuthenticatedPreviewManager, PreviewError


class FakeWorkspace:
    def __init__(self):
        self.retained = []
        self.cleanup_calls = 0
    def retain_for_preview(self, job_id, worker_id, *, ttl_seconds):
        self.retained.append((job_id, worker_id, ttl_seconds))
    def cleanup_expired_preview_workspaces(self):
        self.cleanup_calls += 1
        return 0


class FakeRuntime:
    def __init__(self):
        self.rows = {}
        self.started = 0
        self.workspaces = FakeWorkspace()
        self.session_ttl_seconds = 1800
        self.reaped = 0
    def start_static(self, job_id, worker_id, *, output_relative):
        self.started += 1
        runtime_id = str(uuid.uuid4())
        row = {"runtime_id": runtime_id, "session_token": "private-capability",
               "expires_in_seconds": 120, "started_at": "now"}
        self.rows[runtime_id] = {"job_id": job_id, "worker_id": worker_id,
                                 "token": row["session_token"], "state": "running",
                                 "port": 43210}
        return row
    def start_next(self, job_id, worker_id, *, owner_approved=False):
        if owner_approved is not True:
            raise RuntimeError("Owner approval required")
        self.started += 1
        runtime_id = str(uuid.uuid4())
        row = {"runtime_id": runtime_id, "session_token": "private-capability",
               "expires_in_seconds": 120, "started_at": "now", "runtime_kind": "next"}
        self.rows[runtime_id] = {"job_id": job_id, "worker_id": worker_id,
                                 "token": row["session_token"], "state": "running",
                                 "port": 43210, "runtime_kind": "next"}
        return row
    def status(self, runtime_id, token):
        row = self.rows[runtime_id]
        if token != row["token"]:
            raise RuntimeError("bad capability")
        return {"runtime_id": runtime_id, "job_id": row["job_id"],
                "state": row["state"], "port": row["port"],
                "runtime_kind": row.get("runtime_kind", "static"),
                "expires_in_seconds": 100}
    def stop(self, runtime_id, token):
        self.status(runtime_id, token)
        self.rows[runtime_id]["state"] = "stopped"
        return {"runtime_id": runtime_id, "state": "stopped"}
    def reap_expired(self):
        self.reaped += 1
        return 0


class AuthenticatedPreviewManagerTests(unittest.TestCase):
    def setUp(self):
        self.runtime = FakeRuntime()
        self.previews = AuthenticatedPreviewManager(self.runtime)
        self.job_id = str(uuid.uuid4())

    def test_reaper_stops_expired_runtime_manager_and_cleans_expired_workspaces(self):
        self.assertEqual(self.previews.reap_expired(), 0)
        self.assertEqual(self.runtime.reaped, 1)
        self.assertEqual(self.runtime.workspaces.cleanup_calls, 1)

    def test_preview_start_renews_workspace_retention_for_runtime_ttl(self):
        self.previews.start(self.job_id, "local-worker")
        self.assertEqual(
            self.runtime.workspaces.retained,
            [(self.job_id, "local-worker", 1860)],
        )

    def test_browser_response_never_contains_runtime_capability_or_upstream_url(self):
        row = self.previews.start(self.job_id, "local-worker")
        self.assertNotIn("session_token", row)
        self.assertNotIn("url", row)
        self.assertNotIn("port", row)
        self.assertIn(f"/api/jobs/{self.job_id}/previews/", row["preview_path"])
        self.assertNotIn("private-capability", repr(row))

    def test_one_preview_per_job_and_job_binding(self):
        row = self.previews.start(self.job_id, "local-worker")
        with self.assertRaises(PreviewError):
            self.previews.start(self.job_id, "local-worker")
        with self.assertRaises(PreviewError):
            self.previews.status(row["runtime_id"], str(uuid.uuid4()))
        self.assertEqual(self.runtime.started, 1)

    def test_stale_runtime_is_pruned_before_a_new_preview_starts(self):
        first = self.previews.start(self.job_id, "local-worker")
        self.runtime.rows[first["runtime_id"]]["state"] = "exited"
        second = self.previews.start(self.job_id, "local-worker")
        self.assertNotEqual(first["runtime_id"], second["runtime_id"])
        self.assertEqual(self.runtime.started, 2)

    def test_lists_only_active_previews_for_the_requested_job(self):
        row = self.previews.start(self.job_id, "local-worker")
        other_job = str(uuid.uuid4())
        self.previews.start(other_job, "local-worker")
        listed = self.previews.list_for_job(self.job_id)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["runtime_id"], row["runtime_id"])
        self.assertNotIn("session_token", listed[0])
        self.assertNotIn("port", listed[0])


    def test_next_preview_requires_owner_approval_and_reports_runtime_kind(self):
        with self.assertRaisesRegex(PreviewError, "explicit Owner approval"):
            self.previews.start(self.job_id, "local-worker", runtime_kind="next")
        row = self.previews.start(
            self.job_id, "local-worker", runtime_kind="next", owner_approved=True
        )
        self.assertEqual(row["runtime_kind"], "next")
        status = self.previews.status(row["runtime_id"], self.job_id)
        self.assertEqual(status["runtime_kind"], "next")

    def test_angular_browser_output_is_an_allowed_static_preview_root(self):
        row = self.previews.start(
            self.job_id, "local-worker", "source/dist/browser", runtime_kind="static"
        )
        self.assertEqual(row["runtime_kind"], "static")

    def test_status_and_stop_keep_capability_server_side(self):
        row = self.previews.start(self.job_id, "local-worker")
        status = self.previews.status(row["runtime_id"], self.job_id)
        self.assertEqual(status["state"], "running")
        stopped = self.previews.stop(row["runtime_id"], self.job_id)
        self.assertEqual(stopped["state"], "stopped")
        with self.assertRaises(PreviewError):
            self.previews.status(row["runtime_id"], self.job_id)

    def test_rejects_invalid_output_and_path_traversal(self):
        with self.assertRaises(PreviewError):
            self.previews.start(self.job_id, "local-worker", "../outside")
        for path in ("../secret", "a/../../secret", "/etc/passwd", "a\\\\b", "a//b"):
            with self.subTest(path=path), self.assertRaises(PreviewError):
                self.previews._safe_relative_path(path)

    def test_rejects_invalid_job_and_worker(self):
        with self.assertRaises(PreviewError):
            self.previews.start("not-a-uuid", "local-worker")
        with self.assertRaises(PreviewError):
            self.previews.start(self.job_id, "bad/worker")


if __name__ == "__main__":
    unittest.main()
