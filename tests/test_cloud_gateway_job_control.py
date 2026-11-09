"""Tests for the local-first DCP job queue; no repository code is executed."""
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

    def test_worker_ownership_and_missing_job(self):
        job, _ = self.create()
        self.store.claim("local-worker-1")
        with self.assertRaises(JobConflict):
            self.store.append_log(job["id"], "other-worker", "forged")
        with self.assertRaises(JobNotFound):
            self.store.cancel("missing")

if __name__ == "__main__":
    unittest.main()
