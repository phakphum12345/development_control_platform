"""Fixed-template, read-only Terminal executor for registered Project Workspaces.

The browser never supplies an executable, argv, cwd, environment, or shell.
The executor resolves a trusted catalog entry and receives a path only from the
Runner's LocalProjectRegistry after workspace/snapshot verification.
"""
from __future__ import annotations

import os
import queue
import re
import shutil
import tempfile
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tools.cloud_gateway.terminal_catalog import preview_template
from tools.cloud_gateway.terminal_execution_contract import template_version_digest


class TerminalExecutionError(RuntimeError):
    """A Terminal job was rejected or failed its bounded execution policy."""


@dataclass(frozen=True)
class TerminalExecutionResult:
    outcome: str
    command: tuple[str, ...]
    return_code: int | None
    duration_seconds: float
    output_bytes: int
    error_code: str | None = None


_EXECUTABLES = frozenset({"git", "python", "node"})
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|secret|token|private[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)
_SECRET_TOKEN = re.compile(
    r"(?i)(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._~+/-]{16,})"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)


def redact_terminal_output(value: str) -> str:
    """Redact common credential formats before any output reaches durable logs."""
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
    text = _SECRET_ASSIGNMENT.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", text)
    return _SECRET_TOKEN.sub("[REDACTED TOKEN]", text)


class TerminalScriptExecutor:
    """Run only catalog-defined read-only scripts in a trusted project directory."""

    def __init__(
        self, *, enabled: bool = False, timeout_ceiling_seconds: int = 60,
        output_ceiling_bytes: int = 1024 * 1024,
        log: Callable[[str, str], None] | None = None,
    ):
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        if (isinstance(timeout_ceiling_seconds, bool)
                or not isinstance(timeout_ceiling_seconds, int)
                or not 1 <= timeout_ceiling_seconds <= 300):
            raise ValueError("timeout ceiling must be between 1 and 300 seconds")
        if (isinstance(output_ceiling_bytes, bool)
                or not isinstance(output_ceiling_bytes, int)
                or not 1024 <= output_ceiling_bytes <= 5 * 1024 * 1024):
            raise ValueError("output ceiling must be between 1 KiB and 5 MiB")
        self.enabled = enabled
        self.timeout_ceiling_seconds = timeout_ceiling_seconds
        self.output_ceiling_bytes = output_ceiling_bytes
        self.log = log or (lambda stream, message: None)

    @staticmethod
    def _trusted_directory(value: str | os.PathLike) -> Path:
        raw = Path(value).expanduser()
        if not raw.is_absolute():
            raise TerminalExecutionError("Project Workspace path must be absolute")
        current = Path(raw.anchor)
        for part in raw.parts[1:]:
            current = current / part
            try:
                if current.is_symlink() or (
                    hasattr(current, "is_junction") and current.is_junction()
                ):
                    raise TerminalExecutionError("Project Workspace path contains a link")
            except OSError:
                raise TerminalExecutionError("Project Workspace path cannot be inspected") from None
        try:
            resolved = raw.resolve(strict=True)
        except (OSError, RuntimeError):
            raise TerminalExecutionError("Project Workspace is unavailable") from None
        if resolved != raw or not resolved.is_dir():
            raise TerminalExecutionError("Project Workspace is not a canonical directory")
        return resolved

    @staticmethod
    def _environment(template: dict, job_home: Path) -> dict[str, str]:
        allowed = set(template.get("environment_allowlist", []))
        if not allowed.issubset({"PATH", "HOME", "USERPROFILE", "SYSTEMROOT"}):
            raise TerminalExecutionError("Terminal template requests an unsupported environment variable")
        env: dict[str, str] = {}
        for name in allowed:
            if name == "PATH":
                value = os.environ.get("PATH", "")
                if value:
                    env[name] = value
            elif name in ("HOME", "USERPROFILE"):
                env[name] = str(job_home)
            elif name == "SYSTEMROOT":
                value = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
                if value:
                    env[name] = value
        # Fixed, non-user-controlled safety settings for read-only Git inspection.
        if template["executable"] == "git":
            env["GIT_OPTIONAL_LOCKS"] = "0"
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["CI"] = "true"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        return env

    @staticmethod
    def _terminate_tree(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, check=False, timeout=5,
                    shell=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def run(
        self, job_id: str, worker_id: str, workspace_path: str | os.PathLike,
        template_id: str, parameters: dict, expected_template_digest: str,
        *, cancel_requested: Callable[[], bool] | None = None,
    ) -> TerminalExecutionResult:
        if not self.enabled:
            raise TerminalExecutionError("Terminal execution is disabled on this Runner")
        workspace = self._trusted_directory(workspace_path)
        try:
            template = preview_template(template_id, parameters)
        except (ValueError, TypeError) as exc:
            raise TerminalExecutionError(str(exc)) from None
        if (template.get("execution_enabled") is not True
                or template.get("mutation_class") != "read-only"
                or template.get("network") != "denied"
                or template.get("approval_required") is not False
                or template.get("working_directory_policy") != "assigned_workspace_required"):
            raise TerminalExecutionError("Terminal template is not enabled for the read-only execution policy")
        if template_version_digest(template_id, parameters) != expected_template_digest:
            raise TerminalExecutionError("Terminal template version changed after authorization")
        executable = template.get("executable")
        argv = template.get("argv")
        if (executable not in _EXECUTABLES or not isinstance(argv, list)
                or len(argv) > 32 or any(not isinstance(arg, str) or "\x00" in arg for arg in argv)):
            raise TerminalExecutionError("Terminal template resolved an unsafe command")
        resolved = shutil.which(executable)
        if not resolved or not Path(resolved).is_file():
            raise TerminalExecutionError("Required Terminal executable is unavailable")
        job_home = Path(tempfile.mkdtemp(prefix="dcp-terminal-home-"))
        try:
            if os.name == "posix":
                os.chmod(job_home, 0o700)
        except OSError:
            shutil.rmtree(job_home, ignore_errors=True)
            raise TerminalExecutionError("Temporary Terminal environment could not be secured") from None
        env = self._environment(template, job_home)
        timeout = min(int(template["timeout_seconds"]), self.timeout_ceiling_seconds)
        output_limit = min(int(template["max_output_bytes"]), self.output_ceiling_bytes)
        command = [resolved, *argv]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command, cwd=str(workspace), env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False,
                close_fds=True, start_new_session=(os.name != "nt"),
                creationflags=creationflags, bufsize=0,
            )
        except OSError:
            shutil.rmtree(job_home, ignore_errors=True)
            raise TerminalExecutionError("Terminal executable could not be started") from None

        chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=8)

        def read_output():
            try:
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    chunks.put(chunk)
            finally:
                chunks.put(None)

        reader = threading.Thread(target=read_output, name="dcp-terminal-output", daemon=True)
        reader.start()
        output_bytes = 0
        output_exceeded = False
        timed_out = False
        cancelled = False
        reader_done = False
        deadline = started + timeout
        while not reader_done or process.poll() is None:
            if process.poll() is None:
                if cancel_requested is not None and cancel_requested():
                    cancelled = True
                    self._terminate_tree(process)
                elif time.monotonic() >= deadline:
                    timed_out = True
                    self._terminate_tree(process)
            try:
                chunk = chunks.get(timeout=0.05)
            except queue.Empty:
                continue
            if chunk is None:
                reader_done = True
                continue
            remaining = max(0, output_limit - output_bytes)
            accepted = chunk[:remaining]
            output_bytes += len(accepted)
            if accepted:
                self.log("stdout", accepted.decode("utf-8", errors="replace"))
            if len(accepted) != len(chunk):
                output_exceeded = True
                self._terminate_tree(process)
        try:
            return_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._terminate_tree(process)
            return_code = process.wait(timeout=5)
        reader.join(timeout=2)
        duration = round(time.monotonic() - started, 3)
        if cancelled:
            outcome, error = "cancelled", "TERMINAL_CANCELLED"
        elif timed_out:
            outcome, error = "failed", "TERMINAL_TIMEOUT"
        elif output_exceeded:
            outcome, error = "failed", "TERMINAL_OUTPUT_LIMIT"
        elif return_code != 0:
            outcome, error = "failed", "TERMINAL_EXIT_NONZERO"
        else:
            outcome, error = "succeeded", None
        self.log("system", f"Terminal execution {outcome}; exit={return_code}; duration={duration}s; output={output_bytes} bytes")
        return TerminalExecutionResult(
            outcome=outcome, command=tuple(command), return_code=return_code,
            duration_seconds=duration, output_bytes=output_bytes, error_code=error,
        )
