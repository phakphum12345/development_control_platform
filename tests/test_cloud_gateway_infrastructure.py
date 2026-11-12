"""Contract tests for DCP Infrastructure Manager; fake provider only."""
import tempfile
import unittest
from pathlib import Path

from tools.cloud_gateway.infrastructure import (
    FakeInfrastructureProvider, InfrastructureManager, InfrastructureStore,
    LifecycleConflict, ResourceNotFound,
)


class InfrastructureManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = FakeInfrastructureProvider()
        self.database = Path(self.temp.name) / "infra.sqlite3"
        self.store = InfrastructureStore(self.database)
        self.manager = InfrastructureManager(self.store, {"fake": self.provider})

    def tearDown(self):
        self.temp.cleanup()

    def create(self, key="infra-create-0001"):
        return self.manager.create(target_os="linux",
            image_id="dcp-linux-ubuntu-24.04", template_id="flutter-linux-small",
            idempotency_key=key)

    def assert_provider_and_inventory_state(self, row, expected_state):
        inventory = self.manager.get(row["id"])
        provider = self.provider.resources[row["provider_resource_id"]]
        self.assertEqual(inventory["state"], expected_state)
        self.assertEqual(provider["state"], expected_state)
        observed = self.manager.inspect(row["id"])
        self.assertEqual(observed["state"], expected_state)
        self.assertEqual(self.provider.resources[row["provider_resource_id"]]["state"],
                         expected_state)

    def test_catalog_is_provider_neutral_and_external_provisioning_disabled(self):
        catalog = self.manager.catalog()
        self.assertEqual(catalog["providers"][0]["id"], "fake")
        self.assertFalse(catalog["provisioning_enabled"])
        self.assertEqual(len(catalog["images"]), 3)
        self.assertEqual(len(catalog["templates"]), 3)

    def test_fake_lifecycle_keeps_provider_inventory_and_audit_in_sync(self):
        row, created = self.create()
        self.assertTrue(created)
        self.assertEqual(row["state"], "provisioned")
        resource_id = row["id"]
        self.assert_provider_and_inventory_state(row, "provisioned")

        row = self.manager.start(resource_id)
        self.assert_provider_and_inventory_state(row, "running")

        row = self.manager.stop(resource_id)
        self.assert_provider_and_inventory_state(row, "stopped")

        row = self.manager.restart(resource_id)
        self.assert_provider_and_inventory_state(row, "running")

        row = self.manager.delete(resource_id)
        self.assert_provider_and_inventory_state(row, "deleted")
        calls_before_repeat_delete = list(self.provider.calls)
        self.assertEqual(self.manager.delete(resource_id)["state"], "deleted")
        self.assertEqual(self.provider.calls, calls_before_repeat_delete)

        events = [event["event"] for event in self.store.events(resource_id)]
        self.assertEqual(events, [
            "resource_created", "running", "stopped", "running", "deleted"
        ])

        reopened_store = InfrastructureStore(self.database)
        persisted = reopened_store.get(resource_id)
        self.assertEqual(persisted["state"], "deleted")
        self.assertEqual(
            [event["event"] for event in reopened_store.events(resource_id)], events
        )

    def test_idempotency_returns_existing_without_second_provider_create(self):
        first, created = self.create()
        second, created_again = self.create()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual([c[0] for c in self.provider.calls].count("create"), 1)

    def test_idempotency_key_cannot_be_reused_for_different_request(self):
        self.create()
        with self.assertRaises(LifecycleConflict):
            self.manager.create(target_os="windows", image_id="dcp-windows-2025",
                template_id="flutter-windows-small", idempotency_key="infra-create-0001")

    def test_image_and_template_os_must_match(self):
        with self.assertRaisesRegex(ValueError, "match target OS"):
            self.manager.create(target_os="linux", image_id="dcp-linux-ubuntu-24.04",
                template_id="flutter-windows-small", idempotency_key="infra-mismatch-001")

    def test_invalid_transitions_are_rejected_before_provider_side_effects(self):
        row, _ = self.create()
        calls_before = list(self.provider.calls)
        with self.assertRaises(LifecycleConflict):
            self.manager.stop(row["id"])
        self.assertEqual(self.provider.calls, calls_before)
        provider_row = self.provider.resources[row["provider_resource_id"]]
        self.assertEqual(provider_row["state"], "provisioned")
        self.assertEqual(self.manager.get(row["id"])["state"], "provisioned")

        self.manager.delete(row["id"])
        calls_after_delete = list(self.provider.calls)
        with self.assertRaises(LifecycleConflict):
            self.manager.start(row["id"])
        self.assertEqual(self.provider.calls, calls_after_delete)

    def test_unknown_resource_is_not_silently_accepted(self):
        with self.assertRaises(ResourceNotFound):
            self.manager.inspect("missing-resource")

    def test_external_provider_fails_closed_when_provisioning_disabled(self):
        class External(FakeInfrastructureProvider):
            provider_id = "external"
        external = External()
        manager = InfrastructureManager(self.store, {"external": external},
                                        default_provider="external", provisioning_enabled=False)
        with self.assertRaisesRegex(Exception, "disabled"):
            manager.create(target_os="linux", image_id="dcp-linux-ubuntu-24.04",
                template_id="flutter-linux-small", idempotency_key="external-create-001")
        self.assertEqual(external.calls, [])


if __name__ == "__main__":
    unittest.main()
