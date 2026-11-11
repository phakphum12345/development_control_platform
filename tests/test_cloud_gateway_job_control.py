"""Tests for the local-first DCP job queue; no repository code is executed."""
import json
import tempfile
import unittest
from pathlib import Path
from tools.cloud_gateway.job_control import JobConflict, JobNotFound, JobStore

SHA = "a" * 40

class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JobStore(str(Path(self.tmp.name) / "jobs.sqlite3"))
        self.payload = {"repository": "owner/repo", "commit_sha": SHA, "target": "test"}

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, key="job-key-0001"):
        return self.store.create(self.payload, key)

    def test_idempotent_create_and_event(self):
        first, created = self.create()
        again, created_again = self.create()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(first["state"], "queued")
        self.assertEqual(self.store.events(first["id"])[0]["event"], "queued")

    def test_conflicting_idempotency_and_invalid_payload(self):
        self.create()
        with self.assertRaises(JobConflict):
            self.store.create({**self.payload, "target": "build"}, "job-key-0001")
        with self.assertRaises(ValueError):
            self.store.create({**self.payload, "commit_sha": "bad"}, "job-key-0002")


    def test_accepts_static_and_vite_web_targets(self):
        for target in ("build_static_web", "build_vite"):
            with self.subTest(target=target):
                row, created = self.store.create(
                    {**self.payload, "target": target}, f"job-key-{target}"
                )
                self.assertTrue(created)
                self.assertEqual(row["target"], target)

    def test_local_folder_accepts_playwright_target_only_for_static_test_flow(self):
        payload = {
            "source_type": "local_folder",
            "project_id": "12345678-1234-4234-8234-123456789abc",
            "snapshot_sha256": "d" * 64,
            "target": "test_static_web",
        }
        row, created = self.store.create(payload, "local-folder-playwright-01")
        self.assertTrue(created)
        self.assertEqual(row["target"], "test_static_web")
        self.assertEqual(row["payload"]["source_type"], "local_folder")

    def test_local_folder_job_uses_immutable_snapshot_identity(self):
        project_id = "12345678-1234-4234-8234-123456789abc"
        payload = {
            "source_type": "local_folder",
            "project_id": project_id,
            "snapshot_sha256": "b" * 64,
            "target": "build_static_web",
        }
        row, created = self.store.create(payload, "local-folder-job-01")
        self.assertTrue(created)
        self.assertEqual(row["payload"]["source_type"], "local_folder")
        self.assertEqual(row["payload"]["source_id"], project_id)
        self.assertEqual(row["payload"]["source_sha256"], "b" * 64)
        self.assertEqual(row["repository"], "local-folder/" + project_id)
        self.assertRegex(row["commit_sha"], r"^[0-9a-f]{40}$")
        again, created_again = self.store.create(payload, "local-folder-job-01")
        self.assertFalse(created_again)
        self.assertEqual(again["id"], row["id"])

    def test_local_folder_job_rejects_invalid_snapshot_and_non_web_targets(self):
        base = {
            "source_type": "local_folder",
            "project_id": "12345678-1234-4234-8234-123456789abc",
            "snapshot_sha256": "c" * 64,
            "target": "build_static_web",
        }
        for payload in (
            {**base, "snapshot_sha256": "bad"},
            {**base, "project_id": "../outside"},
            {**base, "target": "build_android"},
            {**base, "path": "C:/Users/owner"},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.store.create(payload, "local-folder-invalid-" + str(len(json.dumps(payload))))

    def test_claim_heartbeat_logs_and_finish(self):
        job, _ = self.create()
        claimed = self.store.claim("local-worker-1")
        self.assertEqual(claimed["id"], job["id"])
        self.store.heartbeat(job["id"], "local-worker-1")
        self.store.append_log(job["id"], "local-worker-1", "tests started")
        done = self.store.finish(job["id"], "local-worker-1", "succeeded", {"exit_code": 0})
        self.assertEqual(done["state"], "succeeded")
        self.assertEqual(self.store.logs(job["id"])[0]["message"], "tests started")
        self.assertIsNone(self.store.claim("local-worker-2"))

    def test_cancel_queued_and_running(self):
        queued, _ = self.create()
        self.assertEqual(self.store.cancel(queued["id"])["state"], "cancelled")
        running, _ = self.create("job-key-0002")
        self.store.claim("local-worker-1")
        self.assertEqual(self.store.cancel(running["id"])["state"], "cancel_requested")
        with self.assertRaises(JobConflict):
            self.store.finish(running["id"], "local-worker-1", "succeeded")
        self.assertEqual(self.store.finish(running["id"], "local-worker-1", "cancelled")["state"], "cancelled")

    def test_expired_lease_is_requeued_and_old_worker_is_fenced(self):
        job, _ = self.create()
        claimed = self.store.claim("local-worker-1")
        self.assertEqual(claimed["id"], job["id"])
        with self.store.db() as db:
            db.execute(
                "UPDATE jobs SET lease_until=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", job["id"]),
            )
        with self.assertRaises(JobConflict):
            self.store.heartbeat(job["id"], "local-worker-1")
        recovered = self.store.recover_expired_leases()
        self.assertEqual(recovered, [{"id": job["id"], "state": "queued"}])
        reclaimed = self.store.claim("local-worker-2")
        self.assertEqual(reclaimed["worker"], "local-worker-2")
        with self.assertRaises(JobConflict):
            self.store.finish(job["id"], "local-worker-1", "succeeded")

    def test_expired_cancel_request_becomes_cancelled(self):
        job, _ = self.create()
        self.store.claim("local-worker-1")
        self.store.cancel(job["id"])
        with self.store.db() as db:
            db.execute(
                "UPDATE jobs SET lease_until=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", job["id"]),
            )
        recovered = self.store.recover_expired_leases()
        self.assertEqual(recovered, [{"id": job["id"], "state": "cancelled"}])
        self.assertEqual(self.store.get(job["id"])["state"], "cancelled")

    def test_worker_ownership_and_missing_job(self):
        job, _ = self.create()
        self.store.claim("local-worker-1")
        with self.assertRaises(JobConflict):
            self.store.append_log(job["id"], "other-worker", "forged")
        with self.assertRaises(JobNotFound):
            self.store.cancel("missing")

if __name__ == "__main__":
    unittest.main()
