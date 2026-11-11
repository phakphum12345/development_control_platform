"""Explicitly enrolled local project roots and read-only source fingerprints.

This module records project identity only. It never executes source, follows
symlinks, accesses the network, or accepts browser-supplied filesystem paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


class LocalProjectError(RuntimeError):
    """Local project enrollment, lookup, or snapshot validation failed."""


_IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv",
    "__pycache__", ".dart_tool", "build", "dist", ".next", "coverage",
})
_MAX_FILES = 100_000
_MAX_BYTES = 1024 * 1024 * 1024


def default_registry_path() -> Path:
    """Return the same per-user DCP data location used by the Windows/local stack."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / "DCP" / "local-projects.json"


def _reject_link_components(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                raise LocalProjectError(f"{label} path contains a symlink or junction")
        except OSError:
            raise LocalProjectError(f"{label} path cannot be inspected") from None


def _canonical_directory(value: str | os.PathLike, label: str) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raise LocalProjectError(f"{label} must be an absolute path")
    try:
        _reject_link_components(raw, label)
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError):
        raise LocalProjectError(f"{label} does not exist or cannot be resolved") from None
    if not resolved.is_dir() or resolved in (Path(resolved.anchor), Path.home().resolve()):
        raise LocalProjectError(f"{label} must be a non-root directory")
    return resolved


class LocalProjectRegistry:
    """Persist explicitly approved roots and project snapshot identities.

    The caller must obtain the selected directory from a local, trusted UI/CLI
    interaction. A browser request must refer to an enrolled project ID, never
    supply an arbitrary host path.
    """

    def __init__(
        self,
        registry_file: str | os.PathLike,
        *,
        max_files: int = _MAX_FILES,
        max_bytes: int = _MAX_BYTES,
    ):
        raw = Path(registry_file).expanduser()
        if not raw.is_absolute():
            raise ValueError("registry_file must be an absolute path")
        if isinstance(max_files, bool) or not isinstance(max_files, int) or not 1 <= max_files <= _MAX_FILES:
            raise ValueError("max_files is outside the allowed range")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= _MAX_BYTES:
            raise ValueError("max_bytes is outside the allowed range")
        parent = raw.parent
        parent.mkdir(parents=True, exist_ok=True)
        _reject_link_components(parent, "registry directory")
        if raw.exists():
            _reject_link_components(raw, "registry file")
        self.registry_file = parent.resolve(strict=True) / raw.name
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._data = self._load()

    def _load(self) -> dict:
        if not self.registry_file.exists():
            return {"version": 1, "roots": {}, "projects": {}}
        try:
            if self.registry_file.is_symlink() or not self.registry_file.is_file():
                raise LocalProjectError("registry file is not a regular file")
            raw = self.registry_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise LocalProjectError("registry file is unreadable or invalid") from None
        if (not isinstance(data, dict) or data.get("version") != 1
                or not isinstance(data.get("roots"), dict)
                or not isinstance(data.get("projects"), dict)):
            raise LocalProjectError("registry schema is invalid")
        return data

    def reload(self) -> None:
        """Refresh persisted enrollment state so CLI changes become visible to Gateway."""
        self._data = self._load()

    def _save(self) -> None:
        payload = json.dumps(self._data, sort_keys=True, separators=(",", ":")) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=".dcp-projects-", dir=self.registry_file.parent)
        try:
            if os.name != "nt":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.registry_file)
            if os.name != "nt":
                os.chmod(self.registry_file, 0o600)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def enroll_root(self, selected_path: str | os.PathLike) -> dict:
        """Enroll one explicitly selected existing local directory; no recursion."""
        root = _canonical_directory(selected_path, "selected root")
        for root_id, record in self._data["roots"].items():
            if record.get("path") == str(root):
                return {"root_id": root_id, **record}
        root_id = str(uuid.uuid4())
        record = {"path": str(root), "created_at": datetime.now(timezone.utc).isoformat()}
        self._data["roots"][root_id] = record
        self._save()
        return {"root_id": root_id, **record}

    def list_roots(self) -> list[dict]:
        return [{"root_id": key, **value} for key, value in sorted(self._data["roots"].items())]

    def _fingerprint(self, project: Path) -> tuple[str, int, int]:
        digest = hashlib.sha256()
        file_count = 0
        total_bytes = 0
        stack = [project]
        entries: list[tuple[str, Path]] = []
        while stack:
            current = stack.pop()
            try:
                children = sorted(os.scandir(current), key=lambda entry: entry.name)
            except OSError:
                raise LocalProjectError("project directory cannot be inspected") from None
            for entry in children:
                if entry.name in _IGNORED_DIRS and entry.is_dir(follow_symlinks=False):
                    continue
                path = Path(entry.path)
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    raise LocalProjectError("project entry cannot be inspected") from None
                if stat.S_ISLNK(info.st_mode):
                    raise LocalProjectError("project contains a symlink; snapshot rejected")
                relative = path.relative_to(project).as_posix()
                if stat.S_ISDIR(info.st_mode):
                    stack.append(path)
                elif stat.S_ISREG(info.st_mode):
                    entries.append((relative, path))
                else:
                    raise LocalProjectError("project contains a special filesystem entry")
        entries.sort(key=lambda item: item[0])
        if len(entries) > self.max_files:
            raise LocalProjectError("project file-count limit exceeded")
        for relative, path in entries:
            try:
                before = path.lstat()
                if not stat.S_ISREG(before.st_mode):
                    raise LocalProjectError("project file changed type during fingerprint")
                file_hash = hashlib.sha256()
                size = 0
                flags = os.O_RDONLY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(path, flags)
                with os.fdopen(descriptor, "rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if not stat.S_ISREG(opened.st_mode) or (
                        before.st_ino and opened.st_ino and before.st_ino != opened.st_ino
                    ):
                        raise LocalProjectError("project file changed during fingerprint")
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        total_bytes += len(chunk)
                        if total_bytes > self.max_bytes:
                            raise LocalProjectError("project snapshot byte limit exceeded")
                        file_hash.update(chunk)
                    after = os.fstat(handle.fileno())
                if (opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    after.st_ino, after.st_size, after.st_mtime_ns
                ) or size != after.st_size:
                    raise LocalProjectError("project changed while snapshot was fingerprinted")
            except OSError:
                raise LocalProjectError("project file cannot be read safely") from None
            digest.update(relative.encode("utf-8", "surrogateescape"))
            digest.update(b"\0")
            digest.update(str(size).encode("ascii"))
            digest.update(b"\0")
            digest.update(file_hash.digest())
        return digest.hexdigest(), len(entries), total_bytes

    def register_project(self, root_id: str, selected_project: str | os.PathLike) -> dict:
        """Register a selected directory only when it is contained in an enrolled root."""
        root_record = self._data["roots"].get(root_id)
        if not isinstance(root_record, dict):
            raise LocalProjectError("approved root is not enrolled")
        root = _canonical_directory(root_record.get("path", ""), "enrolled root")
        project = _canonical_directory(selected_project, "selected project")
        try:
            relative = project.relative_to(root)
        except ValueError:
            raise LocalProjectError("selected project is outside every approved root") from None
        if not relative.parts:
            # Enrolling a broad root as a project can accidentally import unrelated files.
            raise LocalProjectError("select a project directory beneath the enrolled root")
        fingerprint, file_count, total_bytes = self._fingerprint(project)
        project_id = next((
            key for key, value in self._data["projects"].items()
            if value.get("path") == str(project) and value.get("root_id") == root_id
        ), str(uuid.uuid4()))
        record = {
            "root_id": root_id,
            "path": str(project),
            "relative_path": relative.as_posix(),
            "snapshot_sha256": fingerprint,
            "file_count": file_count,
            "total_bytes": total_bytes,
        }
        self._data["projects"][project_id] = record
        self._save()
        return {"project_id": project_id, **record}

    def materialize_project(
        self,
        project_id: str,
        destination: str | os.PathLike,
        expected_sha256: str,
    ) -> dict:
        """Copy a registered source into a new read-only snapshot directory.

        The caller must provide the fingerprint recorded when the job was queued.
        The source is revalidated before and after copying; a changed source fails
        closed. The snapshot is never executed by this method.
        """
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise LocalProjectError("expected snapshot SHA-256 is invalid")
        self.reload()
        record = self._data["projects"].get(project_id)
        if not isinstance(record, dict):
            raise LocalProjectError("project is not registered")
        if record.get("snapshot_sha256") != expected_sha256:
            raise LocalProjectError("queued snapshot fingerprint no longer matches the registry")
        root_record = self._data["roots"].get(record.get("root_id"))
        if not isinstance(root_record, dict):
            raise LocalProjectError("approved root is no longer enrolled")
        root = _canonical_directory(root_record.get("path", ""), "enrolled root")
        project = _canonical_directory(record.get("path", ""), "selected project")
        try:
            relative_project = project.relative_to(root)
        except ValueError:
            raise LocalProjectError("registered project moved outside its approved root") from None
        if not relative_project.parts:
            raise LocalProjectError("registered project cannot be the approved root itself")

        before_sha, file_count, total_bytes = self._fingerprint(project)
        if before_sha != expected_sha256:
            raise LocalProjectError("project changed after it was registered; refresh before queueing")

        raw_destination = Path(destination).expanduser()
        if not raw_destination.is_absolute() or raw_destination.name in ("", ".", ".."):
            raise LocalProjectError("snapshot destination must be a new absolute directory")
        parent = raw_destination.parent
        try:
            _reject_link_components(parent, "snapshot destination parent")
            parent = parent.resolve(strict=True)
        except (OSError, RuntimeError):
            raise LocalProjectError("snapshot destination parent is unavailable") from None
        if not parent.is_dir():
            raise LocalProjectError("snapshot destination parent is not a directory")
        target = parent / raw_destination.name
        if target.exists() or target.is_symlink():
            raise LocalProjectError("snapshot destination already exists")

        entries: list[tuple[str, Path]] = []
        stack = [project]
        while stack:
            current = stack.pop()
            try:
                children = sorted(os.scandir(current), key=lambda entry: entry.name)
            except OSError:
                raise LocalProjectError("project directory cannot be inspected") from None
            for entry in children:
                if entry.name in _IGNORED_DIRS and entry.is_dir(follow_symlinks=False):
                    continue
                path = Path(entry.path)
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    raise LocalProjectError("project entry cannot be inspected") from None
                if stat.S_ISLNK(info.st_mode):
                    raise LocalProjectError("project contains a symlink; snapshot rejected")
                if stat.S_ISDIR(info.st_mode):
                    stack.append(path)
                elif stat.S_ISREG(info.st_mode):
                    relative = path.relative_to(project).as_posix()
                    if "\\" in relative:
                        raise LocalProjectError("project path contains a platform-ambiguous separator")
                    posix = PurePosixPath(relative)
                    if posix.is_absolute() or not posix.parts or any(part in ("", ".", "..") for part in posix.parts):
                        raise LocalProjectError("project contains an unsafe relative path")
                    entries.append((relative, path))
                else:
                    raise LocalProjectError("project contains a special filesystem entry")
        entries.sort(key=lambda item: item[0])
        if len(entries) != file_count:
            raise LocalProjectError("project file list changed during snapshot preparation")

        created = False
        try:
            target.mkdir(mode=0o700)
            created = True
            copied_total = 0
            for relative, source_file in entries:
                relative_path = PurePosixPath(relative)
                output_file = target.joinpath(*relative_path.parts)
                output_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                resolved_parent = output_file.parent.resolve(strict=True)
                if resolved_parent != target.resolve(strict=True) and target.resolve(strict=True) not in resolved_parent.parents:
                    raise LocalProjectError("snapshot output path escaped destination")
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
                        raise LocalProjectError("source file changed type during snapshot")
                    while True:
                        chunk = source_handle.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        copied_total += len(chunk)
                        if copied > self.max_bytes or copied_total > self.max_bytes:
                            raise LocalProjectError("snapshot byte limit exceeded")
                        output_handle.write(chunk)
                        file_hash.update(chunk)
                    source_after = os.fstat(source_handle.fileno())
                    output_handle.flush()
                    os.fsync(output_handle.fileno())
                if (opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    source_after.st_ino, source_after.st_size, source_after.st_mtime_ns
                ) or copied != source_after.st_size:
                    raise LocalProjectError("source file changed while snapshot was copied")
                os.chmod(output_file, 0o400)

            source_after_sha, source_after_count, source_after_bytes = self._fingerprint(project)
            snapshot_sha, snapshot_count, snapshot_bytes = self._fingerprint(target)
            if (source_after_sha != expected_sha256 or snapshot_sha != expected_sha256
                    or source_after_count != file_count or snapshot_count != file_count
                    or source_after_bytes != total_bytes or snapshot_bytes != total_bytes
                    or copied_total != total_bytes):
                raise LocalProjectError("source or materialized snapshot failed integrity verification")

            for current, dirs, _files in os.walk(target, topdown=False, followlinks=False):
                for name in dirs:
                    os.chmod(Path(current) / name, 0o500)
                os.chmod(current, 0o500)
            return {
                "project_id": project_id,
                "snapshot_sha256": snapshot_sha,
                "snapshot_directory": str(target),
                "file_count": snapshot_count,
                "total_bytes": snapshot_bytes,
                "read_only_permissions_applied": True,
                "os_sandbox": False,
            }
        except Exception:
            if created and target.exists():
                for current, dirs, files in os.walk(target, topdown=False, followlinks=False):
                    for name in files:
                        try:
                            os.chmod(Path(current) / name, 0o600)
                        except OSError:
                            pass
                    for name in dirs:
                        try:
                            os.chmod(Path(current) / name, 0o700)
                        except OSError:
                            pass
                    try:
                        os.chmod(current, 0o700)
                    except OSError:
                        pass
                shutil.rmtree(target, ignore_errors=True)
            raise

    def refresh_project(self, project_id: str) -> dict:
        """Revalidate containment and produce a new content fingerprint."""
        record = self._data["projects"].get(project_id)
        if not isinstance(record, dict):
            raise LocalProjectError("project is not registered")
        refreshed = self.register_project(record["root_id"], record["path"])
        if refreshed["project_id"] != project_id:
            raise LocalProjectError("project identity changed unexpectedly")
        return refreshed

    def get_project(self, project_id: str) -> dict:
        record = self._data["projects"].get(project_id)
        if not isinstance(record, dict):
            raise LocalProjectError("project is not registered")
        return {"project_id": project_id, **record}

    def list_projects(self) -> list[dict]:
        return [{"project_id": key, **value} for key, value in sorted(self._data["projects"].items())]
