"""Owner-scoped Gateway facade for local static previews.

Runtime capability tokens remain inside this process. Browser callers receive only
opaque runtime IDs and a same-origin proxy path; upstream hosts and ports are fixed
to loopback and are never accepted from requests.
"""
from __future__ import annotations

import http.client
import re
import threading
import uuid
from urllib.parse import quote

from tools.local_runner_agent.runtime import RuntimeErrorDCP, RuntimeManager


class PreviewError(RuntimeError):
    """Preview lookup, authorization, or upstream failure."""


class AuthenticatedPreviewManager:
    MAX_RESPONSE_BYTES = 8 * 1024 * 1024
    _RUNTIME_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    def __init__(self, runtime_manager: RuntimeManager):
        self.runtime_manager = runtime_manager
        self._tokens: dict[str, str] = {}
        self._jobs: dict[str, str] = {}
        self._lock = threading.RLock()

    def _prune_stale(self) -> None:
        for runtime_id, token in list(self._tokens.items()):
            try:
                status = self.runtime_manager.status(runtime_id, token)
                if status.get("state") != "running":
                    try:
                        self.runtime_manager.stop(runtime_id, token)
                    except RuntimeErrorDCP:
                        pass
                    self._tokens.pop(runtime_id, None)
                    self._jobs.pop(runtime_id, None)
            except RuntimeErrorDCP:
                self._tokens.pop(runtime_id, None)
                self._jobs.pop(runtime_id, None)

    def start(self, job_id: str, worker_id: str, output_relative: str = "source/dist", *, runtime_kind: str = "static", owner_approved: bool = False) -> dict:
        try:
            parsed_job_id = uuid.UUID(job_id)
        except (ValueError, TypeError, AttributeError):
            raise PreviewError("invalid job id") from None
        if str(parsed_job_id) != job_id:
            raise PreviewError("invalid job id")
        if not isinstance(worker_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", worker_id):
            raise PreviewError("invalid worker id")
        if output_relative not in ("source/dist", "source/dist/browser", "source/build/web", "dist", "dist/browser", "build/web"):
            raise PreviewError("unsupported preview output")
        with self._lock:
            self._prune_stale()
            try:
                self.runtime_manager.workspaces.retain_for_preview(
                    job_id, worker_id,
                    ttl_seconds=min(86400, self.runtime_manager.session_ttl_seconds + 60),
                )
            except Exception:
                raise PreviewError("job workspace is not retained for local preview") from None
            active_for_job = sum(1 for value in self._jobs.values() if value == job_id)
            if active_for_job:
                raise PreviewError("a preview is already active for this job")
            try:
                if runtime_kind == "static":
                    row = self.runtime_manager.start_static(
                        job_id, worker_id, output_relative=output_relative
                    )
                elif runtime_kind == "next":
                    if owner_approved is not True:
                        raise PreviewError("explicit Owner approval is required for Next.js runtime")
                    row = self.runtime_manager.start_next(
                        job_id, worker_id, owner_approved=True
                    )
                else:
                    raise PreviewError("unsupported preview runtime kind")
            except RuntimeErrorDCP as exc:
                raise PreviewError(str(exc)) from None
            runtime_id = row["runtime_id"]
            self._tokens[runtime_id] = row["session_token"]
            self._jobs[runtime_id] = job_id
            return {
                "runtime_id": runtime_id,
                "job_id": job_id,
                "runtime_kind": row.get("runtime_kind", runtime_kind),
                "state": "running",
                "preview_path": f"/api/jobs/{job_id}/previews/{runtime_id}/content/",
                "expires_in_seconds": row["expires_in_seconds"],
                "started_at": row["started_at"],
            }

    def status(self, runtime_id: str, job_id: str) -> dict:
        with self._lock:
            token = self._tokens.get(runtime_id)
            if token is None or self._jobs.get(runtime_id) != job_id:
                raise PreviewError("preview not found")
            try:
                row = self.runtime_manager.status(runtime_id, token)
            except RuntimeErrorDCP:
                self._tokens.pop(runtime_id, None)
                self._jobs.pop(runtime_id, None)
                raise PreviewError("preview is no longer available") from None
            return {
                "runtime_id": runtime_id, "job_id": job_id,
                "runtime_kind": row.get("runtime_kind", "static"),
                "state": row["state"],
                "expires_in_seconds": row["expires_in_seconds"],
            }

    def list_for_job(self, job_id: str) -> list[dict]:
        with self._lock:
            self._prune_stale()
            rows = []
            for runtime_id, bound_job in self._jobs.items():
                if bound_job != job_id:
                    continue
                token = self._tokens.get(runtime_id)
                if not token:
                    continue
                try:
                    status = self.runtime_manager.status(runtime_id, token)
                except RuntimeErrorDCP:
                    continue
                rows.append({
                    "runtime_id": runtime_id,
                    "job_id": job_id,
                    "runtime_kind": status.get("runtime_kind", "static"),
                    "state": status["state"],
                    "preview_path": f"/api/jobs/{job_id}/previews/{runtime_id}/content/",
                    "expires_in_seconds": status["expires_in_seconds"],
                })
            return rows

    def reap_expired(self) -> int:
        with self._lock:
            self.runtime_manager.reap_expired()
            self._prune_stale()
            return self.runtime_manager.workspaces.cleanup_expired_preview_workspaces()

    def stop(self, runtime_id: str, job_id: str) -> dict:
        with self._lock:
            token = self._tokens.get(runtime_id)
            if token is None or self._jobs.get(runtime_id) != job_id:
                raise PreviewError("preview not found")
            try:
                result = self.runtime_manager.stop(runtime_id, token)
            except RuntimeErrorDCP:
                raise PreviewError("preview is no longer available") from None
            finally:
                self._tokens.pop(runtime_id, None)
                self._jobs.pop(runtime_id, None)
            return result

    @staticmethod
    def _safe_relative_path(relative_path: str) -> str:
        if not isinstance(relative_path, str) or len(relative_path) > 2048:
            raise PreviewError("invalid preview path")
        decoded = relative_path
        if (decoded.startswith("/") or chr(92) in decoded or chr(0) in decoded
                or any(ord(ch) < 32 for ch in decoded)):
            raise PreviewError("invalid preview path")
        parts = decoded.split("/")
        if any(part in ("", ".", "..") for part in parts[:-1]):
            raise PreviewError("invalid preview path")
        if any(part in (".", "..") for part in parts):
            raise PreviewError("invalid preview path")
        return "/" + "/".join(quote(part, safe="-._~!$&'()*+,;=:@") for part in parts if part)

    def get_content(self, runtime_id: str, job_id: str, relative_path: str) -> tuple[int, str, bytes]:
        if not self._RUNTIME_ID.fullmatch(runtime_id or ""):
            raise PreviewError("preview not found")
        target = self._safe_relative_path(relative_path)
        with self._lock:
            token = self._tokens.get(runtime_id)
            if token is None or self._jobs.get(runtime_id) != job_id:
                raise PreviewError("preview not found")
            try:
                status = self.runtime_manager.status(runtime_id, token)
            except RuntimeErrorDCP:
                self._tokens.pop(runtime_id, None)
                self._jobs.pop(runtime_id, None)
                raise PreviewError("preview is no longer available") from None
            if status["state"] != "running":
                raise PreviewError("preview is not running")
            port = status["port"]
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request("GET", target, headers={
                "Host": f"127.0.0.1:{port}", "Connection": "close",
                "Accept": "text/html,application/javascript,text/css,image/*,font/*,application/json,*/*",
            })
            response = connection.getresponse()
            content_type = response.getheader("Content-Type", "application/octet-stream")
            body = response.read(self.MAX_RESPONSE_BYTES + 1)
            if len(body) > self.MAX_RESPONSE_BYTES:
                raise PreviewError("preview response exceeds size limit")
            if response.status not in (200, 304, 404):
                raise PreviewError("preview upstream returned an unsupported status")
            if not re.match(r"^(text/|application/(javascript|json|manifest\+json)|image/|font/)", content_type, re.I):
                content_type = "application/octet-stream"
            return response.status, content_type, body
        except (OSError, http.client.HTTPException):
            raise PreviewError("preview upstream is unavailable") from None
        finally:
            connection.close()
