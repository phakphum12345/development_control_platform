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
        self.assertEqual(first["attempt_count"], 0)
        self.assertEqual(first["max_attempts"], 3)
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
        self.assertIsNone(done["worker"], "terminal jobs must release their active lease owner")
        self.assertEqual(done["last_worker"], "local-worker-1")
        self.assertIsNone(done["lease_until"])
        self.assertEqual(self.store.logs(job["id"])[0]["message"], "tests started")
        self.assertIsNone(self.store.claim("local-worker-2"))

    def test_legacy_jobs_database_adds_worker_provenance_column(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy-jobs.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("""
                    CREATE TABLE jobs (
                        id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL,
                        fingerprint TEXT NOT NULL, repository TEXT NOT NULL,
                        commit_sha TEXT NOT NULL, target TEXT NOT NULL,
                        state TEXT NOT NULL, payload TEXT NOT NULL,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        worker TEXT, lease_until TEXT, cancel_at TEXT,
                        result TEXT, error_code TEXT
                    )
                """)
            migrated = JobStore(str(path))
            with migrated.db() as db:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
            self.assertIn("last_worker", columns)
            self.assertIn("attempt_count", columns)
            self.assertIn("max_attempts", columns)
            self.assertIn("checkpoint_json", columns)
            self.assertIn("checkpoint_seq", columns)
            self.assertIn("checkpoint_sha256", columns)
            self.assertIn("retry_after", columns)

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
        self.assertEqual(recovered, [{"id": job["id"], "state": "unknown", "retry_after": None}])
        self.assertEqual(self.store.get(job["id"])["state"], "unknown")
        self.assertIsNone(self.store.claim("local-worker-2"))
        resumed = self.store.resume_unknown(job["id"], "owner@example.test")
        self.assertEqual(resumed["state"], "queued")
        reclaimed = self.store.claim("local-worker-2")
        self.assertEqual(reclaimed["worker"], "local-worker-2")
        with self.assertRaises(JobConflict):
            self.store.finish(job["id"], "local-worker-1", "succeeded")

    def test_expired_worker_lease_retries_are_bounded(self):
        job, _ = self.create("job-retry-limit-01")
        first = self.store.claim("retry-worker-1")
        self.assertEqual(first["id"], job["id"])
        self.assertEqual(first["attempt_count"], 1)
        self.assertEqual(first["max_attempts"], 3)

        for attempt in (1, 2):
            checkpoint = {
                "version": 1, "step": "ready-to-finish",
                "safe_to_resume": True,
                "data": {"outcome": "succeeded", "result": {"completed_units": attempt}},
            }
            self.store.checkpoint(job["id"], "retry-worker-" + str(attempt), attempt, checkpoint)
            with self.store.db() as db:
                db.execute(
                    "UPDATE jobs SET lease_until=? WHERE id=?",
                    ("2000-01-01T00:00:00+00:00", job["id"]),
                )
            recovered = self.store.recover_expired_leases()
            self.assertEqual(recovered[0]["id"], job["id"])
            self.assertEqual(recovered[0]["state"], "retry_wait")
            self.assertIsNotNone(recovered[0]["retry_after"])
            self.assertIsNone(self.store.claim("retry-worker-" + str(attempt + 1)))
            with self.store.db() as db:
                db.execute(
                    "UPDATE jobs SET retry_after=? WHERE id=?",
                    ("2000-01-01T00:00:00+00:00", job["id"]),
                )
            claimed = self.store.claim("retry-worker-" + str(attempt + 1))
            self.assertEqual(claimed["attempt_count"], attempt + 1)
            self.assertEqual(claimed["checkpoint"]["step"], "safe-boundary-" + str(attempt))

        self.store.checkpoint(
            job["id"], "retry-worker-3", 3,
            {"version": 1, "step": "ready-to-finish", "safe_to_resume": True,
             "data": {"outcome": "succeeded", "result": {"done": False}}},
        )
        with self.store.db() as db:
            db.execute(
                "UPDATE jobs SET lease_until=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", job["id"]),
            )
        recovered = self.store.recover_expired_leases()
        self.assertEqual(recovered[0]["id"], job["id"])
        self.assertEqual(recovered[0]["state"], "failed")
        final = self.store.get(job["id"])
        self.assertEqual(final["state"], "failed")
        self.assertEqual(final["error_code"], "LEASE_EXPIRED")
        self.assertEqual(final["attempt_count"], 3)
        self.assertEqual(final["last_worker"], "retry-worker-3")
        self.assertIsNone(self.store.claim("retry-worker-4"))
        events = self.store.events(job["id"])
        self.assertEqual(
            [event["event"] for event in events].count("lease_expired_retry_wait"), 2
        )
        self.assertEqual(
            [event["event"] for event in events].count("lease_expired_failed"), 1
        )
        failed_event = next(event for event in events if event["event"] == "lease_expired_failed")
        self.assertEqual(failed_event["detail"]["worker"], "retry-worker-3")
        self.assertEqual(failed_event["detail"]["attempt_count"], 3)

    def test_checkpoint_is_monotonic_idempotent_and_lease_bound(self):
        job, _ = self.create("job-checkpoint-0001")
        self.store.claim("checkpoint-worker")
        checkpoint = {
            "version": 1, "step": "inventory-complete",
            "safe_to_resume": True, "data": {"files_seen": 12},
        }
        saved = self.store.checkpoint(job["id"], "checkpoint-worker", 1, checkpoint)
        self.assertEqual(saved["checkpoint_seq"], 1)
        self.assertEqual(saved["checkpoint"], checkpoint)
        replay = self.store.checkpoint(job["id"], "checkpoint-worker", 1, checkpoint)
        self.assertEqual(replay["checkpoint_sha256"], saved["checkpoint_sha256"])
        with self.assertRaises(JobConflict):
            self.store.checkpoint(
                job["id"], "checkpoint-worker", 1,
                {**checkpoint, "data": {"files_seen": 13}},
            )
        with self.assertRaises(JobConflict):
            self.store.checkpoint(job["id"], "checkpoint-worker", 3, checkpoint)
        with self.assertRaises(ValueError):
            self.store.checkpoint(
                job["id"], "checkpoint-worker", 2,
                {"version": 1, "step": "bad", "safe_to_resume": True,
                 "data": {"api_token": "must-not-be-stored"}},
            )
        self.assertEqual(self.store.get(job["id"])["checkpoint_seq"], 1)

    def test_unsafe_or_missing_checkpoint_requires_owner_reconciliation(self):
        job, _ = self.create("job-unsafe-checkpoint-01")
        self.store.claim("unsafe-worker")
        self.store.checkpoint(
            job["id"], "unsafe-worker", 1,
            {"version": 1, "step": "external-side-effect", "safe_to_resume": False, "data": {}},
        )
        with self.store.db() as db:
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?",
                       ("2000-01-01T00:00:00+00:00", job["id"]))
        recovered = self.store.recover_expired_leases()
        self.assertEqual(recovered[0]["state"], "unknown")
        with self.assertRaises(JobConflict):
            self.store.resume_unknown(job["id"], "owner@example.test")
        self.assertEqual(self.store.get(job["id"])["state"], "unknown")

    def test_nonterminal_checkpoint_is_not_automatically_replayed(self):
        job, _ = self.create("job-nonterminal-checkpoint-01")
        self.store.claim("nonterminal-worker")
        self.store.checkpoint(
            job["id"], "nonterminal-worker", 1,
            {"version": 1, "step": "source-materialized", "safe_to_resume": True,
             "data": {"source_sha256": "a" * 64}},
        )
        with self.store.db() as db:
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?",
                       ("2000-01-01T00:00:00+00:00", job["id"]))
        recovered = self.store.recover_expired_leases()
        self.assertEqual(recovered[0]["state"], "unknown")
        self.assertEqual(self.store.get(job["id"])["error_code"], "OUTCOME_UNKNOWN")

    def test_checkpoint_rejects_wrong_worker_and_expired_lease(self):
        job, _ = self.create("job-checkpoint-fence-01")
        self.store.claim("right-worker")
        checkpoint = {"version": 1, "step": "safe", "safe_to_resume": True, "data": {}}
        with self.assertRaises(JobConflict):
            self.store.checkpoint(job["id"], "wrong-worker", 1, checkpoint)
        with self.store.db() as db:
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?",
                       ("2000-01-01T00:00:00+00:00", job["id"]))
        with self.assertRaises(JobConflict):
            self.store.checkpoint(job["id"], "right-worker", 1, checkpoint)

    def test_resume_unknown_requires_state_and_attempt_budget(self):
        job, _ = self.create("job-resume-unknown-01")
        with self.assertRaises(JobConflict):
            self.store.resume_unknown(job["id"], "owner@example.test")
        self.store.claim("resume-worker")
        with self.store.db() as db:
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?",
                       ("2000-01-01T00:00:00+00:00", job["id"]))
        self.store.recover_expired_leases()
        with self.assertRaises(ValueError):
            self.store.resume_unknown(job["id"], "../not-owner")
        resumed = self.store.resume_unknown(job["id"], "owner@example.test")
        self.assertEqual(resumed["state"], "queued")
        self.assertIsNone(resumed["retry_after"])

    def test_concurrent_workers_cannot_claim_the_same_job(self):
        import threading

        job, _ = self.create("job-concurrent-claim-01")
        second_store = JobStore(self.store.path)
        barrier = threading.Barrier(3)
        results = []
        lock = threading.Lock()

        def claim(store, worker):
            barrier.wait()
            result = store.claim(worker)
            with lock:
                results.append(result)

        threads = [
            threading.Thread(target=claim, args=(self.store, "claim-worker-1")),
            threading.Thread(target=claim, args=(second_store, "claim-worker-2")),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

        claimed = [item for item in results if item is not None]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["id"], job["id"])
        self.assertEqual(self.store.get(job["id"])["state"], "running")

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
        self.assertEqual(recovered, [{"id": job["id"], "state": "cancelled", "retry_after": None}])
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
