"""Tests for explicit, fail-closed Azure provider composition."""
import base64
import unittest
from types import SimpleNamespace

from tools.cloud_gateway.azure_provider_runtime import build_azure_provider_runtime
from tools.cloud_gateway.azure_vm import AzureVMProvider


SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
NETWORK_RG = "dcp-network"


def resource(kind, name):
    return (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{NETWORK_RG}"
        f"/providers/Microsoft.Network/{kind}/{name}"
    )


def ssh_key():
    key_type = b"ssh-ed25519"
    wire = len(key_type).to_bytes(4, "big") + key_type + (32).to_bytes(4, "big") + b"\x01" * 32
    return "ssh-ed25519 " + base64.b64encode(wire).decode("ascii") + " dcp-test"


def environment():
    return {
        "DCP_AZURE_PROVIDER_ENABLED": "true",
        "DCP_AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
        "DCP_AZURE_RESOURCE_GROUP": "dcp-runners",
        "DCP_AZURE_LOCATION": "eastus",
        "DCP_AZURE_SUBNET_ID": resource("virtualNetworks", "vnet") + "/subnets/runners",
        "DCP_AZURE_NSG_ID": resource("networkSecurityGroups", "runner-nsg"),
        "DCP_AZURE_ROUTE_TABLE_ID": resource("routeTables", "runner-rt"),
        "DCP_AZURE_FIREWALL_ID": resource("azureFirewalls", "runner-fw"),
        "DCP_AZURE_FIREWALL_POLICY_ID": resource("firewallPolicies", "runner-policy"),
        "DCP_AZURE_BUDGET_NAME": "dcp-monthly",
        "DCP_AZURE_PROJECTED_RUN_COST_USD": "1.25",
        "DCP_AZURE_LINUX_VM_SIZE": "Standard_D2s_v5",
        "DCP_AZURE_WINDOWS_VM_SIZE": "Standard_D4s_v5",
        "DCP_AZURE_LINUX_IMAGE_PUBLISHER": "Canonical",
        "DCP_AZURE_LINUX_IMAGE_OFFER": "ubuntu-24_04-lts",
        "DCP_AZURE_LINUX_IMAGE_SKU": "server",
        "DCP_AZURE_LINUX_IMAGE_VERSION": "24.04.202501010",
        "DCP_AZURE_WINDOWS_IMAGE_PUBLISHER": "MicrosoftWindowsServer",
        "DCP_AZURE_WINDOWS_IMAGE_OFFER": "WindowsServer",
        "DCP_AZURE_WINDOWS_IMAGE_SKU": "2025-datacenter-g2",
        "DCP_AZURE_WINDOWS_IMAGE_VERSION": "2025.01.15",
        "DCP_RUNNER_VERSION": "2.331.0",
        "DCP_RUNNER_LINUX_SHA256": "a" * 64,
        "DCP_RUNNER_WINDOWS_SHA256": "b" * 64,
        "DCP_AZURE_GUEST_ADMIN_USERNAME": "dcpadmin",
        "DCP_AZURE_LINUX_SSH_PUBLIC_KEY": ssh_key(),
    }


class FakeArm:
    subscription_id = SUBSCRIPTION
    resource_group = "dcp-runners"


class AzureProviderRuntimeTests(unittest.TestCase):
    def factories(self):
        seen = {}
        def credential_factory(env=None):
            seen["credential_env"] = env
            return object()
        def arm_factory(subscription, resource_group, credential):
            seen["arm_args"] = (subscription, resource_group, credential)
            seen["arm"] = FakeArm()
            return seen["arm"]
        def egress_factory(arm, env):
            seen["egress_args"] = (arm, env)
            return lambda os_name, subnet_id, nsg_id: True
        return seen, credential_factory, arm_factory, egress_factory

    def test_provider_is_disabled_without_explicit_opt_in(self):
        settings = SimpleNamespace(provisioning_enabled=False)
        seen, credential, arm, egress = self.factories()
        self.assertIsNone(build_azure_provider_runtime(
            settings, None, None, None, env={}, credential_factory=credential,
            arm_factory=arm, egress_factory=egress,
        ))
        self.assertEqual(seen, {})

    def test_global_provisioning_cannot_run_with_provider_disabled(self):
        settings = SimpleNamespace(provisioning_enabled=True)
        with self.assertRaises(ValueError):
            build_azure_provider_runtime(settings, None, None, None, env={})

    def test_enabled_provider_requires_complete_config_and_all_independent_guards(self):
        settings = SimpleNamespace(provisioning_enabled=False)
        budget = SimpleNamespace(authorize=lambda active_count: None)
        app = SimpleNamespace(create_registration_token=lambda repository: None)
        with self.assertRaises(ValueError):
            build_azure_provider_runtime(settings, app, lambda: True, object(), env=environment())
        with self.assertRaises(ValueError):
            build_azure_provider_runtime(settings, None, None, budget, env=environment())
        with self.assertRaises(ValueError):
            build_azure_provider_runtime(settings, app, lambda: True, None, env=environment())
        incomplete = environment()
        incomplete.pop("DCP_AZURE_FIREWALL_POLICY_ID")
        with self.assertRaises(ValueError):
            build_azure_provider_runtime(
                settings, app, lambda: True, budget, env=incomplete,
            )
        with self.assertRaises(ValueError):
            build_azure_provider_runtime(
                settings, app, lambda: True, budget, env=environment(),
                credential_factory=credential, arm_factory=arm,
                egress_factory=lambda arm, env: None,
            )


    def test_composes_real_provider_with_pinned_images_and_live_network_checker(self):
        settings = SimpleNamespace(provisioning_enabled=False)
        seen, credential, arm, egress = self.factories()
        budget = SimpleNamespace(authorize=lambda active_count: None)
        app = SimpleNamespace(create_registration_token=lambda repository: None)
        online = lambda *args: True
        values = environment()
        provider = build_azure_provider_runtime(
            settings, app, online, budget, env=values,
            credential_factory=credential, arm_factory=arm, egress_factory=egress,
        )
        self.assertIsInstance(provider, AzureVMProvider)
        self.assertEqual(provider.vm_sizes, {
            "linux": "Standard_D2s_v5", "windows": "Standard_D4s_v5",
        })
        self.assertEqual(provider.image_references["linux"]["version"], "24.04.202501010")
        self.assertEqual(provider.image_references["windows"]["version"], "2025.01.15")
        self.assertTrue(provider.readiness("linux")["ready"])
        self.assertTrue(provider.readiness("windows")["ready"])
        self.assertIs(seen["credential_env"], values)
        self.assertEqual(seen["arm_args"][:2], (SUBSCRIPTION, "dcp-runners"))
        self.assertIs(seen["egress_args"][0], seen["arm"])
        self.assertEqual(provider.bootstrap_factory.runner_version, "2.331.0")
        self.assertEqual(provider.bootstrap_factory.os_profile_factory.admin_username, "dcpadmin")

    def test_rejects_invalid_provider_opt_in_or_guest_profile(self):
        settings = SimpleNamespace(provisioning_enabled=False)
        values = environment()
        values["DCP_AZURE_PROVIDER_ENABLED"] = "sometimes"
        with self.assertRaises(ValueError):
            build_azure_provider_runtime(
                settings, SimpleNamespace(create_registration_token=lambda repository: None), lambda: True,
                SimpleNamespace(authorize=lambda _: None), env=values,
            )
        values = environment()
        values["DCP_AZURE_LINUX_SSH_PUBLIC_KEY"] = "ssh-rsa invalid"
        with self.assertRaises(ValueError):
            build_azure_provider_runtime(
                settings, object(), lambda: True,
                SimpleNamespace(authorize=lambda _: None), env=values,
            )


if __name__ == "__main__":
    unittest.main()
