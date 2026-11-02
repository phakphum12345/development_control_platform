"""HTTPS adapter for a separately deployed cloud-runner gateway.

The gateway owns vendor-specific VM provisioning and GitHub ephemeral-runner
registration. DCP never receives or logs GitHub runner registration tokens.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from .provider import RunnerInstance


class ProviderError(RuntimeError):
    pass


class CloudAPIProvider:
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 timeout: int = 20):
        self.base_url = (base_url or os.getenv("DCP_RUNNER_PROVIDER_URL", "")).rstrip("/")
        self.token = token or os.getenv("DCP_RUNNER_PROVIDER_TOKEN", "")
        self.timeout = timeout
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ProviderError("Provider URL must be an HTTPS origin without embedded credentials.")
        if not self.token:
            raise ProviderError("DCP_RUNNER_PROVIDER_TOKEN is not configured.")

    def _request(self, method: str, path: str, payload: dict | None = None) -> RunnerInstance:
        url = self.base_url + path
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "DCP-Cloud-Runner-Control-Plane/1.0",
        })
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read(65536).decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Cloud provider request failed: {type(exc).__name__}") from exc
        if not isinstance(data, dict):
            raise ProviderError("Provider returned an invalid response shape.")
        provider_id = data.get("id")
        state = data.get("state")
        if not isinstance(provider_id, str) or not provider_id or not isinstance(state, str):
            raise ProviderError("Provider response must contain non-empty id and state fields.")
        labels = data.get("labels", [])
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            raise ProviderError("Provider response labels must be a list of strings.")
        return RunnerInstance(provider_id, state, data.get("runner_name"), tuple(labels), data.get("detail"))

    def provision(self, payload: dict) -> RunnerInstance:
        return self._request("POST", "/v1/runners", payload)

    def status(self, provider_id: str) -> RunnerInstance:
        return self._request("GET", f"/v1/runners/{quote(provider_id, safe='')}")

    def terminate(self, provider_id: str) -> RunnerInstance:
        return self._request("DELETE", f"/v1/runners/{quote(provider_id, safe='')}")
