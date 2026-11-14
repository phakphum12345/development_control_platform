"""Bounded, disposable Workspace projection primitives for Windows PSEC jobs.

This module deliberately does not grant ACLs or launch processes. A projection
is not executable until the Windows Package-SID authorization layer verifies
access to the job-private roots and the child proves the expected access.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class ProjectionError(RuntimeError):
    """Workspace projection could not be created or verified safely."""


@dataclass(frozen=True)
class ProjectionLimits:
    max_files: int = 20_000
    max_entries: int = 40_000
    max_total_bytes: int = 512 * 1024 * 1024
    max_file_bytes: int = 128 * 1024 * 1024
    max_relative_path_chars: int = 240
    max_copy_seconds: float = 60.0
    chunk_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("max_files", "max_entries", "max_total_bytes", "max_file_bytes",
                     "max_relative_path_chars", "chunk_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (isinstance(self.max_copy_seconds, bool)
                or not isinstance(self.max_copy_seconds, (int, float))
                or self.max_copy_seconds <= 0):
            raise ValueError("max_copy_seconds must be positive")


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    kind: str
    size: int
    sha256: str


@dataclass
class WorkspaceProjection:
    """Owned job-private projection and scratch paths.

    The caller must not launch an AppContainer against these paths until a
    separate Windows ACL manager has applied and verified the exact Package
    SID permissions. close() is intentionally strict and raises on failure.
    """
    root: Path
    workspace: Path
    scratch: Path
    manifest: tuple[ManifestEntry, ...]
    manifest_sha256: str
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        if self.root.is_symlink() or _is_reparse(self.root):
            raise ProjectionError("job projection root became a reparse point")
        try:
            shutil.rmtree(self.root)
        except OSError as exc:
            raise ProjectionError("job projection cleanup failed") from exc
        if self.root.exists():
            raise ProjectionError("job projection cleanup was incomplete")
        self._closed = True


_RESERVED_DOS = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\\..*)?$",
    re.IGNORECASE,
)


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError as exc:
        raise ProjectionError("filesystem entry cannot be inspected") from exc
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _canonical_directory(value: str | os.PathLike, label: str) -> Path:
    raw = Path(value)
    if not raw.is_absolute():
        raise ProjectionError(f"{label} must be absolute")
    current = Path(raw.anchor)
    for part in raw.parts[1:]:
        current = current / part
        if current.is_symlink() or _is_reparse(current):
            raise ProjectionError(f"{label} contains a reparse point")
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ProjectionError(f"{label} is unavailable") from exc
    if resolved != raw or not resolved.is_dir():
        raise ProjectionError(f"{label} must be a canonical directory")
    return resolved


def _reject_alternate_data_streams(path: Path) -> None:
    """Reject NTFS named streams; fail closed if Windows cannot enumerate them."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class _StreamData(ctypes.Structure):
        # WIN32_FIND_STREAM_DATA layout is LARGE_INTEGER StreamSize
        # followed by WCHAR cStreamName[MAX_PATH + 1]. Keep this exact
        # native field order; reversing it corrupts the stream-name read.
        _fields_ = [
            ("StreamSize", ctypes.c_longlong),
            ("cStreamName", wintypes.WCHAR * 296),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = getattr(kernel32, "FindFirstStreamW", None)
    find_next = getattr(kernel32, "FindNextStreamW", None)
    find_close = getattr(kernel32, "FindClose", None)
    if find_first is None or find_next is None or find_close is None:
        raise ProjectionError("NTFS alternate-stream enumeration is unavailable")

    handle_type = wintypes.HANDLE
    find_first.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                           ctypes.POINTER(_StreamData), wintypes.DWORD]
    find_first.restype = handle_type
    find_next.argtypes = [handle_type, ctypes.POINTER(_StreamData)]
    find_next.restype = wintypes.BOOL
    find_close.argtypes = [handle_type]
    find_close.restype = wintypes.BOOL

    data = _StreamData()
    handle = find_first(str(path), 0, ctypes.byref(data), 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        # FindFirstStreamW reports ERROR_HANDLE_EOF when the path has no
        # enumerable streams (notably ordinary directories). This is a
        # successful empty result, not an inspection failure.
        if error == 38:  # ERROR_HANDLE_EOF
            return
        raise ProjectionError(
            f"NTFS alternate streams cannot be inspected (Windows error {error})"
        )

    try:
        while True:
            stream_name = data.cStreamName
            # The unnamed/default file stream is expected. All named data
            # streams are rejected because the projection copies only bytes
            # from the unnamed stream.
            if stream_name != "::$DATA":
                raise ProjectionError("workspace contains an alternate data stream")
            if not find_next(handle, ctypes.byref(data)):
                error = ctypes.get_last_error()
                if error == 38:  # ERROR_HANDLE_EOF
                    break
                raise ProjectionError(
                    f"NTFS alternate streams cannot be enumerated (Windows error {error})"
                )
    finally:
        if not find_close(handle):
            raise ProjectionError("NTFS alternate-stream enumeration handle close failed")


def _validate_component(name: str) -> None:
    if (not name or name in {".", ".."} or name.endswith((".", " "))
            or any(ord(char) < 32 for char in name)
            or any(char in name for char in '<>:"/\\|?*')):
        raise ProjectionError("workspace contains an invalid Windows path component")
    stem = name.split(".", 1)[0]
    if _RESERVED_DOS.fullmatch(stem):
        raise ProjectionError("workspace contains a reserved DOS device name")


def _ensure_unique_names(names: Iterator[str] | list[str] | tuple[str, ...]) -> None:
    seen: set[str] = set()
    for name in names:
        folded = name.casefold()
        if folded in seen:
            raise ProjectionError("workspace contains a case-insensitive name collision")
        seen.add(folded)


def _walk(source: Path, limits: ProjectionLimits, started: float
          ) -> Iterator[tuple[Path, str, os.stat_result]]:
    count = 0
    entry_count = 0
    folded_paths: set[str] = set()
    stack: list[tuple[Path, str]] = [(source, "")]
    while stack:
        directory, relative_parent = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise ProjectionError("workspace directory cannot be enumerated") from exc
        _ensure_unique_names([entry.name for entry in entries])
        for entry in entries:
            if time.monotonic() - started > limits.max_copy_seconds:
                raise ProjectionError("workspace projection exceeded its time limit")
            _validate_component(entry.name)
            relative = f"{relative_parent}/{entry.name}" if relative_parent else entry.name
            if len(relative) > limits.max_relative_path_chars:
                raise ProjectionError("workspace path exceeds the configured length limit")
            folded_relative = relative.casefold()
            if folded_relative in folded_paths:
                raise ProjectionError("workspace contains a case-insensitive path collision")
            folded_paths.add(folded_relative)
            entry_count += 1
            if entry_count > limits.max_entries:
                raise ProjectionError("workspace exceeds the filesystem-entry limit")
            path = Path(entry.path)
            try:
                # On Windows, DirEntry.stat() can report st_nlink=0 for
                # ordinary NTFS entries. Path.lstat() queries the path through
                # the OS stat path and provides the link count needed here.
                info = path.lstat()
            except OSError as exc:
                raise ProjectionError("workspace entry cannot be inspected") from exc
            attributes = getattr(info, "st_file_attributes", 0)
            if entry.is_symlink() or attributes & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
            ):
                raise ProjectionError("workspace contains a symlink or reparse point")
            if stat.S_ISDIR(info.st_mode):
                # FindFirstStreamW does not enumerate directory streams on
                # Windows (it reports ERROR_HANDLE_EOF for directories).
                # Enumerate named streams on regular files below instead.
                yield path, relative, info
                stack.append((path, relative))
            elif stat.S_ISREG(info.st_mode):
                _reject_alternate_data_streams(path)
                link_count = getattr(info, "st_nlink", 0)
                if link_count != 1:
                    detail = ("cannot verify file hard-link count"
                              if link_count < 1 else "workspace contains a multiply-linked file")
                    raise ProjectionError(detail)
                count += 1
                if count > limits.max_files:
                    raise ProjectionError("workspace exceeds the file-count limit")
                if info.st_size > limits.max_file_bytes:
                    raise ProjectionError("workspace file exceeds the per-file size limit")
                yield path, relative, info
            else:
                raise ProjectionError("workspace contains an unsupported filesystem object")


def _hash_file(path: Path, chunk_bytes: int, deadline: float) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                if time.monotonic() > deadline:
                    raise ProjectionError("workspace projection exceeded its time limit")
                chunk = stream.read(chunk_bytes)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
    except OSError as exc:
        raise ProjectionError("workspace file could not be read") from exc
    return digest.hexdigest(), total


def _manifest_digest(entries: tuple[ManifestEntry, ...]) -> str:
    digest = hashlib.sha256()
    for item in sorted(entries, key=lambda value: value.path.casefold()):
        record = f"{item.kind}\0{item.path}\0{item.size}\0{item.sha256}\n"
        digest.update(record.encode("utf-8"))
    return digest.hexdigest()


def create_workspace_projection(
    source_workspace: str | os.PathLike,
    private_parent: str | os.PathLike,
    *,
    limits: ProjectionLimits | None = None,
) -> WorkspaceProjection:
    """Copy a bounded, link-free Workspace snapshot into a unique job root.

    private_parent must already be a dedicated runner-controlled directory.
    This function never changes its ACL. The caller remains responsible for
    proving the parent/root traversal and Package-SID DACLs before launch.
    """
    limits = limits or ProjectionLimits()
    source = _canonical_directory(source_workspace, "source Workspace")
    parent = _canonical_directory(private_parent, "private parent")
    if source == parent or source in parent.parents or parent in source.parents:
        raise ProjectionError("private parent and source Workspace must be disjoint")
    root = Path(tempfile.mkdtemp(prefix="dcp-psec-job-", dir=str(parent)))
    try:
        if root.is_symlink() or _is_reparse(root):
            raise ProjectionError("new job root is a reparse point")
        projection = root / "workspace"
        scratch = root / "scratch"
        projection.mkdir()
        scratch.mkdir()
        started = time.monotonic()
        deadline = started + limits.max_copy_seconds
        manifest: list[ManifestEntry] = []
        total_bytes = 0

        # Create directory structure first; never follow source links.
        discovered = list(_walk(source, limits, started))
        for src, relative, info in discovered:
            if stat.S_ISDIR(info.st_mode):
                (projection / Path(relative)).mkdir(parents=True, exist_ok=True)
                manifest.append(ManifestEntry(
                    relative, "directory", 0, hashlib.sha256(b"").hexdigest()
                ))

        for src, relative, before in discovered:
            if not stat.S_ISREG(before.st_mode):
                continue
            if time.monotonic() > deadline:
                raise ProjectionError("workspace projection exceeded its time limit")
            target = projection / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            source_hash, source_size = _hash_file(src, limits.chunk_bytes, deadline)
            if source_size != before.st_size:
                raise ProjectionError("workspace source changed while being inspected")
            try:
                with src.open("rb") as reader, target.open("xb") as writer:
                    copied = 0
                    digest = hashlib.sha256()
                    while True:
                        if time.monotonic() > deadline:
                            raise ProjectionError("workspace projection exceeded its time limit")
                        chunk = reader.read(limits.chunk_bytes)
                        if not chunk:
                            break
                        copied += len(chunk)
                        total_bytes += len(chunk)
                        if copied > limits.max_file_bytes or total_bytes > limits.max_total_bytes:
                            raise ProjectionError("workspace projection exceeds the byte limit")
                        writer.write(chunk)
                        digest.update(chunk)
                    writer.flush()
                    os.fsync(writer.fileno())
            except OSError as exc:
                raise ProjectionError("workspace file could not be copied") from exc
            after = src.lstat()
            if (_is_reparse(src) or not stat.S_ISREG(after.st_mode)
                    or after.st_size != before.st_size
                    or getattr(after, "st_mtime_ns", None) != getattr(before, "st_mtime_ns", None)
                    or copied != source_size or digest.hexdigest() != source_hash):
                raise ProjectionError("workspace source changed during projection")
            manifest.append(ManifestEntry(relative, "file", copied, digest.hexdigest()))

        # Re-hash the destination tree before publishing the projection object.
        verified: list[ManifestEntry] = []
        for item in manifest:
            staged = projection / Path(item.path)
            if staged.is_symlink() or _is_reparse(staged):
                raise ProjectionError("staged projection contains a reparse point")
            if item.kind == "directory":
                if not staged.is_dir():
                    raise ProjectionError("staged projection directory verification failed")
            elif item.kind == "file":
                if not staged.is_file():
                    raise ProjectionError("staged projection file verification failed")
                staged_hash, staged_size = _hash_file(staged, limits.chunk_bytes, deadline)
                if staged_hash != item.sha256 or staged_size != item.size:
                    raise ProjectionError("staged projection manifest verification failed")
            else:
                raise ProjectionError("projection manifest contains an unknown object type")
            verified.append(item)
        entries = tuple(sorted(verified, key=lambda value: value.path.casefold()))
        return WorkspaceProjection(
            root=root,
            workspace=projection,
            scratch=scratch,
            manifest=entries,
            manifest_sha256=_manifest_digest(entries),
        )
    except Exception:
        try:
            if root.exists() and not root.is_symlink() and not _is_reparse(root):
                shutil.rmtree(root)
        except OSError:
            # Preserve the original failure; callers must also inspect the
            # private parent for an orphan and fail closed on cleanup errors.
            pass
        raise
