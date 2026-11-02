"""Provider-neutral, fail-closed macOS cloud runner provisioning client.

This control plane delegates VM creation to a separately deployed provider adapter.
It never creates a runner on the local host and never treats dispatch acceptance as
proof that a macOS runner is online or that a build passed.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlparse

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class RunnerSettings:
    endpoint: str
    bearer_token: str = field(repr=False)
    allowed_repositories: tuple[str, ...] = ("phakphum12345/generated-A4-pdf",)
    labels: tuple[str, ...] = ("self-hosted", "macOS", "ARM64", "dcp-ephemeral")
    timeout_seconds: int = 20

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("provider endpoint must be an absolute HTTPS URL")
        if not self.bearer_token.strip():
            raise ValueError("provider bearer token is required")
        if not self.allowed_repositories or any(not _REPOSITORY.fullmatch(x) for x in self.allowed_repositories):
            raise ValueError("allowed_repositories must contain owner/name values")
        if not self.labels or any(not x.strip() for x in self.labels):
            raise ValueError("runner labels must be non-empty")
        if not 1 <= self.timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 1 and 60")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RunnerSettings":
        values = os.environ if env is None else env
        raw_repos = values.get("DCP_RUNNER_ALLOWED_REPOSITORIES", "phakphum12345/generated-A4-pdf")
        raw_labels = values.get("DCP_MACOS_RUNNER_LABELS", '["self-hosted","macOS","ARM64","dcp-ephemeral"]')
        try:
            repos, labels = json.loads(raw_repos), json.loads(raw_labels)
        except json.JSONDecodeError as exc:
            raise ValueError("repository allowlist and runner labels must be JSON arrays") from exc
        if not isinstance(repos, list) or not all(isinstance(x, str) for x in repos):
            raise ValueError("DCP_RUNNER_ALLOWED_REPOSITORIES must be a JSON string array")
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
            raise ValueError("DCP_MACOS_RUNNER_LABELS must be a JSON string array")
        return cls(
            endpoint=values.get("DCP_RUNNER_PROVIDER_URL", ""),
            bearer_token=values.get("DCP_RUNNER_PROVIDER_TOKEN", ""),
            allowed_repositories=tuple(repos),
            labels=tuple(labels),
            timeout_seconds=int(values.get("DCP_RUNNER_PROVIDER_TIMEOUT", "20")),
        )


@dataclass(frozen=True)
class ProvisionRequest:
    repository: str
    commit_sha: str
    ref: str
    workflow_run_id: int
    workflow_run_attempt: int = 1

    def validate(self, settings: RunnerSettings) -> None:
        if self.repository not in settings.allowed_repositories:
            raise ValueError("target repository is not on the provider allowlist")
        if not _SHA.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a full 40-character Git SHA")
        if not self.ref or self.ref.startswith("-") or "\\x00" in self.ref:
            raise ValueError("ref is invalid")
        if self.workflow_run_id < 1 or self.workflow_run_attempt < 1:
            raise ValueError("workflow run identifiers must be positive")

    def payload(self, settings: RunnerSettings) -> dict[str, object]:
        self.validate(settings)
        return {
            "contract": "dcp.macos-runner-provision.v1",
            "repository": self.repository,
            "commit_sha": self.commit_sha.lower(),
            "ref": self.ref,
            "workflow_run_id": self.workflow_run_id,
            "workflow_run_attempt": self.workflow_run_attempt,
            "runner": {
                "os": "macOS",
                "architecture": "ARM64",
                "labels": list(settings.labels),
                "ephemeral": True,
                "max_jobs": 1,
            },
            "safety": {
                "repository_allowlist_enforced": True,
                "one_job_then_destroy": True,
                "no_secrets_from_untrusted_pull_requests": True,
                "registration_token_must_not_be_returned": True,
            },
        }


@dataclass(frozen=True)
class ProvisionResult:
    accepted: bool
    request_id: str
    state: str


def request_provisioning(settings: RunnerSettings, request: ProvisionRequest) -> ProvisionResult:
    """Ask the configured provider to provision an ephemeral macOS runner."""
    body = json.dumps(request.payload(settings), separators=(",", ":")).encode("utf-8")
    http_request = urllib.request.Request(
        settings.endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {settings.bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=settings.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"provider rejected request (HTTP {exc.code}); response body suppressed") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"provider unavailable ({type(exc).__name__})") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("provider returned invalid JSON") from None

    if not isinstance(result, dict) or result.get("accepted") is not True:
        raise RuntimeError("provider did not accept the provisioning request")
    request_id, state = result.get("request_id"), result.get("state", "provisioning")
    if not isinstance(request_id, str) or not request_id.strip() or not isinstance(state, str):
        raise RuntimeError("provider response has invalid request_id/state")
    return ProvisionResult(True, request_id, state)
