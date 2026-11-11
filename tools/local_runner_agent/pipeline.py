"""One-job Runner pipeline joining Gateway, checkout, workspace and Flutter execution."""
from __future__ import annotations

import os
import shutil
import stat
import time
import sys
from pathlib import Path
from dataclasses import asdict
from typing import Protocol

from .artifacts import ArtifactPackageError, FlutterArtifactPackager
from .checkout import CheckoutError
from .execution import ExecutionError, FlutterBuildExecutor
from .workspace import WorkspaceError, WorkspaceManager
from .local_project import LocalProjectError, LocalProjectRegistry


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
        local_projects: LocalProjectRegistry | None = None,
    ):
        if isinstance(heartbeat_interval_seconds, bool) or not isinstance(heartbeat_interval_seconds, int) or not 5 <= heartbeat_interval_seconds <= 60:
            raise ValueError("heartbeat interval must be between 5 and 60 seconds")
        self.client = client
        self.workspaces = workspaces
        self.checkout_provider = checkout
        self.executor = executor
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.trusted_repositories = frozenset(trusted_repositories)
        self.artifact_packager = artifact_packager or FlutterArtifactPackager(workspaces)
        detected_os = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
        self.worker_os = worker_os or detected_os
        self.capabilities = frozenset(capabilities or {"flutter", self.worker_os})
        self.local_projects = local_projects
        if self.worker_os not in ("linux", "windows", "macos"):
            raise ValueError("worker_os must be linux, windows, or macos")

    @staticmethod
    def _copy_snapshot_file(source: str, destination: str) -> str:
        source_path = Path(source)
        destination_path = Path(destination)
        try:
            before = source_path.lstat()
        except OSError:
            raise ExecutionError("snapshot file cannot be inspected") from None
        if not stat.S_ISREG(before.st_mode):
            raise ExecutionError("snapshot contains a non-regular file")
        source_flags = os.O_RDONLY
        destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            source_flags |= os.O_NOFOLLOW
            destination_flags |= os.O_NOFOLLOW
        source_fd = os.open(source_path, source_flags)
        try:
            destination_fd = os.open(destination_path, destination_flags, 0o600)
        except Exception:
            os.close(source_fd)
            raise
        copied = 0
        with os.fdopen(source_fd, "rb") as src, os.fdopen(destination_fd, "wb") as dst:
            opened = os.fstat(src.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise ExecutionError("snapshot file changed type during worktree copy")
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                dst.write(chunk)
            after = os.fstat(src.fileno())
            dst.flush()
            os.fsync(dst.fileno())
        if (opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns
        ) or copied != after.st_size:
            raise ExecutionError("snapshot file changed during worktree copy")
        os.chmod(destination_path, 0o600)
        return str(destination_path)

    @staticmethod
    def _make_worktree_writable(root: Path) -> None:
        for current, dirs, files in os.walk(root, topdown=False, followlinks=False):
            for name in files:
                path = Path(current) / name
                if not path.is_symlink():
                    os.chmod(path, 0o600)
            for name in dirs:
                path = Path(current) / name
                if not path.is_symlink() and not (
                    hasattr(path, "is_junction") and path.is_junction()
                ):
                    os.chmod(path, 0o700)
            os.chmod(current, 0o700)

    def _prepare_local_source(self, job: dict, job_id: str, worker_id: str) -> Path:
        if self.local_projects is None:
            raise ExecutionError("Local Project Registry is not configured on this Runner")
        if job.get("execution_approved") is not True:
            raise ExecutionError("Local source execution was not explicitly approved")
        project_id = job.get("local_project_id")
        expected_sha = job.get("snapshot_sha256")
        if not isinstance(project_id, str) or not isinstance(expected_sha, str):
            raise ExecutionError("Local source job is missing its project snapshot binding")
        workspace = self.workspaces.get(job_id, worker_id)
        snapshot_result = self.local_projects.materialize_project(
            project_id, workspace / "source-snapshot", expected_sha
        )
        snapshot = Path(snapshot_result["snapshot_directory"])
        if snapshot.parent.resolve(strict=True) != workspace.resolve(strict=True):
            raise ExecutionError("Local source snapshot escaped the job workspace")
        if self.local_projects._fingerprint(snapshot)[0] != expected_sha:
            raise ExecutionError("Local source snapshot failed pre-build integrity verification")
        source = workspace / "source"
        shutil.copytree(snapshot, source, symlinks=True, copy_function=self._copy_snapshot_file)
        if self.local_projects._fingerprint(source)[0] != expected_sha:
            raise ExecutionError("Local working copy does not match the approved source snapshot")
        self._make_worktree_writable(source)
        self.workspaces.check_quota(job_id, worker_id)
        return source

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
        outcome = "failed"
        error_code = "RUNNER_EXECUTION_FAILED"
        result = {}
        last_heartbeat = 0.0
        try:
            source_type = job.get("source_type") or "github"
            if source_type == "github" and job.get("repository") not in self.trusted_repositories:
                raise ExecutionError("repository is not in the Runner trusted-repository allowlist")
            if source_type not in ("github", "local"):
                raise ExecutionError("unsupported job source type")
            self.workspaces.create(job_id, worker_id)
            allocated = True
            self.client.append_log(job_id, "Runner claimed job; workspace allocated", "system")
            if source_type == "local":
                source = self._prepare_local_source(job, job_id, worker_id)
                self.client.append_log(
                    job_id,
                    "Materialized and verified Local Project snapshot " + str(job.get("snapshot_sha256")),
                    "system",
                )
            else:
                source = self.checkout_provider.checkout(
                    job_id, worker_id, job["repository"], job["commit_sha"]
                )
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

            self.executor.log = lambda stream, message: self.client.append_log(job_id, message, stream)
            build = self.executor.run(
                job_id, worker_id, job["target"],
                cancel_requested=cancellation_requested,
            )
            outcome = build.outcome
            error_code = build.error_code
            result = {
                "source_type": source_type,
                "command": list(build.command),
                "return_code": build.return_code,
                "duration_seconds": build.duration_seconds,
                "output_bytes": build.output_bytes,
                "source_directory": str(source.relative_to(self.workspaces.get(job_id, worker_id))),
            }
            if source_type == "local":
                result["local_project_id"] = job["local_project_id"]
                result["snapshot_sha256"] = job["snapshot_sha256"]
            self.client.append_log(
                job_id,
                f"Flutter execution {outcome}; exit={build.return_code}; "
                f"duration={build.duration_seconds}s; output={build.output_bytes} bytes",
                "system",
            )
            if outcome == "succeeded":
                artifact = self.artifact_packager.package(job_id, worker_id, job["target"])
                if artifact is not None:
                    artifact_path, artifact_name = artifact
                    metadata = self.client.upload_artifact(job_id, str(artifact_path), artifact_name)
                    result["artifact"] = metadata
                    self.client.append_log(
                        job_id, f"Artifact stored: {artifact_name} ({metadata['size']} bytes)", "system"
                    )
                error_code = None
        except (ArtifactPackageError, CheckoutError, ExecutionError, WorkspaceError, LocalProjectError) as exc:
            self.client.append_log(
                job_id, f"Runner rejected job safely: {type(exc).__name__}", "stderr"
            )
            result = {"error": type(exc).__name__}
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
            if allocated:
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
