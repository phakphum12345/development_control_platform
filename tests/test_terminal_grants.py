"""Durable one-time Terminal authorization grant tests."""
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
import uuid
from pathlib import Path

from tools.cloud_gateway.terminal_grants import TerminalGrantError, TerminalGrantStore


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


class TerminalGrantStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "grants.sqlite3"
        self.store = TerminalGrantStore(self.path)
        self.project = str(uuid.uuid4())
        self.workspace = str(uuid.uuid4())
        self.job = str(uuid.uuid4())
        self.claims = {
            "subject": "owner@example.test",
            "session_id": "session_token_1234567890",
            "project_id": self.project,
            "workspace_id": self.workspace,
            "snapshot_sha256": "a" * 64,
            "template_id": "git_status",
            "template_digest": "b" * 64,
            "parameters_sha256": "c" * 64,
            "action": "terminal.read_only",
        }

    def tearDown(self):
        self.temp.cleanup()

    def issue(self, *, ttl=120, now=NOW, action="terminal.read_only"):
        claims = {**self.claims, "action": action}
        return self.store.issue(**claims, ttl_seconds=ttl, now=now)

    def bind(self, grant, *, job_id=None, worker="runner-local", now=NOW):
        return self.store.bind_job(
            grant["authorization_id"], job_id=job_id or self.job,
            worker_id=worker, now=now,
        )

    def consume(self, grant, **overrides):
        args = {
            "job_id": self.job, "worker_id": "runner-local",
            **self.claims, "now": NOW,
        }
        args.update(overrides)
        return self.store.consume(grant["authorization_id"], **args)

    def test_grant_is_durable_and_consumable_only_once(self):
        grant = self.issue()
        self.bind(grant)
        self.store = TerminalGrantStore(self.path)
        self.assertTrue(self.consume(grant)["authorized"])
        with self.assertRaisesRegex(TerminalGrantError, "not active"):
            self.consume(grant)

    def test_grant_cannot_be_bound_to_a_second_job_or_runner(self):
        grant = self.issue()
        self.bind(grant)
        with self.assertRaisesRegex(TerminalGrantError, "already bound"):
            self.bind(grant, job_id=str(uuid.uuid4()), worker="runner-other")

    def test_scope_mismatches_are_rejected(self):
        cases = (
            ("subject", "different-user"),
            ("session_id", "different_session_123456"),
            ("project_id", str(uuid.uuid4())),
            ("workspace_id", str(uuid.uuid4())),
            ("snapshot_sha256", "d" * 64),
            ("template_id", "git_diff"),
            ("template_digest", "e" * 64),
            ("parameters_sha256", "f" * 64),
            ("action", "terminal.modify"),
        )
        for field, value in cases:
            with self.subTest(field=field):
                store = TerminalGrantStore(Path(self.temp.name) / (field + ".sqlite3"))
                grant = store.issue(**self.claims, ttl_seconds=120, now=NOW)
                store.bind_job(grant["authorization_id"], job_id=self.job,
                               worker_id="runner-local", now=NOW)
                args = {
                    "job_id": self.job, "worker_id": "runner-local",
                    **self.claims, "now": NOW,
                }
                args[field] = value
                with self.assertRaisesRegex(TerminalGrantError, "scope"):
                    store.consume(grant["authorization_id"], **args)

    def test_wrong_job_or_runner_cannot_consume_grant(self):
        grant = self.issue()
        self.bind(grant)
        with self.assertRaisesRegex(TerminalGrantError, "not bound"):
            self.consume(grant, worker_id="runner-attacker")

    def test_expired_grant_fails_closed(self):
        grant = self.issue(ttl=15)
        self.bind(grant)
        with self.assertRaisesRegex(TerminalGrantError, "not active"):
            self.consume(grant, now=NOW + timedelta(seconds=16))

    def test_revoked_grant_cannot_be_consumed_or_reactivated(self):
        grant = self.issue()
        self.bind(grant)
        self.assertTrue(self.store.revoke(grant["authorization_id"], now=NOW))
        self.assertFalse(self.store.revoke(grant["authorization_id"], now=NOW))
        with self.assertRaisesRegex(TerminalGrantError, "not active"):
            self.consume(grant)

    def test_only_read_only_action_can_be_issued(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.issue(action="terminal.modify")

    def test_parameter_digest_is_canonical(self):
        first = TerminalGrantStore.parameters_digest({"limit": 10, "path": "."})
        second = TerminalGrantStore.parameters_digest({"path": ".", "limit": 10})
        third = TerminalGrantStore.parameters_digest({"limit": 11, "path": "."})
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_invalid_ttl_and_digest_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "TTL"):
            self.issue(ttl=301)
        invalid = dict(self.claims)
        invalid["snapshot_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.store.issue(**invalid, ttl_seconds=120, now=NOW)


if __name__ == "__main__":
    unittest.main()
