"""Provider-scoped budget isolation tests; no live provider calls."""
import tempfile
import unittest
from pathlib import Path

from tools.cloud_gateway.budget_guard import AzureBudgetGuard, ProviderBudgetGuard
from tools.cloud_gateway.policy import GatewaySettings, PolicyDenied, PROFILES
from tools.cloud_gateway.provider_router import ProviderRouter
from tools.cloud_gateway.service import GatewayService
from tools.cloud_gateway.store import RunnerStore
from tools.runner_backend.provider import RunnerInstance


REPOSITORY = "phakphum12345/generated-A4-pdf"


class Snapshot:
    def __init__(self, provider, permitted=True):
        self.provider = provider
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


class RoutedProvider:
    requires_budget_guard = True
    requires_runner_cleanup = False
    budget_provider = "orka"

    def __init__(self):
        self.calls = []

    def readiness(self, os_name):
        return {"ready": True, "message": "test provider ready"}

    def provision(self, payload):
        self.calls.append(payload)
        return RunnerInstance(
            "orka:dcp-123-abcdef12", "provisioning",
            "dcp-123-abcdef12", tuple(payload["labels"]),
        )


def settings():
    return GatewaySettings(
        provisioning_enabled=True,
        owner_approved=True,
        allowed_repositories=(REPOSITORY,),
        budget_limit_usd=100,
        current_spend_usd=0,
        projected_run_cost_usd=1,
        max_concurrent_runners=2,
        max_runtime_minutes=180,
    )


def macos_payload():
    profile = PROFILES["macos"]
    return {
        "repository": REPOSITORY,
        "workflow_run_id": 123,
        "commit_sha": "a" * 40,
        "target_os": "macos",
        "image": profile["image"],
        "labels": profile["labels"],
        "ephemeral": True,
        "max_runtime_minutes": 30,
        "network_policy": "restricted-egress",
        "registration_token_handling": "provider-side-only",
    }


class ProviderBudgetGuardTests(unittest.TestCase):
    def test_provider_guard_requires_matching_snapshot_identity(self):
        guard = ProviderBudgetGuard("orka", Reader(Snapshot("orka")), 2)
        guard.authorize(1)

        wrong_source = ProviderBudgetGuard(
            "orka", Reader(Snapshot("azure")), 2
        )
        with self.assertRaisesRegex(PolicyDenied, "unavailable"):
            wrong_source.authorize(0)

    def test_provider_guard_fails_closed_on_reader_error_and_budget_denial(self):
        unavailable = ProviderBudgetGuard(
            "orka", Reader(error=RuntimeError("private billing endpoint")), 1
        )
        with self.assertRaisesRegex(PolicyDenied, "unavailable"):
            unavailable.authorize(0)

        over_budget = ProviderBudgetGuard(
            "orka", Reader(Snapshot("orka", permitted=False)), 1
        )
        with self.assertRaisesRegex(PolicyDenied, "budget or forecast"):
            over_budget.authorize(0)

    def test_provider_guard_rejects_invalid_cost_and_active_count(self):
        for cost in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(cost=cost), self.assertRaises(ValueError):
                ProviderBudgetGuard("orka", Reader(Snapshot("orka")), cost)
        guard = ProviderBudgetGuard("orka", Reader(Snapshot("orka")), 1)
        for count in (-1, True, 1.5):
            with self.subTest(count=count), self.assertRaises(PolicyDenied):
                guard.authorize(count)

    def test_azure_budget_guard_cannot_authorize_orka_runner(self):
        provider = RoutedProvider()
        azure_guard = AzureBudgetGuard(Reader(Snapshot("azure")), 1)
        with tempfile.TemporaryDirectory() as temp:
            service = GatewayService(
                settings(),
                RunnerStore(str(Path(temp) / "gateway.sqlite")),
                provider,
                budget_guard=azure_guard,
            )
            with self.assertRaisesRegex(
                PolicyDenied, "provider-specific budget guard"
            ):
                service.create(macos_payload(), "orka-no-azure-fallback")
        self.assertEqual(provider.calls, [])

    def test_orka_runner_uses_only_orka_budget_guard(self):
        provider = RoutedProvider()
        orka_reader = Reader(Snapshot("orka", permitted=True))
        orka_guard = ProviderBudgetGuard("orka", orka_reader, 2)
        azure_reader = Reader(Snapshot("azure", permitted=False))
        azure_guard = AzureBudgetGuard(azure_reader, 50)
        with tempfile.TemporaryDirectory() as temp:
            service = GatewayService(
                settings(),
                RunnerStore(str(Path(temp) / "gateway.sqlite")),
                provider,
                budget_guard=azure_guard,
                provider_budget_guards={"orka": orka_guard},
            )
            row, created = service.create(
                macos_payload(), "orka-provider-budget-key"
            )
        self.assertTrue(created)
        self.assertEqual(row["state"], "provisioning")
        self.assertEqual(orka_reader.calls, 1)
        self.assertEqual(azure_reader.calls, 0)
        self.assertEqual(len(provider.calls), 1)

    def test_provider_router_exposes_distinct_budget_scopes(self):
        router = ProviderRouter(RoutedProvider(), RoutedProvider())
        self.assertEqual(router.budget_provider_for_os("linux"), "azure")
        self.assertEqual(router.budget_provider_for_os("windows"), "azure")
        self.assertEqual(router.budget_provider_for_os("macos"), "orka")


if __name__ == "__main__":
    unittest.main()
