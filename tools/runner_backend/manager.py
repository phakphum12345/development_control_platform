"""Policy-enforcing orchestration for ephemeral macOS cloud runners."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .provider import RunnerInstance, RunnerProvider

_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RunnerPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class RunnerRequest:
    repository: str
    workflow_run_id: int
    commit_sha: str
    image: str = "macos-15-arm64"
    max_runtime_minutes: int = 60

    def validate(self, allowed_repositories: set[str]) -> None:
        if not _REPO.fullmatch(self.repository):
            raise RunnerPolicyError("Repository must use owner/name form.")
        if self.repository not in allowed_repositories:
            raise RunnerPolicyError("Repository is not allowlisted for cloud runner provisioning.")
        if (
            not isinstance(self.workflow_run_id, int)
            or isinstance(self.workflow_run_id, bool)
            or self.workflow_run_id <= 0
        ):
            raise RunnerPolicyError("workflow_run_id must be a positive integer.")
        if not _SHA.fullmatch(self.commit_sha):
            raise RunnerPolicyError("commit_sha must be a full lowercase 40-character SHA.")
        if self.image != "macos-15-arm64":
            raise RunnerPolicyError("Only the approved macos-15-arm64 image is enabled.")
        if (
            not isinstance(self.max_runtime_minutes, int)
            or isinstance(self.max_runtime_minutes, bool)
            or not 5 <= self.max_runtime_minutes <= 180
        ):
            raise RunnerPolicyError("max_runtime_minutes must be an integer between 5 and 180.")


class RunnerManager:
    def __init__(self, provider: RunnerProvider, allowed_repositories: set[str] | None = None):
        self.provider = provider
        configured = os.getenv("DCP_RUNNER_ALLOWED_REPOSITORIES", "")
        self.allowed_repositories = allowed_repositories if allowed_repositories is not None else {
            item.strip() for item in configured.split(",") if item.strip()
        }

    def provision_macos(self, request: RunnerRequest) -> RunnerInstance:
        request.validate(self.allowed_repositories)
        return self.provider.provision({
            "repository": request.repository,
            "workflow_run_id": request.workflow_run_id,
            "commit_sha": request.commit_sha,
            "image": request.image,
            "labels": ["self-hosted", "macOS", "ARM64", "dcp-cloud-macos"],
            "ephemeral": True,
            "max_runtime_minutes": request.max_runtime_minutes,
            "network_policy": "restricted-egress",
            "registration_token_handling": "provider-side-only",
        })

    def status(self, provider_id: str) -> RunnerInstance:
        if not provider_id or len(provider_id) > 200:
            raise RunnerPolicyError("Invalid provider runner ID.")
        return self.provider.status(provider_id)

    def terminate(self, provider_id: str) -> RunnerInstance:
        if not provider_id or len(provider_id) > 200:
            raise RunnerPolicyError("Invalid provider runner ID.")
        return self.provider.terminate(provider_id)
