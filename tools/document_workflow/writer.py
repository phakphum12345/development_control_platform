"""Fail-closed local document writer with idempotency and read-back checks.

This module writes only Markdown and plain-text artifacts inside one explicitly
approved workspace. It is not a GitHub writer and does not expose a network API.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Iterable


_ALLOWED_SUFFIXES = {".md", ".txt"}
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPERATION_KEY = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")


class DocumentWriteError(ValueError):
    """A safe, fail-closed document write error."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise DocumentWriteError("A non-empty relative document path is required.")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise DocumentWriteError("Document path must be a clean relative path inside the workspace.")
    if ":" in path.parts[0]:
        raise DocumentWriteError("Drive-qualified paths are not allowed.")
    if path.suffix.lower() not in _ALLOWED_SUFFIXES:
        raise DocumentWriteError("Only .md and .txt documents may be written.")
    return path


def _within_scope(path: PurePosixPath, allowed_paths: Iterable[str]) -> bool:
    for raw in allowed_paths:
        grant = _normalize_scope_prefix(raw)
        if path == grant or grant in path.parents:
            return True
    return False


def _normalize_scope_prefix(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise DocumentWriteError("Write-scope entries must be non-empty relative paths.")
    path = PurePosixPath(value.replace("\\", "/").strip("/"))
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise DocumentWriteError("Write-scope path is invalid.")
    return path


def _resolve_target(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise DocumentWriteError("Symlinks are not allowed in document write paths.")
    parent = current.parent.resolve(strict=True)
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise DocumentWriteError("Document parent escapes the approved workspace.") from exc
    if not parent.is_dir():
        raise DocumentWriteError("Document parent must be an existing directory.")
    target = parent / current.name
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise DocumentWriteError("Existing document target must be a regular, non-symlink file.")
    return target


def _open_journal(path: Path, root: Path) -> sqlite3.Connection:
    journal = path.expanduser().resolve()
    try:
        journal.relative_to(root)
    except ValueError:
        pass
    else:
        raise DocumentWriteError("Operation journal must be stored outside the workspace.")
    journal.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(journal, timeout=15, isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS document_operations (
            operation_key TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            target_path TEXT NOT NULL,
            expected_sha256 TEXT,
            desired_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at REAL NOT NULL
        )"""
    )
    return connection


def write_document(
    *,
    workspace_root: str | Path,
    journal_path: str | Path,
    project_id: str,
    relative_path: str,
    content: str,
    operation_key: str,
    allowed_paths: Iterable[str],
    expected_sha256: str | None = None,
) -> dict:
    """Create or conditionally replace a .md/.txt file and verify read-back.

    New files require expected_sha256=None. Existing files require their current
    SHA-256. Replaying the same operation key is safe and returns the recorded
    result when the target still has the intended content.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise DocumentWriteError("An explicit project_id is required.")
    if not isinstance(operation_key, str) or not _OPERATION_KEY.fullmatch(operation_key):
        raise DocumentWriteError("operation_key must be 16-128 safe characters.")
    if expected_sha256 is not None and not _HEX_SHA256.fullmatch(expected_sha256):
        raise DocumentWriteError("expected_sha256 must be a full lowercase SHA-256 digest.")
    if not isinstance(content, str) or not content.strip() or "\x00" in content:
        raise DocumentWriteError("Document content must be non-empty UTF-8 text without NUL bytes.")

    root = Path(workspace_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise DocumentWriteError("workspace_root must be an existing directory.")
    relative = _normalize_relative_path(relative_path)
    if not _within_scope(relative, allowed_paths):
        raise DocumentWriteError("Target path is outside the explicitly granted write scope.")
    target = _resolve_target(root, relative)
    payload = content.encode("utf-8")
    desired_sha = _digest(payload)
    rel_key = relative.as_posix()

    db = _open_journal(Path(journal_path), root)
    try:
        # Hold a SQLite write lock across compare, atomic replace and read-back.
        # This serializes writers using the same journal, including other processes.
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute(
            "SELECT project_id,target_path,expected_sha256,desired_sha256,status "
            "FROM document_operations WHERE operation_key=?",
            (operation_key,),
        ).fetchone()
        if prior:
            if prior[:4] != (project_id, rel_key, expected_sha256, desired_sha):
                raise DocumentWriteError("Idempotency key was already used for a different operation.")
            actual = _digest(target.read_bytes()) if target.exists() else None
            if actual == desired_sha:
                db.execute(
                    "UPDATE document_operations SET status='PASS',updated_at=? WHERE operation_key=?",
                    (time.time(), operation_key),
                )
                db.execute("COMMIT")
                return {
                    "status": "PASS",
                    "operation": "DOCUMENT_WRITE_RECONCILED",
                    "project_id": project_id,
                    "path": rel_key,
                    "sha256": desired_sha,
                    "idempotent_replay": True,
                    "read_back_verified": True,
                }
            raise DocumentWriteError("Previous operation outcome is not verifiable; reconcile manually (UNKNOWN).")

        current_sha = _digest(target.read_bytes()) if target.exists() else None
        if current_sha != expected_sha256:
            raise DocumentWriteError("Target changed or existence differs from the expected base; refusing stale write.")

        db.execute(
            """INSERT INTO document_operations
            (operation_key,project_id,target_path,expected_sha256,desired_sha256,status,updated_at)
            VALUES(?,?,?,?,?,'PREPARED',?)""",
            (operation_key, project_id, rel_key, expected_sha256, desired_sha, time.time()),
        )

        fd, temp_name = tempfile.mkstemp(prefix=".dcp-document-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # Recheck the base immediately before replacement while holding the journal lock.
            latest_sha = _digest(target.read_bytes()) if target.exists() else None
            if latest_sha != expected_sha256:
                raise DocumentWriteError("Target changed during write preparation; refusing stale replacement.")
            os.replace(temp_name, target)
            read_back = target.read_bytes()
            read_back_sha = _digest(read_back)
            if read_back_sha != desired_sha:
                db.execute(
                    "UPDATE document_operations SET status='UNKNOWN',updated_at=? WHERE operation_key=?",
                    (time.time(), operation_key),
                )
                raise DocumentWriteError("Post-write read-back digest mismatch; operation status UNKNOWN.")
            try:
                dir_fd = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                # File bytes are verified; directory fsync is best-effort on platforms
                # that do not support opening directories.
                pass
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

        db.execute(
            "UPDATE document_operations SET status='PASS',updated_at=? WHERE operation_key=?",
            (time.time(), operation_key),
        )
        db.execute("COMMIT")
        return {
            "status": "PASS",
            "operation": "DOCUMENT_WRITE",
            "project_id": project_id,
            "path": rel_key,
            "size_bytes": len(payload),
            "line_count": content.count("\\n") + 1,
            "sha256": desired_sha,
            "read_back_verified": True,
            "idempotent_replay": False,
        }
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()
