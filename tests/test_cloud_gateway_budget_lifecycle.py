"""Live-budget guard and expired-lease reconciliation tests (no cloud calls)."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.cloud_gateway.budget_guard import AzureBudgetGuard
from tools.cloud_gateway.policy import GatewaySettings, PROFILES
from tools.cloud_gateway.service import GatewayService
from tools.cloud_gateway.store import RunnerStore
from tools.runner_backend.provider import RunnerInstance


REPOSITORY = "phakphum12345/generated-A4-pdf"


class Snapshot:
    def __init__(self, permitted):
        self.permitted = permitted

    def permits(self, projected):
        return self.permitted and projected >= 0


class Reader:
    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot
        self.error = error
        self.calls = 0

    def read(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.snapshot


class Provider:
    def __init__(self):
        self.calls = []

    def provision(self, payload):
        self.calls.append(("provision", payload))
        return RunnerInstance("provider-1", "provisioning", "runner-1", tuple(payload["labels"]))

    def status(self, provider_id):
        self.calls.append(("status", provider_id))
        return RunnerInstance(provider_id, "online")

    def terminate(self, provider_id):
        self.calls.append(("terminate", provider_id))
        return RunnerInstance(provider_id, "terminated")


def request_payload():
    profile = PROFILES["linux"]
    return {
        "repository": REPOSITORY, "workflow_run_id": 99, "commit_sha": "a" * 40,
        "target_os": "linux", "image": profile["image"], "labels": profile["labels"],
        "ephemeral": True, "max_runtime_minutes": 30,
        "network_policy": "restricted-egress",
        "registration_token_handling": "provider-side-only",
    }


def settings():
    return GatewaySettings(
        provisioning_enabled=True, owner_approved=True,
        allowed_repositories=(REPOSITORY,), budget_limit_usd=100,
        current_spend_usd=0, projected_run_cost_usd=1,
        max_concurrent_runners=2, max_runtime_minutes=180,
    )


class BudgetGuardTests(unittest.TestCase):
    def test_reads_live_budget_for_each_authorization(self):
        reader = Reader(Snapshot(True))
        guard = AzureBudgetGuard(reader, 2.5)
        guard.authorize(0)
        guard.authorize(1)
        self.assertEqual(reader.calls, 2)

    def test_projection_includes_every_active_runner_and_new_runner(self):
        class RecordingSnapshot:
            def __init__(self):
                self.projected = []
            def permits(self, projected):
                self.projected.append(projected)
                return projected <= 25
        snapshot = RecordingSnapshot()
        guard = AzureBudgetGuard(Reader(snapshot), 10)
        guard.authorize(1)
        with self.assertRaisesRegex(Exception, "budget or forecast ceiling"):
            guard.authorize(2)
        self.assertEqual(snapshot.projected, [20, 30])

    def test_nonfinite_projected_run_cost_is_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                AzureBudgetGuard(Reader(Snapshot(True)), value)

    def test_denies_when_budget_reader_is_unavailable(self):
        guard = AzureBudgetGuard(Reader(error=RuntimeError("private endpoint")), 1)
        with self.assertRaisesRegex(Exception, "Live Azure budget is unavailable"):
            guard.authorize(0)

    def test_denies_when_snapshot_exceeds_ceiling(self):
        guard = AzureBudgetGuard(Reader(Snapshot(False)), 1)
        with self.assertRaisesRegex(Exception, "budget or forecast ceiling"):
            guard.authorize(0)

    def test_gateway_checks_live_budget_before_provider(self):
        reader = Reader(Snapshot(False))
        provider = Provider()
        with tempfile.TemporaryDirectory() as temp:
            service = GatewayService(
                settings(), RunnerStore(str(Path(temp) / "gateway.sqlite")),
                provider, AzureBudgetGuard(reader, 2),
            )
            with self.assertRaises(Exception):
                service.create(request_payload(), "budget-key-001")
        self.assertEqual(provider.calls, [])
        self.assertEqual(reader.calls, 1)


class ExpiryReconciliationTests(unittest.TestCase):
    def test_expired_online_runner_is_terminated_and_audited(self):
        provider = Provider()
        with tempfile.TemporaryDirectory() as temp:
            store = RunnerStore(str(Path(temp) / "gateway.sqlite"))
            service = GatewayService(settings(), store, provider)
            row, created = service.create(request_payload(), "expiry-key-001")
            self.assertTrue(created)
            expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            with store.db() as db:
                db.execute("UPDATE runners SET expires_at=? WHERE id=?", (expired, row["id"]))
            result = service.reconcile_expired()
            self.assertEqual(result, [{"id": row["id"], "state": "terminated"}])
            self.assertEqual(store.get(row["id"])["state"], "terminated")
            self.assertIn(("terminate", "provider-1"), provider.calls)
            self.assertEqual(service.reconcile_expired(), [])

    def test_cleanup_failure_remains_retryable(self):
        class FailingProvider(Provider):
            def terminate(self, provider_id):
                raise RuntimeError("secret must not be logged")

        with tempfile.TemporaryDirectory() as temp:
            store = RunnerStore(str(Path(temp) / "gateway.sqlite"))
            service = GatewayService(settings(), store, FailingProvider())
            row, _ = service.create(request_payload(), "expiry-key-002")
            expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            with store.db() as db:
                db.execute("UPDATE runners SET expires_at=? WHERE id=?", (expired, row["id"]))
            self.assertEqual(
                service.reconcile_expired(),
                [{"id": row["id"], "state": "cleanup_pending"}],
            )
            self.assertEqual(store.get(row["id"])["state"], "terminating")
            self.assertEqual(len(store.expired_active(datetime.now(timezone.utc).isoformat())), 1)

    def test_naive_reconciliation_time_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            service = GatewayService(settings(), RunnerStore(str(Path(temp) / "db")), Provider())
            with self.assertRaises(ValueError):
                service.reconcile_expired(datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
