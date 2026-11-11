"""Bounded, path-safe checkout of one immutable GitHub commit.

Uses GitHub's source archive endpoint; it does not run git hooks, submodules,
package scripts, or any repository code during extraction.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .workspace import WorkspaceError, WorkspaceManager
from .local_project import LocalProjectError, LocalProjectRegistry


class CheckoutError(RuntimeError):
    """Repository source could not be safely retrieved or extracted."""


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlparse
        old, new = urlparse(req.full_url), urlparse(newurl)
        if new.scheme != "https" or new.hostname not in ("api.github.com", "codeload.github.com"):
            raise CheckoutError("GitHub archive redirected to an untrusted host")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and old.hostname != new.hostname:
            redirected.remove_header("Authorization")
        return redirected



class LocalProjectCheckout:
    """Materialize a registered Local Folder snapshot and create a writable build copy."""

    def __init__(self, workspace_manager: WorkspaceManager, registry: LocalProjectRegistry,
                 *, max_bytes: int = 2 * 1024 * 1024 * 1024):
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= 10 * 1024 * 1024 * 1024:
            raise ValueError("max_bytes is outside the allowed range")
        self.workspaces = workspace_manager
        self.registry = registry
        self.max_bytes = max_bytes

    def _copy_snapshot(self, snapshot: Path, destination: Path) -> int:
        root = snapshot.resolve(strict=True)
        if not root.is_dir() or root.is_symlink() or destination.exists() or destination.is_symlink():
            raise CheckoutError("local snapshot copy paths are unsafe")
        destination.mkdir(mode=0o700)
        total = 0
        for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            relative_dir = current_path.relative_to(root)
            output_dir = destination.joinpath(*relative_dir.parts) if relative_dir.parts else destination
            for name in sorted(dirs):
                source_dir = current_path / name
                info = source_dir.lstat()
                if not stat.S_ISDIR(info.st_mode):
                    raise CheckoutError("local snapshot contains a symlink or special directory")
                (output_dir / name).mkdir(mode=0o700)
            for name in sorted(files):
                source_file = current_path / name
                info = source_file.lstat()
                if not stat.S_ISREG(info.st_mode):
                    raise CheckoutError("local snapshot contains a symlink or special file")
                relative = source_file.relative_to(root)
                if any(part in ("", ".", "..") for part in relative.parts):
                    raise CheckoutError("local snapshot contains an unsafe path")
                output_file = destination.joinpath(*relative.parts)
                output_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                source_flags = os.O_RDONLY
                output_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    source_flags |= os.O_NOFOLLOW
                    output_flags |= os.O_NOFOLLOW
                source_fd = os.open(source_file, source_flags)
                try:
                    output_fd = os.open(output_file, output_flags, 0o600)
                except Exception:
                    os.close(source_fd)
                    raise
                file_hash = hashlib.sha256()
                copied = 0
                with os.fdopen(source_fd, "rb") as source_handle, os.fdopen(output_fd, "wb") as output_handle:
                    opened = os.fstat(source_handle.fileno())
                    if not stat.S_ISREG(opened.st_mode):
                        raise CheckoutError("local snapshot file changed type")
                    while True:
                        chunk = source_handle.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        total += len(chunk)
                        if total > self.max_bytes:
                            raise CheckoutError("local snapshot copy exceeds byte limit")
                        output_handle.write(chunk)
                        file_hash.update(chunk)
                    after = os.fstat(source_handle.fileno())
                    output_handle.flush()
                    os.fsync(output_handle.fileno())
                if (opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    after.st_ino, after.st_size, after.st_mtime_ns
                ) or copied != after.st_size:
                    raise CheckoutError("local snapshot changed during writable copy")
                os.chmod(output_file, 0o600)
        return total

    def checkout(self, job_id: str, worker_id: str, project_id: str,
                 snapshot_sha256: str) -> tuple[Path, dict]:
        workspace = self.workspaces.get(job_id, worker_id)
        snapshot = workspace / "source-snapshot"
        source = workspace / "source"
        try:
            metadata = self.registry.materialize_project(
                project_id, snapshot, snapshot_sha256
            )
            copied_bytes = self._copy_snapshot(snapshot, source)
            copy_sha, copy_count, copy_bytes = self.registry._fingerprint(source)
            if (copy_sha != snapshot_sha256 or copy_count != metadata["file_count"]
                    or copy_bytes != metadata["total_bytes"] or copied_bytes != copy_bytes):
                raise CheckoutError("writable Local Folder copy failed snapshot integrity verification")
            self.workspaces.check_quota(job_id, worker_id)
            return source, {
                "project_id": project_id,
                "snapshot_sha256": snapshot_sha256,
                "file_count": copy_count,
                "total_bytes": copy_bytes,
                "snapshot_directory": "source-snapshot",
            }
        except (LocalProjectError, OSError, ValueError):
            raise CheckoutError("Local Folder snapshot could not be materialized safely") from None


class GitHubCommitCheckout:
    """Download and safely extract a single repository commit into workspace/source."""

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        *,
        token: str | None = None,
        max_archive_bytes: int = 100 * 1024 * 1024,
        max_expanded_bytes: int = 1024 * 1024 * 1024,
        max_files: int = 100_000,
        timeout_seconds: int = 60,
    ):
        for name, value, minimum, maximum in (
            ("max_archive_bytes", max_archive_bytes, 1024, 1024 * 1024 * 1024),
            ("max_expanded_bytes", max_expanded_bytes, 1024, 10 * 1024 * 1024 * 1024),
            ("max_files", max_files, 1, 1_000_000),
            ("timeout_seconds", timeout_seconds, 1, 300),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"{name} is outside its allowed range")
        if token is not None and (not isinstance(token, str) or len(token) < 20):
            raise ValueError("GitHub token is invalid")
        self.workspaces = workspace_manager
        self.token = token
        self.max_archive_bytes = max_archive_bytes
        self.max_expanded_bytes = max_expanded_bytes
        self.max_files = max_files
        self.timeout_seconds = timeout_seconds
        self.opener = urllib.request.build_opener(_SafeRedirect())

    @staticmethod
    def _validate(repository: str, commit_sha: str):
        import re
        if not isinstance(repository, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repository
        ):
            raise CheckoutError("invalid GitHub repository")
        if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise CheckoutError("invalid immutable commit SHA")

    def checkout(self, job_id: str, worker_id: str, repository: str, commit_sha: str) -> Path:
        self._validate(repository, commit_sha)
        workspace = self.workspaces.get(job_id, worker_id)
        source = workspace / "source"
        if source.exists():
            raise CheckoutError("workspace source directory already exists")
        source.mkdir(mode=0o700)
        url = f"https://api.github.com/repos/{repository}/zipball/{commit_sha}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "DCP-Runner-Agent",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(url, headers=headers, method="GET")
        total_written = 0
        try:
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as archive:
                with self.opener.open(request, timeout=self.timeout_seconds) as response:
                    length = response.headers.get("Content-Length")
                    if length and int(length) > self.max_archive_bytes:
                        raise CheckoutError("source archive exceeds download limit")
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total_written += len(chunk)
                        if total_written > self.max_archive_bytes:
                            raise CheckoutError("source archive exceeds download limit")
                        archive.write(chunk)
                archive.seek(0)
                with zipfile.ZipFile(archive) as bundle:
                    entries = bundle.infolist()
                    if len(entries) > self.max_files:
                        raise CheckoutError("source archive contains too many entries")
                    roots = set()
                    expanded = 0
                    safe_entries = []
                    for info in entries:
                        raw = info.filename
                        path = PurePosixPath(raw)
                        if path.is_absolute() or not path.parts or ".." in path.parts or "\\" in raw:
                            raise CheckoutError("source archive contains an unsafe path")
                        roots.add(path.parts[0])
                        if len(path.parts) < 2:
                            continue
                        relative = Path(*path.parts[1:])
                        if relative == Path("."):
                            continue
                        mode = (info.external_attr >> 16) & 0o170000
                        if mode == 0o120000:
                            raise CheckoutError("source archive contains a symlink")
                        if mode not in (0, 0o100000, 0o040000):
                            raise CheckoutError("source archive contains a special file")
                        if not info.is_dir():
                            expanded += info.file_size
                            if expanded > self.max_expanded_bytes:
                                raise CheckoutError("expanded source exceeds size limit")
                        safe_entries.append((info, relative))
                    if len(roots) != 1:
                        raise CheckoutError("source archive has an unexpected root layout")
                    root = source.resolve(strict=True)
                    for info, relative in safe_entries:
                        destination = source.joinpath(relative)
                        resolved = destination.resolve(strict=False)
                        if resolved != root and root not in resolved.parents:
                            raise CheckoutError("source archive path escaped workspace")
                        if info.is_dir():
                            destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                            continue
                        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        written = 0
                        with bundle.open(info, "r") as src, destination.open("xb") as dst:
                            while True:
                                chunk = src.read(1024 * 1024)
                                if not chunk:
                                    break
                                written += len(chunk)
                                if written > info.file_size:
                                    raise CheckoutError("source archive entry exceeded declared size")
                                dst.write(chunk)
                        if written != info.file_size:
                            raise CheckoutError("source archive entry was truncated")
                        file_mode = (info.external_attr >> 16) & 0o777
                        destination.chmod(0o700 if file_mode & 0o111 else 0o600)
            if not (source / "pubspec.yaml").is_file():
                raise CheckoutError("selected commit is not a Flutter project")
            self.workspaces.check_quota(job_id, worker_id)
            return source
        except CheckoutError:
            raise
        except (OSError, zipfile.BadZipFile, urllib.error.URLError, ValueError) as exc:
            raise CheckoutError("GitHub source checkout failed") from exc
