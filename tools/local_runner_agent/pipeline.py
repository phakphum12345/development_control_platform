"""One-job Runner pipeline joining Gateway, checkout, workspace and Flutter execution."""
from __future__ import annotations

import time
import sys
from dataclasses import asdict
from typing import Protocol

from .artifacts import ArtifactPackageError, FlutterArtifactPackager
from .checkout import CheckoutError
from .execution import ExecutionError, FlutterBuildExecutor
from .workspace import WorkspaceError, WorkspaceManager
from .web_build import WebBuildExecutor, WebArtifactPackager


class CheckoutProvider(Protocol):
    def checkout(self, job_id: str, worker_id: str, repository: str, commit_sha: str):
        ...


class RunnerPipeline:
    """Claim and execute one allowlisted Flutter job; never polls indefinitely."""

    def __init__(
        self,
        client,
        workspaces: WorkspaceManager,
        checkout: CheckoutProvider,
        executor: FlutterBuildExecutor,
        *,
        heartbeat_interval_seconds: int = 10,
        trusted_repositories: set[str] | frozenset[str] = frozenset(),
        artifact_packager: FlutterArtifactPackager | None = None,
        worker_os: str | None = None,
        capabilities: set[str] | frozenset[str] | None = None,
        web_executor: WebBuildExecutor | None = None,
        web_artifact_packager: WebArtifactPackager | None = None,
        local_project_checkout=None,
        trusted_local_projects: set[str] | frozenset[str] = frozenset(),
    ):
        if isinstance(heartbeat_interval_seconds, bool) or not isinstance(heartbeat_interval_seconds, int) or not 5 <= heartbeat_interval_seconds <= 60:
            raise ValueError("heartbeat interval must be between 5 and 60 seconds")
        self.client = client
        self.workspaces = workspaces
        self.checkout_provider = checkout
        self.executor = executor
        self.web_executor = web_executor or WebBuildExecutor(workspaces, enabled=False)
        self.web_artifact_packager = web_artifact_packager or WebArtifactPackager(workspaces)
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.trusted_repositories = frozenset(trusted_repositories)
        self.local_project_checkout = local_project_checkout
        self.trusted_local_projects = frozenset(trusted_local_projects)
        self.artifact_packager = artifact_packager or FlutterArtifactPackager(workspaces)
        detected_os = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
        self.worker_os = worker_os or detected_os
        self.capabilities = frozenset(capabilities or {"flutter", self.worker_os})
        if self.worker_os not in ("linux", "windows", "macos"):
            raise ValueError("worker_os must be linux, windows, or macos")

    def run_once(self) -> dict | None:
        """Claim at most one job. Returns None when the queue is empty."""
        runner = self.client.register(self.worker_os, sorted(self.capabilities))
        if runner.get("state") != "online":
            raise ExecutionError("Runner is draining or offline and cannot claim new work")
        job = self.client.claim(lease_seconds=300)
        if job is None:
            return None
        job_id = job["id"]
        worker_id = job["worker"]
        allocated = False
        retained_for_preview = False
        outcome = "failed"
        error_code = "RUNNER_EXECUTION_FAILED"
        result = {}
        last_heartbeat = 0.0
        try:
            job_payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            # The Gateway's public claim response deliberately omits the private payload.
            # Source identity and immutable revision are exposed as sanitized top-level fields.
            source_type = job.get("source_type") or job_payload.get("source_type", "github")
            if source_type == "github":
                if job["repository"] not in self.trusted_repositories:
                    raise ExecutionError("repository is not in the Runner trusted-repository allowlist")
            elif source_type == "local_folder":
                project_id = job.get("source_id") or job_payload.get("source_id")
                snapshot_sha256 = job.get("source_sha256") or job_payload.get("source_sha256")
                if project_id not in self.trusted_local_projects:
                    raise ExecutionError("local project is not in the Runner trusted-project allowlist")
                if self.local_project_checkout is None:
                    raise CheckoutError("Local Project snapshot checkout is not configured")
                if not isinstance(snapshot_sha256, str):
                    raise CheckoutError("Local Project snapshot revision is unavailable")
            else:
                raise ExecutionError("job source type is not supported by this Runner")
            self.workspaces.cleanup_expired_preview_workspaces()
            self.workspaces.create(job_id, worker_id)
            allocated = True
            self.client.append_log(job_id, "Runner claimed job; workspace allocated", "system")
            if source_type == "local_folder":
                source, snapshot = self.local_project_checkout.checkout(
                    job_id, worker_id, project_id, snapshot_sha256
                )
                result["source_type"] = "local_folder"
                result["source_sha256"] = snapshot["snapshot_sha256"]
                self.client.append_log(
                    job_id, "Materialized owner-approved Local Folder snapshot SHA-256 "
                    + snapshot["snapshot_sha256"], "system"
                )
            else:
                source = self.checkout_provider.checkout(
                    job_id, worker_id, job["repository"], job["commit_sha"]
                )
                result["source_type"] = "github"
                self.client.append_log(
                    job_id, f"Checked out immutable commit {job['commit_sha']}", "system"
                )

            def cancellation_requested():
                nonlocal last_heartbeat
                now = time.monotonic()
                if now - last_heartbeat < self.heartbeat_interval_seconds:
                    return False
                current = self.client.heartbeat(job_id, lease_seconds=300)
                self.client.heartbeat_worker()
                last_heartbeat = now
                return current.get("state") == "cancel_requested"

            selected_executor = self.web_executor if job["target"] in ("build_static_web", "build_vite") else self.executor
            selected_executor.log = lambda stream, message: self.client.append_log(job_id, message, stream)
            build = selected_executor.run(
                job_id, worker_id, job["target"],
                cancel_requested=cancellation_requested,
            )
            outcome = build.outcome
            error_code = build.error_code
            result.update({
                "command": list(build.command),
                "return_code": build.return_code,
                "duration_seconds": build.duration_seconds,
                "output_bytes": build.output_bytes,
                "source_directory": str(source.relative_to(self.workspaces.get(job_id, worker_id))),
            })
            self.client.append_log(
                job_id,
                f"Build execution {outcome}; exit={build.return_code}; "
                f"duration={build.duration_seconds}s; output={build.output_bytes} bytes",
                "system",
            )
            if outcome == "succeeded":
                packager = self.web_artifact_packager if job["target"] in ("build_static_web", "build_vite") else self.artifact_packager
                artifact = packager.package(job_id, worker_id, job["target"])
                if artifact is not None:
                    artifact_path, artifact_name = artifact
                    metadata = self.client.upload_artifact(job_id, str(artifact_path), artifact_name)
                    result["artifact"] = metadata
                    self.client.append_log(
                        job_id, f"Artifact stored: {artifact_name} ({metadata['size']} bytes)", "system"
                    )
                if outcome == "succeeded" and job["target"] in ("build_static_web", "build_vite"):
                    self.workspaces.retain_for_preview(job_id, worker_id, ttl_seconds=3600)
                    self.client.append_log(
                        job_id, "Successful web build workspace retained for a bounded local preview window", "system"
                    )
                    retained_for_preview = True
                    result["workspace_retained_for_preview"] = True
                error_code = None
        except (ArtifactPackageError, CheckoutError, ExecutionError, WorkspaceError) as exc:
            self.client.append_log(
                job_id, f"Runner rejected job safely: {type(exc).__name__}", "stderr"
            )
            result = {"error": type(exc).__name__}
            if isinstance(exc, ExecutionError):
                # ExecutionError messages are fixed policy diagnostics, not subprocess output.
                result["reason"] = str(exc)
            error_code = "RUNNER_POLICY_OR_BUILD_ERROR"
        except Exception as exc:
            # Do not echo exception text: transport and provider errors can contain secrets.
            try:
                self.client.append_log(
                    job_id, f"Runner failed safely: {type(exc).__name__}", "stderr"
                )
            except Exception:
                pass
            result = {"error": type(exc).__name__}
            error_code = "RUNNER_INTERNAL_ERROR"
        finally:
            if allocated and not retained_for_preview:
                try:
                    self.workspaces.cleanup(job_id, worker_id)
                    self.client.append_log(job_id, "Workspace cleaned", "system")
                except Exception:
                    outcome = "failed"
                    error_code = "WORKSPACE_CLEANUP_FAILED"
                    result["workspace_cleanup"] = "failed"
        try:
            completed = self.client.finish(
                job_id, outcome, result=result, error_code=error_code
            )
            return {"job": completed, "outcome": outcome, "result": result}
        except Exception:
            # A lost/expired lease must never be reported as a successful completion.
            return {
                "job_id": job_id, "outcome": "unconfirmed",
                "error": "JOB_FINISH_NOT_CONFIRMED",
            }
