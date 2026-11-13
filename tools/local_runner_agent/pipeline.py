"""One-job Runner pipeline joining Gateway, checkout, workspace and Flutter execution."""
from __future__ import annotations

import time
import sys
from dataclasses import asdict
from typing import Protocol

from .artifacts import ArtifactPackageError, FlutterArtifactPackager
from .checkout import CheckoutError
from .execution import ExecutionError, FlutterBuildExecutor
from .terminal_executor import TerminalExecutionError, TerminalScriptExecutor
from tools.cloud_gateway.terminal_execution_contract import parameters_digest
from .workspace import WorkspaceError, WorkspaceManager
from .web_build import WebBuildExecutor, WebArtifactPackager
from .browser_test import BrowserTestError, StaticWebPlaywrightTester


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
        browser_test_executor: StaticWebPlaywrightTester | None = None,
        terminal_executor: TerminalScriptExecutor | None = None,
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
        self.browser_test_executor = browser_test_executor
        self.terminal_executor = terminal_executor or TerminalScriptExecutor(enabled=False)
        self.artifact_packager = artifact_packager or FlutterArtifactPackager(workspaces)
        detected_os = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
        self.worker_os = worker_os or detected_os
        self.capabilities = frozenset(capabilities or {"flutter", self.worker_os})
        if self.worker_os not in ("linux", "windows", "macos"):
            raise ValueError("worker_os must be linux, windows, or macos")

    def _save_checkpoint(self, job_id, sequence, step, safe_to_resume, data):
        checkpoint = {
            "version": 1,
            "step": step,
            "safe_to_resume": safe_to_resume,
            "data": data,
        }
        saved = self.client.checkpoint(job_id, sequence + 1, checkpoint)
        return saved["checkpoint_seq"]

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
        checkpoint = job.get("checkpoint") if isinstance(job.get("checkpoint"), dict) else None
        checkpoint_seq = job.get("checkpoint_seq", 0)
        if (checkpoint and checkpoint.get("safe_to_resume") is True
                and checkpoint.get("step") == "ready-to-finish"):
            saved = checkpoint.get("data", {})
            if (not isinstance(saved, dict)
                    or saved.get("outcome") not in ("succeeded", "failed", "cancelled")
                    or not isinstance(saved.get("result"), dict)):
                return {"job_id": job_id, "outcome": "unconfirmed",
                        "error": "CHECKPOINT_CONTRACT_INVALID"}
            try:
                completed = self.client.finish(
                    job_id, saved["outcome"], result=saved["result"],
                    error_code=saved.get("error_code"),
                )
                return {
                    "job": completed, "outcome": saved["outcome"],
                    "result": saved["result"], "resumed_from_checkpoint": True,
                }
            except Exception:
                return {"job_id": job_id, "outcome": "unconfirmed",
                        "error": "CHECKPOINT_FINISH_NOT_CONFIRMED"}
        allocated = False
        retained_for_preview = False
        outcome = "failed"
        error_code = "RUNNER_EXECUTION_FAILED"
        result = {}
        last_heartbeat = 0.0
        browser_test_artifact_path = None
        try:
            job_payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
            # The Gateway's public claim response deliberately omits the private payload.
            # Source identity and immutable revision are exposed as sanitized top-level fields.
            source_type = job.get("source_type") or job_payload.get("source_type", "github")
            terminal_job = job.get("terminal") if isinstance(job.get("terminal"), dict) else {}
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
            elif source_type == "terminal_script":
                project_id = terminal_job.get("project_id")
                workspace_id = terminal_job.get("workspace_id")
                snapshot_sha256 = terminal_job.get("snapshot_sha256")
                if job.get("target") != "terminal_script":
                    raise ExecutionError("Terminal source requires the terminal_script target")
                if project_id not in self.trusted_local_projects:
                    raise ExecutionError("Terminal project is not in the Runner trusted-project allowlist")
                if self.local_project_checkout is None:
                    raise CheckoutError("Terminal Project Workspace registry is not configured")
                if not self.terminal_executor.enabled:
                    raise TerminalExecutionError("Terminal execution is disabled on this Runner")
                required = (
                    project_id, workspace_id, snapshot_sha256,
                    terminal_job.get("template_id"), terminal_job.get("authorization_id"),
                    terminal_job.get("template_digest"), terminal_job.get("parameters_sha256"),
                )
                if any(not isinstance(value, str) or not value for value in required):
                    raise ExecutionError("Terminal job contract is incomplete")
                if not isinstance(terminal_job.get("parameters"), dict):
                    raise ExecutionError("Terminal job parameters are invalid")
                if parameters_digest(terminal_job["parameters"]) != terminal_job["parameters_sha256"]:
                    raise TerminalExecutionError("Terminal parameter digest does not match the queued Job")
                # The Gateway verifies the current Job lease and consumes the app-issued
                # one-time grant before the Runner resolves or executes the project path.
                grant = self.client.verify_terminal_grant(job_id, terminal_job["authorization_id"])
                if grant.get("action") != "terminal.read_only":
                    raise TerminalExecutionError("Runner received an unsupported Terminal grant scope")
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
            elif source_type == "terminal_script":
                resolved = self.local_project_checkout.registry.resolve_workspace(
                    project_id, workspace_id, snapshot_sha256
                )
                source = Path(resolved["path"])
                result.update({
                    "source_type": "terminal_script",
                    "source_sha256": snapshot_sha256,
                    "project_workspace_id": workspace_id,
                    "project_relative_path": resolved["relative_path"],
                })
                self.client.append_log(
                    job_id, "Resolved the authorized Project Workspace and verified its current snapshot",
                    "system",
                )
            else:
                source = self.checkout_provider.checkout(
                    job_id, worker_id, job["repository"], job["commit_sha"]
                )
                result["source_type"] = "github"
                self.client.append_log(
                    job_id, f"Checked out immutable commit {job['commit_sha']}", "system"
                )

            checkpoint_seq = self._save_checkpoint(
                job_id, checkpoint_seq, "source-materialized", False,
                {
                    "source_type": source_type,
                    "source_id": job.get("source_id") or job.get("repository"),
                    "source_sha256": job.get("source_sha256") or job.get("commit_sha"),
                },
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

            if source_type == "terminal_script":
                self.terminal_executor.log = lambda stream, message: self.client.append_log(job_id, message, stream)
                terminal_result = self.terminal_executor.run(
                    job_id, worker_id, source,
                    terminal_job["template_id"], terminal_job["parameters"],
                    terminal_job["template_digest"],
                    cancel_requested=cancellation_requested,
                )
                outcome = terminal_result.outcome
                error_code = terminal_result.error_code
                build_succeeded = outcome == "succeeded"
                result.update({
                    "template_id": terminal_job["template_id"],
                    "return_code": terminal_result.return_code,
                    "duration_seconds": terminal_result.duration_seconds,
                    "output_bytes": terminal_result.output_bytes,
                })
                self.client.append_log(
                    job_id,
                    f"Terminal template {terminal_job['template_id']} {outcome}; "
                    f"exit={terminal_result.return_code}; output={terminal_result.output_bytes} bytes",
                    "system",
                )
                if outcome == "succeeded":
                    error_code = None
            else:
                build_target = "build_static_web" if job["target"] == "test_static_web" else job["target"]
                selected_executor = self.web_executor if build_target in WebBuildExecutor.TARGETS else self.executor
                selected_executor.log = lambda stream, message: self.client.append_log(job_id, message, stream)
                build = selected_executor.run(
                    job_id, worker_id, build_target,
                    cancel_requested=cancellation_requested,
                )
                outcome = build.outcome
                error_code = build.error_code
                build_succeeded = outcome == "succeeded"
                result.update({
                    "command": list(build.command),
                    "return_code": build.return_code,
                    "duration_seconds": build.duration_seconds,
                    "output_bytes": build.output_bytes,
                    "source_directory": str(source.relative_to(self.workspaces.get(job_id, worker_id))),
                })
                if build_succeeded and job["target"] == "test_static_web":
                    if self.browser_test_executor is None:
                        raise BrowserTestError("Playwright test capability is not configured on this Runner")
                    browser_result = self.browser_test_executor.run(job_id, worker_id)
                    browser_test_artifact_path = browser_result.get("artifact_path")
                    result["browser_test"] = {
                        key: value for key, value in browser_result.items()
                        if key not in ("artifact_path",)
                    }
                    self.client.append_log(
                        job_id,
                        "Playwright static preview tests " + browser_result["status"],
                        "system",
                    )
                    if browser_result["status"] != "PASS":
                        outcome = "failed"
                        error_code = "WEB_BROWSER_TESTS_FAILED"
                self.client.append_log(
                    job_id,
                    f"Build execution {outcome}; exit={build.return_code}; "
                    f"duration={build.duration_seconds}s; output={build.output_bytes} bytes",
                    "system",
                )

            if build_succeeded and source_type != "terminal_script":
                packager = self.web_artifact_packager if build_target in ("build_static_web", "build_vite") else self.artifact_packager
                artifact = packager.package(job_id, worker_id, build_target)
                if artifact is not None:
                    artifact_path, artifact_name = artifact
                    metadata = self.client.upload_artifact(job_id, str(artifact_path), artifact_name)
                    result["artifact"] = metadata
                    self.client.append_log(
                        job_id, f"Artifact stored: {artifact_name} ({metadata['size']} bytes)", "system"
                    )
                if job["target"] == "test_static_web" and self.browser_test_executor is not None:
                    if browser_test_artifact_path is not None:
                        metadata = self.client.upload_artifact(job_id, str(browser_test_artifact_path), "web-test-results.zip")
                        result["test_artifact"] = metadata
                        self.client.append_log(
                            job_id, f"Test evidence stored: web-test-results.zip ({metadata['size']} bytes)", "system"
                        )
                if job["target"] in ("build_static_web", "build_vite", "test_static_web"):
                    self.workspaces.retain_for_preview(job_id, worker_id, ttl_seconds=3600)
                    self.client.append_log(
                        job_id, "Successful web build workspace retained for a bounded local preview window", "system"
                    )
                    retained_for_preview = True
                    result["workspace_retained_for_preview"] = True
                if outcome == "succeeded":
                    error_code = None
        except (ArtifactPackageError, BrowserTestError, CheckoutError, ExecutionError, TerminalExecutionError, WorkspaceError) as exc:
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
            if (not retained_for_preview and result.get("workspace_cleanup") != "failed"
                    and outcome != "cancelled"):
                checkpoint_seq = self._save_checkpoint(
                    job_id, checkpoint_seq, "ready-to-finish", True,
                    {"outcome": outcome, "result": result, "error_code": error_code},
                )
            else:
                checkpoint_step = (
                    "cancelled-ready-to-finish" if outcome == "cancelled"
                    else "workspace-not-transferable"
                )
                checkpoint_seq = self._save_checkpoint(
                    job_id, checkpoint_seq, checkpoint_step, False,
                    {"outcome": outcome, "result": result, "error_code": error_code},
                )
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
