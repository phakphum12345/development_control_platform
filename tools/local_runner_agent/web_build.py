"""Local-first static and Vite build adapters for trusted projects.

No dependency installation or package-manager lifecycle scripts are run.
Vite config and application build code are executable project code, therefore
this adapter remains behind the Runner's explicit execution opt-in and trusted
repository allowlist.
"""
from __future__ import annotations

import os
import re
import queue
import shutil
import signal
import stat
import subprocess
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .execution import BuildResult, ExecutionError
from .workspace import WorkspaceManager


class WebBuildExecutor:
    TARGETS = {"build_static_web", "build_vite", "build_next", "build_angular"}

    def __init__(self, workspace_manager: WorkspaceManager, *, enabled: bool = False,
                 timeout_seconds: int = 1800, max_output_bytes: int = 5 * 1024 * 1024,
                 max_artifact_bytes: int = 100 * 1024 * 1024,
                 log: Callable[[str, str], None] | None = None):
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 7200:
            raise ValueError("timeout_seconds must be between 1 and 7200")
        if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or not 1024 <= max_output_bytes <= 50 * 1024 * 1024:
            raise ValueError("max_output_bytes must be between 1 KiB and 50 MiB")
        if isinstance(max_artifact_bytes, bool) or not isinstance(max_artifact_bytes, int) or not 1024 <= max_artifact_bytes <= 1024 * 1024 * 1024:
            raise ValueError("max_artifact_bytes must be between 1 KiB and 1 GiB")
        self.workspaces = workspace_manager
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.max_artifact_bytes = max_artifact_bytes
        self.log = log or (lambda stream, message: None)

    @staticmethod
    def command_for(target: str, source: Path) -> tuple[str, ...]:
        if target == "build_static_web":
            if not (source / "index.html").is_file():
                raise ExecutionError("static web project requires a root index.html")
            return ("static-copy",)
        if target in {"build_vite", "build_next", "build_angular"}:
            package = source / "package.json"
            if package.is_symlink() or not package.is_file():
                raise ExecutionError("package.json is missing or unsafe")
            try:
                package_info = package.lstat()
                if not stat.S_ISREG(package_info.st_mode) or package_info.st_size > 1024 * 1024:
                    raise ExecutionError("package.json is not a bounded regular file")
                import json
                data = json.loads(package.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ExecutionError("package.json is invalid or unavailable") from None
            if not isinstance(data, dict):
                raise ExecutionError("package.json must contain an object")
            deps = {}
            for group in ("dependencies", "devDependencies", "optionalDependencies"):
                values = data.get(group, {})
                if isinstance(values, dict):
                    deps.update(values)
            names = {str(name).lower() for name in deps}
            node = shutil.which("node")
            if not node:
                raise ExecutionError("Node.js executable is unavailable")

            if target == "build_vite":
                cli = source / "node_modules" / "vite" / "bin" / "vite.js"
                parents = ("node_modules", "node_modules/vite", "node_modules/vite/bin")
                if ("vite" not in names or not ({"react", "react-dom", "vue"} & names)
                        or cli.is_symlink() or not cli.is_file()
                        or any((source / part).is_symlink() for part in parents)):
                    raise ExecutionError("preinstalled Vite CLI and React/Vue dependencies are required")
                return (node, str(cli), "build")

            if target == "build_next":
                cli = source / "node_modules" / "next" / "dist" / "bin" / "next"
                parents = ("node_modules", "node_modules/next", "node_modules/next/dist", "node_modules/next/dist/bin")
                if ("next" not in names or "react" not in names
                        or cli.is_symlink() or not cli.is_file()
                        or any((source / part).is_symlink() for part in parents)):
                    raise ExecutionError("preinstalled Next.js CLI and React dependencies are required")
                return (node, str(cli), "build")

            cli = source / "node_modules" / "@angular" / "cli" / "bin" / "ng.js"
            parents = ("node_modules", "node_modules/@angular", "node_modules/@angular/cli",
                       "node_modules/@angular/cli/bin")
            if ("@angular/core" not in names or "@angular/cli" not in names
                    or cli.is_symlink() or not cli.is_file()
                    or any((source / part).is_symlink() for part in parents)):
                raise ExecutionError("preinstalled Angular CLI and Angular core dependencies are required")
            angular_file = source / "angular.json"
            if angular_file.is_symlink() or not angular_file.is_file():
                raise ExecutionError("angular.json is missing or unsafe")
            try:
                angular_info = angular_file.lstat()
                if not stat.S_ISREG(angular_info.st_mode) or angular_info.st_size > 1024 * 1024:
                    raise ExecutionError("angular.json is not a bounded regular file")
                angular = json.loads(angular_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ExecutionError("angular.json is invalid or unavailable") from None
            projects = angular.get("projects", {}) if isinstance(angular, dict) else {}
            if not isinstance(projects, dict):
                raise ExecutionError("angular.json projects must be an object")
            applications = []
            for name, project in projects.items():
                if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
                    continue
                if not isinstance(project, dict) or project.get("projectType") != "application":
                    continue
                targets = project.get("architect", project.get("targets", {}))
                if isinstance(targets, dict) and isinstance(targets.get("build"), dict):
                    applications.append(name)
            default_project = angular.get("defaultProject") if isinstance(angular, dict) else None
            if isinstance(default_project, str) and default_project in applications:
                project_name = default_project
            elif len(applications) == 1:
                project_name = applications[0]
            else:
                raise ExecutionError("angular.json must identify exactly one application build target")
            return (node, str(cli), "build", project_name, "--output-path", "dist")
        raise ExecutionError("unsupported web build target")

    @staticmethod
    def _terminate_tree(process: subprocess.Popen) -> None:
        if os.name == "nt":
            taskkill = shutil.which("taskkill")
            if taskkill and process.poll() is None:
                subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10, check=False)
            elif process.poll() is None:
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

    def run(self, job_id: str, worker_id: str, target: str, *,
            cancel_requested: Callable[[], bool] | None = None) -> BuildResult:
        if not self.enabled:
            raise ExecutionError("web build execution is disabled by runner policy")
        workspace = self.workspaces.get(job_id, worker_id)
        source = workspace / "source" if (workspace / "source").is_dir() else workspace
        if source.is_symlink() or not source.is_dir():
            raise ExecutionError("project source directory is unsafe")
        command = self.command_for(target, source)
        self.workspaces.check_quota(job_id, worker_id)
        started = time.monotonic()
        if target == "build_static_web":
            destination = source / "dist"
            if destination.exists() or destination.is_symlink():
                raise ExecutionError("static build destination already exists")
            destination.mkdir(mode=0o700)
            excluded_dirs = {"dist", "node_modules", ".git", ".dcp-artifacts"}
            def safe_public_name(name: str) -> bool:
                lowered = name.lower()
                return not (
                    name.startswith(".") or lowered in {"id_rsa", "id_ed25519"}
                    or lowered.endswith((".pem", ".key", ".p12", ".pfx", ".secret", ".sqlite", ".sqlite3"))
                    or lowered.startswith(".env")
                )
            for item in source.iterdir():
                if item.name in excluded_dirs or not safe_public_name(item.name):
                    continue
                info = item.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise ExecutionError("static source contains a symlink")
                if stat.S_ISREG(info.st_mode):
                    if info.st_size > self.max_artifact_bytes:
                        raise ExecutionError("static source file exceeds size limit")
                    shutil.copyfile(item, destination / item.name)
                elif stat.S_ISDIR(info.st_mode):
                    for current, dirs, files in os.walk(item, followlinks=False):
                        current_path = Path(current)
                        for dirname in list(dirs):
                            child = current_path / dirname
                            if child.is_symlink():
                                raise ExecutionError("static source contains a symlink directory")
                            if dirname.startswith(".") or dirname in excluded_dirs:
                                dirs.remove(dirname)
                        for filename in files:
                            path = current_path / filename
                            if not safe_public_name(filename):
                                continue
                            meta = path.lstat()
                            if not stat.S_ISREG(meta.st_mode):
                                raise ExecutionError("static source contains a non-regular file")
                            relative = path.relative_to(source)
                            if meta.st_size > self.max_artifact_bytes:
                                raise ExecutionError("static source file exceeds size limit")
                            out = destination / relative
                            out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                            shutil.copyfile(path, out)
            self.workspaces.check_quota(job_id, worker_id)
            self.log("system", "Static web files copied to dist/; no source code executed")
            return BuildResult("succeeded", command, 0, round(time.monotonic() - started, 3), 0)

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(workspace / ".runner-home"),
            "USERPROFILE": str(workspace / ".runner-home"),
            "TMPDIR": str(workspace / ".tmp"),
            "TEMP": str(workspace / ".tmp"),
            "TMP": str(workspace / ".tmp"),
            "CI": "true",
            "NODE_ENV": "production",
            "npm_config_ignore_scripts": "true",
            "npm_config_audit": "false",
            "npm_config_fund": "false",
        }
        for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT"):
            if os.name == "nt" and os.environ.get(key):
                env[key] = os.environ[key]
        for key in ("HOME", ".runner-home", ".tmp"):
            path = workspace / key if key != "HOME" else workspace / ".runner-home"
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        process = subprocess.Popen(
            list(command), cwd=str(source), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False,
            close_fds=True, start_new_session=(os.name != "nt"), creationflags=creationflags,
        )
        output_bytes = 0
        outcome, error_code = "succeeded", None
        deadline = started + self.timeout_seconds
        chunks: queue.Queue = queue.Queue()
        def pump():
            try:
                while True:
                    data = process.stdout.read(4096)
                    if not data:
                        break
                    chunks.put(data)
            finally:
                chunks.put(None)
        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        stream_closed = False
        try:
            while process.poll() is None or not stream_closed:
                now = time.monotonic()
                if now >= deadline and process.poll() is None:
                    outcome, error_code = "failed", "BUILD_TIMEOUT"
                    self._terminate_tree(process)
                elif cancel_requested and cancel_requested() and process.poll() is None:
                    outcome, error_code = "cancelled", None
                    self._terminate_tree(process)
                try:
                    chunk = chunks.get(timeout=0.1)
                except queue.Empty:
                    continue
                if chunk is None:
                    stream_closed = True
                    continue
                remaining = self.max_output_bytes - output_bytes
                output_bytes += len(chunk)
                text = chunk[:max(0, remaining)].decode("utf-8", "replace")
                if text:
                    self.log("stdout", text)
                if output_bytes > self.max_output_bytes and process.poll() is None:
                    outcome, error_code = "failed", "BUILD_OUTPUT_LIMIT"
                    self._terminate_tree(process)
            return_code = process.wait(timeout=5)
            reader.join(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
            if outcome == "succeeded" and return_code != 0:
                outcome, error_code = "failed", "BUILD_FAILED"
        finally:
            if process.poll() is None:
                self._terminate_tree(process)
        if outcome == "succeeded":
            output_name = { "build_vite": "dist", "build_angular": "dist", "build_next": ".next" }.get(target)
            if output_name:
                output_path = source / output_name
                if output_path.is_symlink() or not output_path.is_dir():
                    outcome, error_code = "failed", "BUILD_OUTPUT_MISSING"
        self.workspaces.check_quota(job_id, worker_id)
        return BuildResult(outcome, command, return_code, round(time.monotonic() - started, 3),
                           output_bytes, error_code)


class WebArtifactPackager:
    def __init__(self, workspaces: WorkspaceManager, *, max_bytes: int = 100 * 1024 * 1024,
                 max_files: int = 100_000):
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1024 <= max_bytes <= 1024 * 1024 * 1024:
            raise ValueError("max_bytes must be between 1 KiB and 1 GiB")
        self.workspaces, self.max_bytes, self.max_files = workspaces, max_bytes, max_files

    def package(self, job_id: str, worker_id: str, target: str):
        workspace = self.workspaces.get(job_id, worker_id)
        source = workspace / "source" if (workspace / "source").is_dir() else workspace
        output_name = {"build_vite": "dist", "build_angular": "dist", "build_next": ".next"}.get(target, "dist")
        output = source / output_name
        if output.is_symlink() or not output.is_dir():
            raise ExecutionError("web build output is missing or unsafe")
        staging = workspace / ".dcp-artifacts"
        if staging.is_symlink() or (staging.exists() and not staging.is_dir()):
            raise ExecutionError("artifact staging directory is unsafe")
        staging.mkdir(mode=0o700, exist_ok=True)
        destination = staging / "web-build.zip"
        if destination.exists() or destination.is_symlink():
            raise ExecutionError("artifact destination already exists")
        entries, total = [], 0
        for current, dirs, files in os.walk(output, followlinks=False):
            base = Path(current)
            for dirname in list(dirs):
                if (base / dirname).is_symlink():
                    raise ExecutionError("web artifact contains a symlink directory")
            for filename in files:
                path = base / filename
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    raise ExecutionError("web artifact contains a non-regular file")
                relative = path.relative_to(output)
                total += info.st_size
                entries.append((path, relative))
                if len(entries) > self.max_files or total > self.max_bytes:
                    raise ExecutionError("web artifact exceeds configured limits")
        if not entries:
            raise ExecutionError("web build output is empty")
        with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, relative in entries:
                archive.write(path, relative.as_posix())
        if destination.stat().st_size > self.max_bytes:
            destination.unlink(missing_ok=True)
            raise ExecutionError("compressed web artifact exceeds configured limit")
        destination.chmod(0o600)
        self.workspaces.check_quota(job_id, worker_id)
        return destination, destination.name
