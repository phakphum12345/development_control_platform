"""Durable provider routing for Azure Linux/Windows and Orka macOS."""
from __future__ import annotations

from tools.runner_backend.provider import RunnerInstance
from .policy import PROFILES


class ProviderRouter:
    """Route by approved OS profile and namespace provider IDs across restarts."""

    requires_runner_cleanup = True
    _PREFIXES = {"azure": "azure:", "orka": "orka:"}

    def __init__(self, azure_provider, orka_provider):
        self.providers = {"azure": azure_provider, "orka": orka_provider}

    def _provider_name_for_os(self, os_name):
        profile = PROFILES.get(os_name)
        if profile is None:
            raise ValueError("Unsupported runner OS")
        return profile["provider"]

    def budget_provider_for_os(self, os_name):
        """Return the provider key used to select an independent budget guard."""
        return self._provider_name_for_os(os_name)

    def _unwrap(self, provider_id):
        if not isinstance(provider_id, str):
            raise ValueError("Invalid routed provider identifier")
        for name, prefix in self._PREFIXES.items():
            if provider_id.startswith(prefix) and len(provider_id) > len(prefix):
                return name, provider_id[len(prefix):]
        raise ValueError("Unknown routed provider identifier")

    @staticmethod
    def _wrap(name, instance):
        if not isinstance(instance, RunnerInstance):
            raise TypeError("Provider returned an invalid runner instance")
        return RunnerInstance(
            name + ":" + instance.provider_id,
            instance.state,
            instance.runner_name,
            instance.labels,
            instance.detail,
        )

    def readiness(self, os_name):
        name = self._provider_name_for_os(os_name)
        provider = self.providers.get(name)
        check = getattr(provider, "readiness", None)
        if not callable(check):
            return {"ready": False, "message": name + " provider is not configured"}
        try:
            result = check(os_name)
        except Exception:
            return {"ready": False, "message": name + " provider readiness check failed"}
        if not isinstance(result, dict) or result.get("ready") is not True:
            return result if isinstance(result, dict) else {
                "ready": False, "message": name + " provider is not ready"
            }
        return result

    def provision(self, payload):
        name = self._provider_name_for_os(payload.get("target_os"))
        provider = self.providers.get(name)
        if provider is None:
            raise RuntimeError(name + " provider is not configured")
        ready = self.readiness(payload["target_os"])
        if ready.get("ready") is not True:
            raise RuntimeError("Selected provider is not ready")
        return self._wrap(name, provider.provision(payload))

    def status(self, provider_id):
        name, raw_id = self._unwrap(provider_id)
        provider = self.providers.get(name)
        if provider is None:
            raise RuntimeError(name + " provider is not configured")
        return self._wrap(name, provider.status(raw_id))

    def terminate(self, provider_id):
        name, raw_id = self._unwrap(provider_id)
        provider = self.providers.get(name)
        if provider is None:
            raise RuntimeError(name + " provider is not configured")
        return self._wrap(name, provider.terminate(raw_id))
