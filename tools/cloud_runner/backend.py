"""DCP workflow client for the canonical Cloud Runner Gateway contract.

This module is intentionally an adapter over the shared runner policy and HTTPS
provider implementation. It never provisions infrastructure on the local host.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlparse

from tools.runner_backend.cloud_api import CloudAPIProvider
from tools.runner_backend.manager import RunnerManager, RunnerRequest
from tools.runner_backend.provider import RunnerInstance

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class RunnerSettings:
    endpoint: str
    bearer_token: str = field(repr=False)
    allowed_repositories: tuple[str, ...] = ("phakphum12345/generated-A4-pdf",)
    timeout_seconds: int = 20

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        try:
            valid_origin = (
                parsed.scheme == "https"
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and parsed.path in ("", "/")
                and not parsed.params
                and not parsed.query
                and not parsed.fragment
                and (parsed.port is None or 1 <= parsed.port <= 65535)
            )
        except ValueError:
            valid_origin = False
        if not valid_origin:
            raise ValueError("provider URL must be an HTTPS origin without path, query, fragment, or credentials")
        if not self.bearer_token.strip():
            raise ValueError("provider bearer token is required")
        if (
            not self.allowed_repositories
            or any(not isinstance(repo, str) or not _REPOSITORY.fullmatch(repo) for repo in self.allowed_repositories)
            or len(set(self.allowed_repositories)) != len(self.allowed_repositories)
        ):
            raise ValueError("allowed_repositories must contain unique owner/name values")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int):
            raise ValueError("provider timeout must be an integer")
        if not 1 <= self.timeout_seconds <= 60:
            raise ValueError("provider timeout must be between 1 and 60 seconds")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RunnerSettings":
        values = os.environ if env is None else env
        raw_repos = values.get(
            "DCP_RUNNER_ALLOWED_REPOSITORIES",
            "phakphum12345/generated-A4-pdf",
        ).strip()
        # Accept JSON arrays for backwards compatibility, but document and emit
        # the simpler comma-separated format.
        if raw_repos.startswith("["):
            try:
                repos = json.loads(raw_repos)
            except json.JSONDecodeError as exc:
                raise ValueError("DCP_RUNNER_ALLOWED_REPOSITORIES must be a comma-separated list or JSON array") from exc
        else:
            repos = [item.strip() for item in raw_repos.split(",") if item.strip()]
        if not isinstance(repos, list) or not all(isinstance(item, str) for item in repos):
            raise ValueError("DCP_RUNNER_ALLOWED_REPOSITORIES must contain repository strings")
        try:
            timeout = int(values.get("DCP_RUNNER_PROVIDER_TIMEOUT", "20"))
        except (TypeError, ValueError) as exc:
            raise ValueError("DCP_RUNNER_PROVIDER_TIMEOUT must be an integer") from exc
        return cls(
            endpoint=values.get("DCP_RUNNER_PROVIDER_URL", ""),
            bearer_token=values.get("DCP_RUNNER_PROVIDER_TOKEN", ""),
            allowed_repositories=tuple(repos),
            timeout_seconds=timeout,
        )


@dataclass(frozen=True)
class ProvisionRequest:
    repository: str
    commit_sha: str
    workflow_run_id: int

    def validate(self, settings: RunnerSettings) -> None:
        if self.repository not in settings.allowed_repositories:
            raise ValueError("target repository is not on the provider allowlist")
        if not isinstance(self.commit_sha, str) or not _SHA.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a full 40-character Git SHA")
        if (
            isinstance(self.workflow_run_id, bool)
            or not isinstance(self.workflow_run_id, int)
            or self.workflow_run_id < 1
        ):
            raise ValueError("workflow_run_id must be a positive integer")


@dataclass(frozen=True)
class ProvisionResult:
    runner_id: str
    state: str
    runner_name: str | None
    labels: tuple[str, ...]
    detail: str | None


def request_provisioning(settings: RunnerSettings, request: ProvisionRequest) -> ProvisionResult:
    """Request an ephemeral macOS runner using the canonical OpenAPI payload."""
    request.validate(settings)
    provider = CloudAPIProvider(
        base_url=settings.endpoint,
        token=settings.bearer_token,
        timeout=settings.timeout_seconds,
    )
    manager = RunnerManager(provider, set(settings.allowed_repositories))
    instance: RunnerInstance = manager.provision_macos(
        RunnerRequest(
            repository=request.repository,
            workflow_run_id=request.workflow_run_id,
            commit_sha=request.commit_sha.lower(),
        )
    )
    return ProvisionResult(
        runner_id=instance.provider_id,
        state=instance.state,
        runner_name=instance.runner_name,
        labels=instance.labels,
        detail=instance.detail,
    )
