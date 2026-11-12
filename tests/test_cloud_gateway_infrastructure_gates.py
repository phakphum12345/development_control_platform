"""Persistent independent infrastructure gate tests."""
import tempfile
import unittest
from pathlib import Path

from tools.cloud_gateway.infrastructure_gates import (
    GateUnavailable,
    InfrastructureGateError,
    InfrastructureGateStore,
)


class InfrastructureGateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "gates.sqlite"
        self.store = InfrastructureGateStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_both_gates_start_off_and_are_independent(self):
        status = self.store.status({
            "cloud_provisioning": True,
            "vm_creation": False,
        })
        self.assertFalse(status["cloud_provisioning"]["enabled"])
        self.assertFalse(status["vm_creation"]["enabled"])
        self.assertTrue(status["cloud_provisioning"]["ready"])
        self.assertFalse(status["cloud_provisioning"]["effective_enabled"])

    def test_enable_requires_exact_confirmation_and_ready_capability(self):
        with self.assertRaises(InfrastructureGateError):
            self.store.set_enabled(
                "cloud_provisioning", True, "owner", "ENABLE", True
            )
        with self.assertRaises(GateUnavailable):
            self.store.set_enabled(
                "cloud_provisioning", True, "owner",
                "ENABLE CLOUD PROVISIONING", False,
            )

    def test_gate_switches_are_independent_and_audited(self):
        cloud = self.store.set_enabled(
            "cloud_provisioning", True, "owner",
            "ENABLE CLOUD PROVISIONING", True,
        )
        self.assertTrue(cloud["enabled"])
        self.assertTrue(cloud["effective_enabled"])
        vm = self.store.set_enabled(
            "vm_creation", False, "owner", "", False,
        )
        self.assertFalse(vm["enabled"])
        status = self.store.status({
            "cloud_provisioning": True, "vm_creation": True,
        })
        self.assertTrue(status["cloud_provisioning"]["effective_enabled"])
        self.assertFalse(status["vm_creation"]["effective_enabled"])
        self.assertEqual(len(self.store.events()), 2)

    def test_state_and_audit_survive_reopen(self):
        self.store.set_enabled(
            "vm_creation", True, "owner", "ENABLE VM CREATION", True,
        )
        reopened = InfrastructureGateStore(self.path)
        status = reopened.status({"vm_creation": True})
        self.assertTrue(status["vm_creation"]["enabled"])
        self.assertTrue(status["vm_creation"]["effective_enabled"])
        self.assertEqual(reopened.events("vm_creation")[0]["actor"], "owner")

    def test_invalid_gate_value_and_actor_are_rejected(self):
        with self.assertRaises(InfrastructureGateError):
            self.store.set_enabled("other", False, "owner")
        with self.assertRaises(InfrastructureGateError):
            self.store.set_enabled("vm_creation", 1, "owner")
        with self.assertRaises(InfrastructureGateError):
            self.store.set_enabled("vm_creation", False, "")


if __name__ == "__main__":
    unittest.main()
