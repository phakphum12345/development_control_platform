"""Loopback-only static application runtime supervision for DCP.

Only already-built static output is served. This module never executes project
code, binds a public interface, creates infrastructure, or exposes host paths.
The returned session token is a capability for a later authenticated Preview
Proxy integration; this module alone is not a browser-facing authorization API.
"""
from __future__ import annotations

import hmac
import os
import secrets
import shutil
import signal
import stat
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .workspace import WorkspaceError, WorkspaceManager


class RuntimeErrorDCP(RuntimeError):
    """Runtime start, stop, or session validation failure."""


@dataclass
class _Runtime:
    runtime_id: str
    job_id: str
    worker_id: str
    port: int
    root: Path
    runtime_kind: str
    process: subprocess.Popen
    log_path: Path
    token: str
    expires_at: float
    started_at: str


class RuntimeManager:
    """Supervise static build previews on loopback with expiring owner capabilities."""

    def __init__(self, workspaces: WorkspaceManager, *, max_active: int = 4,
                 session_ttl_seconds: int = 1800, startup_timeout_seconds: int = 10,
                 max_log_bytes: int = 2 * 1024 * 1024):
        for name, value, low, high in (
            ("max_active", max_active, 1, 64),
            ("session_ttl_seconds", session_ttl_seconds, 60, 86400),
            ("startup_timeout_seconds", startup_timeout_seconds, 1, 60),
            ("max_log_bytes", max_log_bytes, 1024, 20 * 1024 * 1024),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name} is outside its allowed range")
        self.workspaces = workspaces
        self.max_active = max_active
        self.session_ttl_seconds = session_ttl_seconds
        self.startup_timeout_seconds = startup_timeout_seconds
        self.max_log_bytes = max_log_bytes
        self._runtimes: dict[str, _Runtime] = {}

    @staticmethod
    def _safe_output(workspace: Path, output_relative: str) -> Path:
        if output_relative not in ("source/dist", "source/dist/browser", "source/build/web", "dist", "dist/browser", "build/web"):
            raise RuntimeErrorDCP("unsupported build output directory")
        candidate = workspace / output_relative
        current = workspace
        for part in Path(output_relative).parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeErrorDCP("runtime output path contains a symlink")
        if not candidate.is_dir():
            raise RuntimeErrorDCP("built application output is missing")
        resolved = candidate.resolve(strict=True)
        if resolved != workspace and workspace not in resolved.parents:
            raise RuntimeErrorDCP("runtime output escaped its job workspace")
        index = candidate / "index.html"
        if index.is_symlink() or not index.is_file():
            raise RuntimeErrorDCP("built application must contain a regular index.html")
        for current_dir, dirs, files in os.walk(candidate, followlinks=False):
            base = Path(current_dir)
            for name in dirs:
                if (base / name).is_symlink():
                    raise RuntimeErrorDCP("runtime output contains a symlink directory")
            for name in files:
                item = base / name
                if not item.is_file() or item.is_symlink():
                    raise RuntimeErrorDCP("runtime output contains an unsafe file")
        return resolved

    @staticmethod
    def _allocate_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if process.poll() is None:
            if os.name == "nt":
                taskkill = shutil.which("taskkill")
                if taskkill:
                    subprocess.run(
                        [taskkill, "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=10, check=False,
                    )
                else:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def start_static(self, job_id: str, worker_id: str, *,
                     output_relative: str = "source/dist") -> dict:
        """Start an already-built static app; no project code or shell is executed."""
        try:
            workspace = self.workspaces.get(job_id, worker_id)
            self.workspaces.check_quota(job_id, worker_id)
        except WorkspaceError:
            raise RuntimeErrorDCP("job workspace is not safe or available") from None
        self.reap_expired()
        if len(self._runtimes) >= self.max_active:
            raise RuntimeErrorDCP("active runtime limit reached")
        root = self._safe_output(workspace, output_relative)
        port = self._allocate_port()
        runtime_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        log_dir = workspace / ".dcp-runtime"
        if log_dir.is_symlink() or (log_dir.exists() and not log_dir.is_dir()):
            raise RuntimeErrorDCP("runtime log directory is unsafe")
        log_dir.mkdir(mode=0o700, exist_ok=True)
        log_path = log_dir / f"{runtime_id}.log"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(log_path, flags, 0o600)
        log_handle = os.fdopen(fd, "wb")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(workspace / ".runner-home"),
            "USERPROFILE": str(workspace / ".runner-home"),
            "TMPDIR": str(workspace / ".tmp"),
            "TEMP": str(workspace / ".tmp"),
            "TMP": str(workspace / ".tmp"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT"):
            if os.name == "nt" and os.environ.get(key):
                env[key] = os.environ[key]
        (workspace / ".runner-home").mkdir(mode=0o700, exist_ok=True)
        (workspace / ".tmp").mkdir(mode=0o700, exist_ok=True)
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "http.server", str(port),
                 "--bind", "127.0.0.1", "--directory", str(root)],
                cwd=str(workspace), env=env, stdin=subprocess.DEVNULL,
                stdout=log_handle, stderr=subprocess.STDOUT, shell=False,
                close_fds=True, start_new_session=(os.name != "nt"),
                creationflags=flags,
            )
        except OSError:
            log_handle.close()
            log_path.unlink(missing_ok=True)
            raise RuntimeErrorDCP("local static runtime could not be started") from None
        finally:
            if not log_handle.closed:
                log_handle.close()

        deadline = time.monotonic() + self.startup_timeout_seconds
        healthy = False
        url = f"http://127.0.0.1:{port}/"
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with urllib.request.urlopen(url, timeout=0.5) as response:
                    healthy = response.status == 200 and "text/html" in response.headers.get("Content-Type", "")
                if healthy:
                    break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        if not healthy:
            self._terminate(process)
            log_path.unlink(missing_ok=True)
            raise RuntimeErrorDCP("local static runtime failed its health check")

        expires = time.monotonic() + self.session_ttl_seconds
        row = _Runtime(
            runtime_id, job_id, worker_id, port, root, "static", process, log_path, token,
            expires, datetime.now(timezone.utc).isoformat(),
        )
        self._runtimes[runtime_id] = row
        return {
            "runtime_id": runtime_id, "job_id": job_id, "runtime_kind": "static", "state": "running",
            "url": url, "port": port, "expires_in_seconds": self.session_ttl_seconds,
            "session_token": token, "started_at": row.started_at,
            "bind_host": "127.0.0.1",
        }


    @staticmethod
    def _safe_next_output(workspace: Path) -> Path:
        source = workspace / "source"
        output = source / ".next"
        if source.is_symlink() or output.is_symlink() or not output.is_dir():
            raise RuntimeErrorDCP("Next.js build output is missing or unsafe")
        build_id = output / "BUILD_ID"
        if build_id.is_symlink() or not build_id.is_file():
            raise RuntimeErrorDCP("Next.js production BUILD_ID is missing or unsafe")
        resolved = output.resolve(strict=True)
        if workspace not in resolved.parents:
            raise RuntimeErrorDCP("Next.js build output escaped its job workspace")
        for current_dir, dirs, files in os.walk(output, followlinks=False):
            base = Path(current_dir)
            if any((base / name).is_symlink() for name in dirs + files):
                raise RuntimeErrorDCP("Next.js build output contains a symlink")
        return resolved

    def start_next(self, job_id: str, worker_id: str, *, owner_approved: bool = False) -> dict:
        """Start a trusted, already-built Next.js server after explicit Owner approval."""
        if owner_approved is not True:
            raise RuntimeErrorDCP("explicit Owner approval is required to run the Next.js server")
        try:
            workspace = self.workspaces.get(job_id, worker_id)
            self.workspaces.check_quota(job_id, worker_id)
        except WorkspaceError:
            raise RuntimeErrorDCP("job workspace is not safe or available") from None
        self.reap_expired()
        if len(self._runtimes) >= self.max_active:
            raise RuntimeErrorDCP("active runtime limit reached")
        root = self._safe_next_output(workspace)
        source = workspace / "source"
        package = source / "package.json"
        if package.is_symlink() or not package.is_file():
            raise RuntimeErrorDCP("Next.js package manifest is missing or unsafe")
        try:
            package_info = package.lstat()
            if not stat.S_ISREG(package_info.st_mode) or package_info.st_size > 1024 * 1024:
                raise RuntimeErrorDCP("Next.js package manifest is not a bounded regular file")
            import json
            manifest = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RuntimeErrorDCP("Next.js package manifest is invalid") from None
        if not isinstance(manifest, dict):
            raise RuntimeErrorDCP("Next.js package manifest must be an object")
        dependencies = {}
        for group in ("dependencies", "devDependencies", "optionalDependencies"):
            values = manifest.get(group, {})
            if isinstance(values, dict):
                dependencies.update(values)
        if not {"next", "react"}.issubset({str(name).lower() for name in dependencies}):
            raise RuntimeErrorDCP("preinstalled Next.js and React dependencies are required")
        cli = source / "node_modules" / "next" / "dist" / "bin" / "next"
        parents = ("node_modules", "node_modules/next", "node_modules/next/dist", "node_modules/next/dist/bin")
        if (cli.is_symlink() or not cli.is_file()
                or any((source / part).is_symlink() for part in parents)):
            raise RuntimeErrorDCP("preinstalled local Next.js CLI is missing or unsafe")
        node = shutil.which("node")
        if not node:
            raise RuntimeErrorDCP("Node.js executable is unavailable")

        port = self._allocate_port()
        runtime_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        log_dir = workspace / ".dcp-runtime"
        if log_dir.is_symlink() or (log_dir.exists() and not log_dir.is_dir()):
            raise RuntimeErrorDCP("runtime log directory is unsafe")
        log_dir.mkdir(mode=0o700, exist_ok=True)
        log_path = log_dir / f"{runtime_id}.log"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(log_path, flags, 0o600)
        log_handle = os.fdopen(fd, "wb")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(workspace / ".runner-home"),
            "USERPROFILE": str(workspace / ".runner-home"),
            "TMPDIR": str(workspace / ".tmp"),
            "TEMP": str(workspace / ".tmp"),
            "TMP": str(workspace / ".tmp"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "NODE_ENV": "production",
            "NEXT_TELEMETRY_DISABLED": "1",
        }
        for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT"):
            if os.name == "nt" and os.environ.get(key):
                env[key] = os.environ[key]
        (workspace / ".runner-home").mkdir(mode=0o700, exist_ok=True)
        (workspace / ".tmp").mkdir(mode=0o700, exist_ok=True)
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                [node, str(cli), "start", "--hostname", "127.0.0.1", "--port", str(port)],
                cwd=str(source), env=env, stdin=subprocess.DEVNULL,
                stdout=log_handle, stderr=subprocess.STDOUT, shell=False,
                close_fds=True, start_new_session=(os.name != "nt"),
                creationflags=flags,
            )
        except OSError:
            log_handle.close()
            log_path.unlink(missing_ok=True)
            raise RuntimeErrorDCP("local Next.js runtime could not be started") from None
        finally:
            if not log_handle.closed:
                log_handle.close()

        deadline = time.monotonic() + self.startup_timeout_seconds
        healthy = False
        url = f"http://127.0.0.1:{port}/"
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with urllib.request.urlopen(url, timeout=0.5) as response:
                    healthy = 200 <= response.status < 500
                if healthy:
                    break
            except urllib.error.HTTPError as exc:
                healthy = 200 <= exc.code < 500
                if healthy:
                    break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        if not healthy:
            self._terminate(process)
            log_path.unlink(missing_ok=True)
            raise RuntimeErrorDCP("Next.js runtime failed its loopback health check")

        expires = time.monotonic() + self.session_ttl_seconds
        row = _Runtime(
            runtime_id, job_id, worker_id, port, root, "next", process, log_path, token,
            expires, datetime.now(timezone.utc).isoformat(),
        )
        self._runtimes[runtime_id] = row
        return {
            "runtime_id": runtime_id, "job_id": job_id, "runtime_kind": "next",
            "state": "running", "url": url, "port": port,
            "expires_in_seconds": self.session_ttl_seconds,
            "session_token": token, "started_at": row.started_at,
            "bind_host": "127.0.0.1",
        }

    def _authorized(self, runtime_id: str, session_token: str) -> _Runtime:
        row = self._runtimes.get(runtime_id)
        if row is None:
            raise RuntimeErrorDCP("runtime not found")
        if not isinstance(session_token, str) or not hmac.compare_digest(row.token, session_token):
            raise RuntimeErrorDCP("runtime session authorization failed")
        if time.monotonic() >= row.expires_at:
            self._stop_row(row)
            raise RuntimeErrorDCP("runtime session expired")
        return row

    def status(self, runtime_id: str, session_token: str) -> dict:
        row = self._authorized(runtime_id, session_token)
        running = row.process.poll() is None
        return {
            "runtime_id": row.runtime_id, "job_id": row.job_id,
            "runtime_kind": row.runtime_kind,
            "state": "running" if running else "exited",
            "port": row.port, "bind_host": "127.0.0.1",
            "expires_in_seconds": max(0, int(row.expires_at - time.monotonic())),
        }

    def logs(self, runtime_id: str, session_token: str) -> str:
        row = self._authorized(runtime_id, session_token)
        if row.log_path.is_symlink() or not row.log_path.is_file():
            raise RuntimeErrorDCP("runtime log is unavailable")
        with row.log_path.open("rb") as handle:
            handle.seek(max(0, row.log_path.stat().st_size - self.max_log_bytes))
            return handle.read(self.max_log_bytes).decode("utf-8", "replace")

    def _stop_row(self, row: _Runtime) -> None:
        self._terminate(row.process)
        self._runtimes.pop(row.runtime_id, None)

    def stop(self, runtime_id: str, session_token: str) -> dict:
        row = self._authorized(runtime_id, session_token)
        self._stop_row(row)
        return {"runtime_id": runtime_id, "state": "stopped"}

    def reap_expired(self) -> int:
        now = time.monotonic()
        expired = [row for row in self._runtimes.values() if now >= row.expires_at or row.process.poll() is not None]
        for row in expired:
            self._stop_row(row)
        return len(expired)

    def list_for_job(self, job_id: str, worker_id: str) -> list[dict]:
        self.workspaces.get(job_id, worker_id)
        return [{
            "runtime_id": row.runtime_id, "job_id": row.job_id,
            "runtime_kind": row.runtime_kind,
            "state": "running" if row.process.poll() is None else "exited",
            "port": row.port, "bind_host": "127.0.0.1",
            "started_at": row.started_at,
        } for row in self._runtimes.values() if row.job_id == job_id and row.worker_id == worker_id]
