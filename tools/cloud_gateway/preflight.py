"""Redacted, read-only deployment preflight for the DCP Cloud Gateway.

This command inspects configuration presence only. It never reads secret values,
contacts cloud APIs, starts services, or provisions infrastructure.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from urllib.parse import urlparse


def _present(env: Mapping[str, str], name: str) -> bool:
    value = env.get(name, "")
    return isinstance(value, str) and bool(value.strip())


def _https_origin(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment
    )


def inspect_environment(env: Mapping[str, str] | None = None) -> dict:
    """Return status-only evidence; never echo configured values."""
    values = os.environ if env is None else env
    checks: list[dict[str, str]] = []

    def add(name: str, passed: bool, detail: str, status: str | None = None) -> None:
        checks.append({
            "check": name,
            "status": status or ("PASS" if passed else "UNKNOWN"),
            "detail": detail,
        })

    add(
        "gateway_api_token",
        _present(values, "DCP_GATEWAY_API_TOKEN"),
        "Server-to-server bearer token is configured" if _present(values, "DCP_GATEWAY_API_TOKEN")
        else "DCP_GATEWAY_API_TOKEN is missing",
    )
    proxy_secret = values.get("DCP_TRUSTED_PROXY_HMAC_SECRET", "")
    proxy_origin = values.get("DCP_PUBLIC_ORIGIN", "")
    proxy_ok = len(proxy_secret) >= 32 and _https_origin(proxy_origin)
    add(
        "trusted_proxy",
        proxy_ok,
        "Trusted proxy HMAC and HTTPS origin are configured" if proxy_ok
        else "Requires a 32+ character HMAC secret and an HTTPS origin",
    )

    enabled = values.get("DCP_GATEWAY_PROVISIONING_ENABLED", "false").lower() == "true"
    approved = values.get("DCP_GATEWAY_OWNER_APPROVED", "false").lower() == "true"
    repositories = tuple(x.strip() for x in values.get("DCP_GATEWAY_ALLOWED_REPOSITORIES", "").split(",") if x.strip())
    allowlist_ok = bool(repositories) and len(set(repositories)) == len(repositories) and all(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", item) for item in repositories
    )
    add("provisioning_disabled_by_default", not enabled,
        "Provisioning remains disabled" if not enabled else "Provisioning flag is enabled; live acceptance is still required")
    add("owner_approval", approved, "Owner approval flag is enabled" if approved else "Owner approval is absent")
    add("repository_allowlist", allowlist_ok,
        "A syntactically valid explicit allowlist is configured" if allowlist_ok else "A non-empty, unique owner/repository allowlist is required")

    github_names = (
        "DCP_AZURE_KEY_VAULT_URL",
        "DCP_GITHUB_APP_ID",
        "DCP_GITHUB_APP_INSTALLATION_ID",
        "DCP_GITHUB_APP_PRIVATE_KEY_SECRET_NAME",
    )
    github_present = all(_present(values, name) for name in github_names)
    vault_url = values.get("DCP_AZURE_KEY_VAULT_URL", "")
    github_valid = github_present and _https_origin(vault_url) and vault_url.endswith(".vault.azure.net")
    add("github_app_configuration", github_valid,
        "GitHub App and Key Vault references are present" if github_valid
        else "GitHub App ID, installation ID, Key Vault origin, and private-key secret name are required")

    azure_names = (
        "DCP_AZURE_SUBSCRIPTION_ID", "DCP_AZURE_RESOURCE_GROUP",
        "DCP_AZURE_LOCATION", "DCP_AZURE_SUBNET_ID", "DCP_AZURE_NSG_ID",
        "DCP_AZURE_BUDGET_NAME", "DCP_AZURE_PROJECTED_RUN_COST_USD",
        "DCP_AZURE_LINUX_VM_SIZE", "DCP_AZURE_WINDOWS_VM_SIZE",
        "DCP_RUNNER_VERSION", "DCP_RUNNER_LINUX_SHA256", "DCP_RUNNER_WINDOWS_SHA256",
    )
    azure_present = all(_present(values, name) for name in azure_names)
    add("azure_configuration_presence", azure_present,
        "Azure resource, budget, VM, and pinned runner artifact settings are present" if azure_present
        else "Azure deployment configuration is incomplete; missing settings are intentionally not echoed")
    add("azure_network_policy", False,
        "UNKNOWN: the deployed subnet/NSG egress policy requires independent live verification")
    add("azure_guest_profile", False,
        "UNKNOWN: OS login profile and protected bootstrap require deployment-specific verification")

    orka_names = (
        "DCP_ORKA_URL", "DCP_ORKA_NAMESPACE", "DCP_ORKA_VM_CONFIG",
        "DCP_ORKA_API_TOKEN_SECRET_NAME",
    )
    orka_present = all(_present(values, name) for name in orka_names)
    orka_url_ok = _https_origin(values.get("DCP_ORKA_URL", ""))
    add("orka_configuration_presence", orka_present and orka_url_ok,
        "Orka endpoint and references are present" if orka_present and orka_url_ok
        else "Orka HTTPS endpoint, namespace, approved VM config, and Key Vault secret name are required")
    add("orka_budget_source", False,
        "UNKNOWN: an authoritative Orka-specific budget reader and freshness policy are not implemented")
    add("orka_user_data_bootstrap", False,
        "UNKNOWN: protected macOS runner User Data bootstrap and registration verification are not implemented")

    add("live_provider_acceptance", False,
        "SKIPPED: this read-only preflight never contacts Azure, Orka, GitHub, or creates resources",
        status="SKIPPED")

    statuses = [item["status"] for item in checks]
    overall = "PASS" if all(status == "PASS" for status in statuses) else (
        "FAIL" if "FAIL" in statuses else "UNKNOWN"
    )
    return {"overall": overall, "provisioning_enabled": enabled, "checks": checks}


def main() -> int:
    result = inspect_environment()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
