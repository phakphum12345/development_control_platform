"""Per-job local workspace isolation for DCP Runner Agents.

This module only allocates and removes directories. It never checks out repositories,
runs commands, or provisions infrastructure.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


_WORKER_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
_MARKER = ".dcp-workspace.json"


class WorkspaceError(RuntimeError):
    """Workspace allocation, ownership, or safety failure."""


class WorkspaceManager:
    """Create private, job-scoped directories beneath one trusted workspace root."""

    def __init__(self, root: str | os.PathLike, max_active: int = 8,
                 max_workspace_bytes: int = 2 * 1024 * 1024 * 1024):
        raw = Path(root).expanduser()
        if not raw.is_absolute():
            raise ValueError("workspace root must be an absolute path")
        if isinstance(max_active, bool) or not isinstance(max_active, int) or not 1 <= max_active <= 256:
            raise ValueError("max_active must be between 1 and 256")
        if (isinstance(max_workspace_bytes, bool) or not isinstance(max_workspace_bytes, int)
                or not 1 <= max_workspace_bytes <= 100 * 1024 * 1024 * 1024):
            raise ValueError("max_workspace_bytes must be between 1 byte and 100 GiB")
        self.root = raw
        self.max_active = max_active
        self.max_workspace_bytes = max_workspace_bytes
        self._prepare_root()

    def _prepare_root(self):
        if self.root.exists() and self.root.is_symlink():
            raise WorkspaceError("workspace root must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise WorkspaceError("workspace root is not a safe directory")
        resolved = self.root.resolve(strict=True)
        if resolved in (Path("/"), Path.home().resolve()):
            raise WorkspaceError("workspace root cannot be a filesystem or home root")
        self.root = resolved
        try:
            os.chmod(self.root, 0o700)
        except OSError as exc:
            raise WorkspaceError("cannot secure workspace root permissions") from exc

    @staticmethod
    def _identity(job_id: str, worker_id: str):
        try:
            parsed = uuid.UUID(job_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("invalid job UUID") from None
        if str(parsed) != job_id:
            raise ValueError("job UUID must use canonical lowercase form")
        if not isinstance(worker_id, str) or not _WORKER_ID.fullmatch(worker_id):
            raise ValueError("invalid worker ID")

    def _active_count(self) -> int:
        count = 0
        for entry in os.scandir(self.root):
            if entry.is_dir(follow_symlinks=False):
                marker = Path(entry.path) / _MARKER
                if marker.is_file() and not marker.is_symlink():
                    count += 1
        return count

    def create(self, job_id: str, worker_id: str) -> Path:
        """Allocate an empty 0700 workspace, bound to one job and worker."""
        self._identity(job_id, worker_id)
        self._prepare_root()
        target = self.root / job_id
        if self._active_count() >= self.max_active:
            raise WorkspaceError("active workspace limit reached")
        try:
            target.mkdir(mode=0o700)
        except FileExistsError:
            raise WorkspaceError("workspace already exists") from None
        try:
            marker = target / _MARKER
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(marker, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"job_id": job_id, "worker_id": worker_id, "version": 1},
                          handle, sort_keys=True)
            return target
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise

    def get(self, job_id: str, worker_id: str) -> Path:
        """Return a workspace only when its directory and ownership marker are valid."""
        self._identity(job_id, worker_id)
        target = self.root / job_id
        if target.is_symlink() or not target.is_dir():
            raise WorkspaceError("workspace does not exist or is not a safe directory")
        resolved = target.resolve(strict=True)
        if resolved.parent != self.root:
            raise WorkspaceError("workspace escaped its configured root")
        marker = target / _MARKER
        if marker.is_symlink() or not marker.is_file():
            raise WorkspaceError("workspace ownership marker is missing or unsafe")
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise WorkspaceError("workspace ownership marker is invalid") from None
        if metadata != {"job_id": job_id, "worker_id": worker_id, "version": 1}:
            raise WorkspaceError("workspace belongs to a different job or worker")
        return target

    def check_quota(self, job_id: str, worker_id: str) -> int:
        """Measure regular-file bytes without following symlinks; fail closed on links."""
        target = self.get(job_id, worker_id)
        total = 0
        for current, dirs, files in os.walk(target, topdown=True, followlinks=False):
            for name in list(dirs):
                item = Path(current) / name
                if item.is_symlink():
                    raise WorkspaceError("workspace contains a symlink")
            for name in files:
                if current == str(target) and name == _MARKER:
                    continue
                item = Path(current) / name
                info = item.lstat()
                if not stat.S_ISREG(info.st_mode):
                    raise WorkspaceError("workspace contains a non-regular file")
                total += info.st_size
                if total > self.max_workspace_bytes:
                    raise WorkspaceError("workspace byte quota exceeded")
        return total

    def retain_for_preview(self, job_id: str, worker_id: str, *, ttl_seconds: int = 3600) -> dict:
        """Retain a successful web-build workspace for a bounded local preview window."""
        self._identity(job_id, worker_id)
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 60 <= ttl_seconds <= 86400:
            raise WorkspaceError("preview retention TTL must be between 60 and 86400 seconds")
        target = self.get(job_id, worker_id)
        marker = target / ".dcp-preview-retention.json"
        if marker.is_symlink() or (marker.exists() and not marker.is_file()):
            raise WorkspaceError("preview retention marker is unsafe")
        temporary = target / (".dcp-preview-retention-" + uuid.uuid4().hex + ".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        payload = json.dumps({
            "job_id": job_id, "worker_id": worker_id,
            "expires_at": time.time() + ttl_seconds, "version": 1,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            fd = os.open(temporary, flags, 0o600)
            try:
                offset = 0
                while offset < len(payload):
                    offset += os.write(fd, payload[offset:])
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, marker)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise WorkspaceError("preview retention marker could not be secured") from None
        return {"job_id": job_id, "expires_in_seconds": ttl_seconds}

    def cleanup_expired_preview_workspaces(self, now_epoch: float | None = None) -> int:
        """Remove only workspaces with a valid, expired DCP preview-retention marker."""
        now = time.time() if now_epoch is None else now_epoch
        removed = 0
        try:
            entries = list(os.scandir(self.root))
        except OSError:
            raise WorkspaceError("workspace root cannot be scanned for expired previews") from None
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            target = Path(entry.path)
            retention = target / ".dcp-preview-retention.json"
            if retention.is_symlink() or not retention.is_file():
                continue
            try:
                value = json.loads(retention.read_text(encoding="utf-8"))
                job_id, worker_id = value.get("job_id"), value.get("worker_id")
                expires_at = value.get("expires_at")
                if (value != {
                    "job_id": job_id, "worker_id": worker_id,
                    "expires_at": expires_at, "version": 1,
                } or not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool)
                        or expires_at > now):
                    continue
                owned = self.get(job_id, worker_id)
                if owned != target:
                    continue
                self.cleanup(job_id, worker_id)
                removed += 1
            except (OSError, ValueError, TypeError, WorkspaceError, json.JSONDecodeError):
                # Invalid or concurrently changing markers are retained for manual inspection.
                continue
        return removed

    def reconcile_terminal_workspaces(
        self,
        status_provider,
        *,
        now_epoch: float | None = None,
        grace_seconds: int = 120,
    ) -> dict:
        """Remove only old Terminal workspaces proven safe by the authenticated Gateway.

        Active, queued, retrying, UNKNOWN, lease-expired, unowned, malformed, and
        preview-retained workspaces are preserved. The Gateway must explicitly
        attest cleanup_safe for the same job/worker before deletion is considered.
        """
        if not callable(status_provider):
            raise ValueError("status_provider must be callable")
        if (isinstance(grace_seconds, bool) or not isinstance(grace_seconds, int)
                or not 60 <= grace_seconds <= 3600):
            raise ValueError("grace_seconds must be between 60 and 3600")
        now = time.time() if now_epoch is None else now_epoch
        if (isinstance(now, bool) or not isinstance(now, (int, float))
                or not math.isfinite(now)):
            raise ValueError("now_epoch must be a finite timestamp")
        cutoff = datetime.fromtimestamp(now - grace_seconds, timezone.utc)
        report = {"scanned": 0, "removed": 0, "skipped": 0}
        try:
            entries = list(os.scandir(self.root))
        except OSError:
            raise WorkspaceError("workspace root cannot be scanned for reconciliation") from None
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            target = Path(entry.path)
            marker = target / _MARKER
            if marker.is_symlink() or not marker.is_file():
                continue
            report["scanned"] += 1
            try:
                metadata = json.loads(marker.read_text(encoding="utf-8"))
                if (not isinstance(metadata, dict)
                        or set(metadata) != {"job_id", "worker_id", "version"}
                        or metadata.get("version") != 1):
                    report["skipped"] += 1
                    continue
                job_id, worker_id = metadata.get("job_id"), metadata.get("worker_id")
                self._identity(job_id, worker_id)
                if entry.name != job_id or target.resolve(strict=True).parent != self.root:
                    report["skipped"] += 1
                    continue
                retention = target / ".dcp-preview-retention.json"
                if retention.exists() or retention.is_symlink():
                    report["skipped"] += 1
                    continue
                try:
                    status = status_provider(job_id)
                except Exception:
                    report["skipped"] += 1
                    continue
                if (not isinstance(status, dict)
                        or status.get("job_id") != job_id
                        or status.get("worker_id") != worker_id
                        or status.get("target") != "terminal_script"
                        or status.get("cleanup_safe") is not True
                        or status.get("state") not in {"succeeded", "failed", "cancelled"}):
                    report["skipped"] += 1
                    continue
                updated_at = status.get("updated_at")
                if not isinstance(updated_at, str):
                    report["skipped"] += 1
                    continue
                try:
                    updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                except ValueError:
                    report["skipped"] += 1
                    continue
                if updated.tzinfo is None or updated > cutoff:
                    report["skipped"] += 1
                    continue
                self.cleanup(job_id, worker_id)
                report["removed"] += 1
            except (OSError, ValueError, TypeError, WorkspaceError, json.JSONDecodeError):
                # Corrupt or concurrently changing ownership evidence is never deleted.
                report["skipped"] += 1
        return report

    def cleanup(self, job_id: str, worker_id: str) -> None:
        """Remove only the exact workspace whose marker proves matching ownership."""
        target = self.get(job_id, worker_id)
        shutil.rmtree(target)
