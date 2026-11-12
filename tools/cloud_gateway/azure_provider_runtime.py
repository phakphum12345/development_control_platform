"""Fail-closed composition for the real Azure ephemeral runner provider."""
from __future__ import annotations

import os

from .azure_egress import AzureEgressPolicyVerifier
from .azure_guest_profile import AzureGuestProfileFactory
from .azure_identity import ManagedIdentityCredential
from .azure_vm import AzureArmClient, AzureVMProvider
from .runner_bootstrap import AzureRunnerBootstrapFactory


_REQUIRED = (
    "DCP_AZURE_SUBSCRIPTION_ID",
    "DCP_AZURE_RESOURCE_GROUP",
    "DCP_AZURE_LOCATION",
    "DCP_AZURE_SUBNET_ID",
    "DCP_AZURE_NSG_ID",
    "DCP_AZURE_ROUTE_TABLE_ID",
    "DCP_AZURE_FIREWALL_ID",
    "DCP_AZURE_FIREWALL_POLICY_ID",
    "DCP_AZURE_BUDGET_NAME",
    "DCP_AZURE_PROJECTED_RUN_COST_USD",
    "DCP_AZURE_LINUX_VM_SIZE",
    "DCP_AZURE_WINDOWS_VM_SIZE",
    "DCP_AZURE_LINUX_IMAGE_PUBLISHER",
    "DCP_AZURE_LINUX_IMAGE_OFFER",
    "DCP_AZURE_LINUX_IMAGE_SKU",
    "DCP_AZURE_LINUX_IMAGE_VERSION",
    "DCP_AZURE_WINDOWS_IMAGE_PUBLISHER",
    "DCP_AZURE_WINDOWS_IMAGE_OFFER",
    "DCP_AZURE_WINDOWS_IMAGE_SKU",
    "DCP_AZURE_WINDOWS_IMAGE_VERSION",
    "DCP_RUNNER_VERSION",
    "DCP_RUNNER_LINUX_SHA256",
    "DCP_RUNNER_WINDOWS_SHA256",
    "DCP_AZURE_GUEST_ADMIN_USERNAME",
    "DCP_AZURE_LINUX_SSH_PUBLIC_KEY",
)


def build_azure_provider_runtime(
    settings,
    github_app,
    runner_online_checker,
    budget_guard,
    env=None,
    credential_factory=None,
    arm_factory=None,
    egress_factory=None,
):
    """Return a fully wired Azure provider only after explicit opt-in and config.

    This function never enables Gateway provisioning or owner approval. It
    only composes a provider. Global policy gates and a live budget guard remain
    independently enforced by GatewayService.
    """
    values = os.environ if env is None else env
    raw_enabled = values.get("DCP_AZURE_PROVIDER_ENABLED", "false").strip().lower()
    if raw_enabled not in ("true", "false"):
        raise ValueError("DCP_AZURE_PROVIDER_ENABLED must be true or false")
    enabled = raw_enabled == "true"
    if not enabled:
        if getattr(settings, "provisioning_enabled", False):
            raise ValueError("Gateway provisioning cannot be enabled while the Azure provider is disabled")
        return None

    missing = [name for name in _REQUIRED if not isinstance(values.get(name), str) or not values.get(name).strip()]
    if missing:
        raise ValueError("Azure provider configuration is incomplete: " + ", ".join(missing))
    if github_app is None or not callable(runner_online_checker):
        raise ValueError("A configured GitHub App and independent runner-online checker are required")
    if budget_guard is None or not callable(getattr(budget_guard, "authorize", None)):
        raise ValueError("A live Azure budget guard is required before Azure provider activation")

    credential_factory = credential_factory or ManagedIdentityCredential
    arm_factory = arm_factory or AzureArmClient
    credential = credential_factory(env=values)
    arm = arm_factory(
        values["DCP_AZURE_SUBSCRIPTION_ID"],
        values["DCP_AZURE_RESOURCE_GROUP"],
        credential,
    )
    guest_profile = AzureGuestProfileFactory.from_environment(values)
    bootstrap = AzureRunnerBootstrapFactory(
        github_app,
        values["DCP_RUNNER_VERSION"],
        values["DCP_RUNNER_LINUX_SHA256"],
        values["DCP_RUNNER_WINDOWS_SHA256"],
        guest_profile,
    )
    if egress_factory is None:
        egress = AzureEgressPolicyVerifier.from_environment(arm, values)
    else:
        egress = egress_factory(arm, values)
    if not callable(egress):
        raise ValueError("A live Azure Firewall egress verifier is required")

    vm_sizes = {
        "linux": values["DCP_AZURE_LINUX_VM_SIZE"],
        "windows": values["DCP_AZURE_WINDOWS_VM_SIZE"],
    }
    images = {
        "linux": {
            "publisher": values["DCP_AZURE_LINUX_IMAGE_PUBLISHER"],
            "offer": values["DCP_AZURE_LINUX_IMAGE_OFFER"],
            "sku": values["DCP_AZURE_LINUX_IMAGE_SKU"],
            "version": values["DCP_AZURE_LINUX_IMAGE_VERSION"],
        },
        "windows": {
            "publisher": values["DCP_AZURE_WINDOWS_IMAGE_PUBLISHER"],
            "offer": values["DCP_AZURE_WINDOWS_IMAGE_OFFER"],
            "sku": values["DCP_AZURE_WINDOWS_IMAGE_SKU"],
            "version": values["DCP_AZURE_WINDOWS_IMAGE_VERSION"],
        },
    }
    return AzureVMProvider(
        arm,
        values["DCP_AZURE_LOCATION"],
        values["DCP_AZURE_SUBNET_ID"],
        values["DCP_AZURE_NSG_ID"],
        vm_sizes,
        images,
        bootstrap,
        runner_online_checker,
        egress,
    )
