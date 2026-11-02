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

_MAX_RESPONSE_BYTES = 65536


class ProviderError(RuntimeError):
    pass


class CloudAPIProvider:
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 timeout: int = 20):
        self.base_url = (base_url or os.getenv("DCP_RUNNER_PROVIDER_URL", "")).rstrip("/")
        self.token = token or os.getenv("DCP_RUNNER_PROVIDER_TOKEN", "")
        self.timeout = timeout
        try:
            parsed = urlparse(self.base_url)
            valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        except ValueError:
            valid_port = False
            parsed = urlparse("")
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or not valid_port
        ):
            raise ProviderError("Provider URL must be an HTTPS origin without path, query, fragment, or embedded credentials.")
        if not self.token:
            raise ProviderError("DCP_RUNNER_PROVIDER_TOKEN is not configured.")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ProviderError("Provider timeout must be a positive number.")

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
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise ProviderError("Provider response exceeded the 65536-byte limit.")
            data = json.loads(raw.decode("utf-8"))
        except ProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            # Deliberately omit exception text: urllib errors may contain URLs or credentials.
            raise ProviderError(f"Cloud provider request failed: {type(exc).__name__}") from exc
        if not isinstance(data, dict):
            raise ProviderError("Provider returned an invalid response shape.")
        provider_id = data.get("id")
        state = data.get("state")
        if not isinstance(provider_id, str) or not provider_id or not isinstance(state, str) or not state:
            raise ProviderError("Provider response must contain non-empty id and state fields.")
        labels = data.get("labels", [])
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            raise ProviderError("Provider response labels must be a list of strings.")
        runner_name = data.get("runner_name")
        detail = data.get("detail")
        if runner_name is not None and not isinstance(runner_name, str):
            raise ProviderError("Provider response runner_name must be a string.")
        if detail is not None and not isinstance(detail, str):
            raise ProviderError("Provider response detail must be a string.")
        return RunnerInstance(provider_id, state, runner_name, tuple(labels), detail)

    def provision(self, payload: dict) -> RunnerInstance:
        return self._request("POST", "/v1/runners", payload)

    def status(self, provider_id: str) -> RunnerInstance:
        return self._request("GET", f"/v1/runners/{quote(provider_id, safe='')}")

    def terminate(self, provider_id: str) -> RunnerInstance:
        return self._request("DELETE", f"/v1/runners/{quote(provider_id, safe='')}")
