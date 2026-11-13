"""Fixed-template, read-only Terminal executor for registered Project Workspaces.

The browser never supplies an executable, argv, cwd, environment, or shell.
The executor resolves a trusted catalog entry and receives a path only from the
Runner's LocalProjectRegistry after workspace/snapshot verification.
"""
from __future__ import annotations

import codecs
import os
import queue
import re
import shutil
import tempfile
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
_INCOMPLETE_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*\Z",
    re.DOTALL,
)
_TAIL_SECRET_PREFIX = re.compile(
    r"(?i)(?:gh[pousr]_[A-Za-z0-9]{0,19}|github_pat_[A-Za-z0-9_]{0,19}|"
    r"sk-[A-Za-z0-9_-]{0,19}|xox[baprs]-[A-Za-z0-9-]{0,9}|"
    r"Bearer\s+[A-Za-z0-9._~+/-]{0,15})$"
)


def redact_terminal_output(value: str) -> str:
    """Redact complete credentials and partial credential prefixes at bounded EOF."""
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
    text = _INCOMPLETE_PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", text)
    text = _SECRET_TOKEN.sub("[REDACTED TOKEN]", text)
    return _TAIL_SECRET_PREFIX.sub("[REDACTED TOKEN PREFIX]", text)


class TerminalOutputRedactor:
    """Redact complete output lines so secrets split across pipe chunks are not leaked."""

    def __init__(self):
        self._buffer = ""
        self._inside_private_key = False

    def feed(self, value: str, *, final: bool = False) -> str:
        self._buffer += value
        lines = self._buffer.splitlines(keepends=True)
        self._buffer = ""
        if not final and lines and not lines[-1].endswith(("\n", "\r")):
            self._buffer = lines.pop()
        output = []
        for line in lines:
            if self._inside_private_key:
                if "-----END " in line and "PRIVATE KEY-----" in line:
                    self._inside_private_key = False
                continue
            if "-----BEGIN " in line and "PRIVATE KEY-----" in line:
                output.append("[REDACTED PRIVATE KEY]\n")
                if not ("-----END " in line and "PRIVATE KEY-----" in line):
                    self._inside_private_key = True
                continue
            output.append(redact_terminal_output(line))
        if final and self._buffer:
            line, self._buffer = self._buffer, ""
            if self._inside_private_key:
                if "-----END " in line and "PRIVATE KEY-----" in line:
                    self._inside_private_key = False
            elif "-----BEGIN " in line and "PRIVATE KEY-----" in line:
                output.append("[REDACTED PRIVATE KEY]")
                if not ("-----END " in line and "PRIVATE KEY-----" in line):
                    self._inside_private_key = True
            else:
                output.append(redact_terminal_output(line))
        return "".join(output)


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
    def _safe_path(workspace: Path) -> str:
        entries = []
        for raw_entry in os.environ.get("PATH", "").split(os.pathsep):
            if not raw_entry:
                continue
            try:
                candidate = Path(raw_entry).expanduser().resolve(strict=True)
                if not candidate.is_dir():
                    continue
                candidate.relative_to(workspace)
                continue
            except ValueError:
                pass
            except (OSError, RuntimeError):
                continue
            entries.append(str(candidate))
        return os.pathsep.join(entries)

    @staticmethod
    def _environment(template: dict, job_home: Path, safe_path: str) -> dict[str, str]:
        allowed = set(template.get("environment_allowlist", []))
        if not allowed.issubset({"PATH", "HOME", "USERPROFILE", "SYSTEMROOT"}):
            raise TerminalExecutionError("Terminal template requests an unsupported environment variable")
        env: dict[str, str] = {}
        for name in allowed:
            if name == "PATH":
                if safe_path:
                    env[name] = safe_path
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
            env["GIT_ATTR_NOSYSTEM"] = "1"
            env["GIT_PAGER"] = "cat"
            env["PAGER"] = "cat"
            # Environment config is applied after repository-local config. This
            # prevents a project-controlled fsmonitor hook or external diff/pager
            # helper from running during otherwise read-only Git inspection.
            git_config = (
                ("core.fsmonitor", "false"),
                ("diff.external", ""),
                ("core.pager", "cat"),
                ("pager.diff", "false"),
                ("pager.log", "false"),
                ("pager.show", "false"),
            )
            env["GIT_CONFIG_COUNT"] = str(len(git_config))
            for index, (key, value) in enumerate(git_config):
                env[f"GIT_CONFIG_KEY_{index}"] = key
                env[f"GIT_CONFIG_VALUE_{index}"] = value
        system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
        if system_root:
            env["SYSTEMROOT"] = system_root
        env["CI"] = "true"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        return env

    @staticmethod
    def _build_command(resolved: str, executable: str, argv: list[str]) -> list[str]:
        """Build argv while disabling Git hooks/helpers that can execute project config."""
        if executable != "git":
            return [resolved, *argv]
        if not argv:
            raise TerminalExecutionError("Git template did not provide a subcommand")
        command_args = list(argv)
        if command_args[0] in {"diff", "show"}:
            command_args = [
                command_args[0], "--no-ext-diff", "--no-textconv",
                *(arg for arg in command_args[1:] if arg not in {"--no-ext-diff", "--no-textconv"}),
            ]
        return [resolved, *command_args]

    @staticmethod
    def _disable_repository_filters(
        resolved: str, workspace: Path, env: dict[str, str]
    ) -> None:
        """Disable repository-defined clean/smudge/process filters before Git inspection."""
        try:
            result = subprocess.run(
                [resolved, "config", "--name-only", "--null", "--list"],
                cwd=str(workspace), env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                shell=False, close_fds=True, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise TerminalExecutionError(
                "Git repository filter configuration could not be inspected safely"
            ) from None
        if result.returncode != 0:
            raise TerminalExecutionError(
                "Git repository filter configuration could not be inspected safely"
            )

        drivers: dict[str, str] = {}
        for raw_key in result.stdout.split(b"\\0"):
            if not raw_key:
                continue
            key = raw_key.decode("utf-8", "replace")
            section, separator, setting = key.rpartition(".")
            if not separator or setting.casefold() not in {"clean", "smudge", "process", "required"}:
                continue
            if not section.casefold().startswith("filter."):
                continue
            driver = section[len("filter."):]
            if driver:
                drivers.setdefault(driver.casefold(), driver)

        index = int(env.get("GIT_CONFIG_COUNT", "0"))
        for driver in drivers.values():
            for setting, value in (
                ("clean", ""), ("smudge", ""), ("process", ""), ("required", "false")
            ):
                env[f"GIT_CONFIG_KEY_{index}"] = f"filter.{driver}.{setting}"
                env[f"GIT_CONFIG_VALUE_{index}"] = value
                index += 1
        env["GIT_CONFIG_COUNT"] = str(index)

    @staticmethod
    def _log_chunks(value: str, max_bytes: int = 7000):
        current = []
        current_bytes = 0
        for char in value:
            size = len(char.encode("utf-8"))
            if current and current_bytes + size > max_bytes:
                yield "".join(current)
                current = []
                current_bytes = 0
            current.append(char)
            current_bytes += size
        if current:
            yield "".join(current)

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
        safe_path = self._safe_path(workspace)
        resolved = shutil.which(executable, path=safe_path)
        if not resolved:
            raise TerminalExecutionError("Required Terminal executable is unavailable")
        resolved_path = Path(resolved).resolve(strict=True)
        if (not resolved_path.is_file() or resolved_path.suffix.lower() in (".bat", ".cmd")):
            raise TerminalExecutionError("Terminal executable is not a trusted native binary")
        try:
            resolved_path.relative_to(workspace)
            raise TerminalExecutionError("Terminal executable cannot be loaded from the Project Workspace")
        except ValueError:
            pass
        resolved = str(resolved_path)
        job_home = Path(tempfile.mkdtemp(prefix="dcp-terminal-home-"))
        try:
            job_home = job_home.resolve(strict=True)
            try:
                job_home.relative_to(workspace)
            except ValueError:
                pass
            else:
                shutil.rmtree(job_home, ignore_errors=True)
                raise TerminalExecutionError(
                    "Temporary Terminal HOME must be outside the Project Workspace"
                )
            if os.name == "posix":
                os.chmod(job_home, 0o700)
        except OSError:
            shutil.rmtree(job_home, ignore_errors=True)
            raise TerminalExecutionError("Temporary Terminal environment could not be secured") from None
        env = self._environment(template, job_home, safe_path)
        if executable == "git":
            try:
                self._disable_repository_filters(resolved, workspace, env)
            except TerminalExecutionError:
                shutil.rmtree(job_home, ignore_errors=True)
                raise
        timeout = min(int(template["timeout_seconds"]), self.timeout_ceiling_seconds)
        output_limit = min(int(template["max_output_bytes"]), self.output_ceiling_bytes)
        command = self._build_command(resolved, executable, argv)
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
        decoder = codecs.getincrementaldecoder("utf-8")()
        redactor = TerminalOutputRedactor()
        output_exceeded = False
        timed_out = False
        cancelled = False
        reader_done = False
        deadline = started + timeout
        try:
            while not reader_done or process.poll() is None:
                if process.poll() is None:
                    try:
                        should_cancel = cancel_requested is not None and cancel_requested()
                    except Exception:
                        raise TerminalExecutionError("Runner could not renew the active Job lease") from None
                    if should_cancel:
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
                    # The decoder preserves UTF-8 across pipe chunks. The redactor
                    # buffers incomplete lines/private-key blocks before emitting
                    # safe text, so credentials split across chunks are never logged.
                    decoded = decoder.decode(accepted, final=False)
                    safe_text = redactor.feed(decoded)
                    for message in self._log_chunks(safe_text, max_bytes=4096):
                        self.log("stdout", message)
                if len(accepted) != len(chunk):
                    output_exceeded = True
                    self._terminate_tree(process)
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._terminate_tree(process)
                return_code = process.wait(timeout=5)
            reader.join(timeout=2)
            decoded_tail = decoder.decode(b"", final=True)
            safe_tail = redactor.feed(decoded_tail, final=True)
            for message in self._log_chunks(safe_tail, max_bytes=4096):
                self.log("stdout", message)
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
        except Exception:
            self._terminate_tree(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            while reader.is_alive():
                try:
                    chunks.get(timeout=0.05)
                except queue.Empty:
                    pass
            reader.join(timeout=1)
            raise
        finally:
            shutil.rmtree(job_home, ignore_errors=True)
