"""Owner-approved, project-scoped document write proposals for the Gateway.

Scopes are persisted server-side. Browser requests can ask an owner to grant a
scope, but the writer always reloads and enforces the persisted grant.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path, PurePosixPath

from tools.document_workflow.writer import DocumentWriteError, write_document
from tools.local_runner_agent.local_project import LocalProjectError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")
_PROJECT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_MAX_CONTENT_BYTES = 512 * 1024
_GRANT_CONFIRMATION = "GRANT DOCUMENT WRITE SCOPE"
_WRITE_CONFIRMATION = "WRITE DOCUMENT"


class DocumentWorkflowError(ValueError):
    """A fail-closed document grant, proposal, or approval error."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _relative(value: str, suffixes: set[str] | None = None) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DocumentWorkflowError("A clean relative path is required.")
    normalized = value.replace("\\", "/")
    raw_parts = normalized.split("/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(p in ("", ".", "..") for p in raw_parts):
        raise DocumentWorkflowError("Path traversal and absolute paths are not allowed.")
    if ":" in path.parts[0]:
        raise DocumentWorkflowError("Drive-qualified paths are not allowed.")
    blocked = {".git", ".github", ".ssh", ".aws", ".azure", ".gnupg", ".kube",
               ".terraform", ".docker", ".config", ".secrets", "secrets",
               "credentials", "node_modules", ".venv", "venv"}
    if any(part.startswith(".") or part.lower() in blocked for part in path.parts):
        raise DocumentWorkflowError("Hidden, credential, and tool-control directories are not writable.")
    if suffixes is not None and path.suffix.lower() not in suffixes:
        raise DocumentWorkflowError("Only .md and .txt documents are supported.")
    return path


class DocumentWorkflowStore:
    """Persist grants and immutable write proposals, then delegate verified writes."""

    def __init__(self, database_path: str | os.PathLike, registry, journal_path: str | os.PathLike | None = None):
        raw = Path(database_path).expanduser()
        if not raw.is_absolute():
            raise ValueError("document workflow database path must be absolute")
        raw.parent.mkdir(parents=True, exist_ok=True)
        if raw.exists() and raw.is_symlink():
            raise ValueError("document workflow database cannot be a symlink")
        self.database_path = raw.resolve()
        self.journal_path = Path(journal_path).expanduser() if journal_path else Path(str(self.database_path) + ".writer")
        if not self.journal_path.is_absolute():
            raise ValueError("document workflow journal path must be absolute")
        self.registry = registry
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS document_write_grants (
                    grant_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    prefixes_json TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_document_grants_project
                    ON document_write_grants(project_id, expires_at, revoked_at);
                CREATE TABLE IF NOT EXISTS document_workflow_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    target_path TEXT,
                    content_sha256 TEXT,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS document_write_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    expected_sha256 TEXT,
                    grant_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT
                );
            """)
        try:
            os.chmod(self.database_path, 0o600)
        except OSError:
            pass

    def _connect(self):
        db = sqlite3.connect(self.database_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            yield db
            if db.in_transaction:
                db.commit()
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def _project(self, project_id: str) -> Path:
        if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
            raise DocumentWorkflowError("Invalid project ID.")
        try:
            self.registry.reload()
            row = self.registry.refresh_project(project_id)
            root = Path(row["path"]).resolve(strict=True)
        except (LocalProjectError, KeyError, OSError, TypeError):
            raise DocumentWorkflowError("Registered Local Project is unavailable.", 404) from None
        if not root.is_dir() or root.is_symlink():
            raise DocumentWorkflowError("Registered Local Project is not a safe directory.", 409)
        return root

    @staticmethod
    def _target(root: Path, relative: PurePosixPath, require_parent: bool = True) -> Path:
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise DocumentWorkflowError("Symlinks are not allowed in document paths.", 400)
        parent = current.parent
        try:
            resolved_parent = parent.resolve(strict=require_parent)
            resolved_parent.relative_to(root)
        except (OSError, ValueError):
            raise DocumentWorkflowError("Document parent must exist inside the registered project.", 400) from None
        if require_parent and not resolved_parent.is_dir():
            raise DocumentWorkflowError("Document parent must be an existing directory.", 400)
        target = resolved_parent / current.name
        if target.exists() and (target.is_symlink() or not target.is_file()):
            raise DocumentWorkflowError("Document target must be a regular file.", 400)
        return target

    @staticmethod
    def _matches_scope(path: PurePosixPath, prefixes: list[str]) -> bool:
        for prefix in prefixes:
            scope = PurePosixPath(prefix)
            if path == scope or scope in path.parents:
                return True
        return False

    def grant_scope(self, project_id: str, prefixes, actor: str, confirmation: str) -> dict:
        if confirmation != _GRANT_CONFIRMATION:
            raise DocumentWorkflowError("Explicit scope confirmation is required.", 403)
        if not isinstance(actor, str) or not actor:
            raise DocumentWorkflowError("Authenticated owner identity is required.", 401)
        if not isinstance(prefixes, list) or not 1 <= len(prefixes) <= 20:
            raise DocumentWorkflowError("Provide 1..20 existing project-relative directories.")
        root = self._project(project_id)
        normalized = []
        for raw in prefixes:
            prefix = _relative(raw)
            target = self._target(root, prefix)
            if not target.exists() or not target.is_dir():
                raise DocumentWorkflowError("Every granted scope must be an existing directory.")
            normalized.append(prefix.as_posix())
        if len(set(normalized)) != len(normalized):
            raise DocumentWorkflowError("Duplicate write-scope paths are not allowed.")
        now = time.time()
        grant_id = str(uuid.uuid4())
        with self._db() as db:
            db.execute(
                """INSERT INTO document_write_grants
                (grant_id,project_id,prefixes_json,granted_by,created_at,expires_at)
                VALUES(?,?,?,?,?,?)""",
                (grant_id, project_id, json.dumps(normalized), actor, now, now + 30 * 86400),
            )
            db.execute(
                """INSERT INTO document_workflow_events
                (event_type,project_id,actor,target_path,created_at)
                VALUES('SCOPE_GRANTED',?,?,?,?)""",
                (project_id, actor, ",".join(normalized), now),
            )
        return {
            "grant_id": grant_id, "project_id": project_id,
            "allowed_paths": normalized, "granted_by": actor,
            "created_at": now, "expires_at": now + 30 * 86400,
            "status": "ACTIVE",
        }

    def list_grants(self, project_id: str | None = None) -> list[dict]:
        now = time.time()
        with self._db() as db:
            if project_id:
                rows = db.execute(
                    "SELECT * FROM document_write_grants WHERE project_id=? ORDER BY created_at DESC",
                    (project_id,),
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM document_write_grants ORDER BY created_at DESC").fetchall()
        return [{
            "grant_id": row["grant_id"], "project_id": row["project_id"],
            "allowed_paths": json.loads(row["prefixes_json"]),
            "granted_by": row["granted_by"], "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "status": "REVOKED" if row["revoked_at"] else ("ACTIVE" if row["expires_at"] > now else "EXPIRED"),
        } for row in rows]

    def revoke_grant(self, grant_id: str, actor: str, confirmation: str) -> dict:
        if confirmation != "REVOKE DOCUMENT WRITE SCOPE":
            raise DocumentWorkflowError("Explicit revocation confirmation is required.", 403)
        with self._db() as db:
            now = time.time()
            cursor = db.execute(
                "UPDATE document_write_grants SET revoked_at=? WHERE grant_id=? AND revoked_at IS NULL",
                (now, grant_id),
            )
            if cursor.rowcount != 1:
                raise DocumentWorkflowError("Active write grant not found.", 404)
            grant = db.execute(
                "SELECT project_id FROM document_write_grants WHERE grant_id=?", (grant_id,)
            ).fetchone()
            db.execute(
                """INSERT INTO document_workflow_events
                (event_type,project_id,actor,created_at)
                VALUES('SCOPE_REVOKED',?,?,?)""",
                (grant["project_id"], actor, now),
            )
        return {"grant_id": grant_id, "revoked_by": actor, "status": "REVOKED"}

    def inspect_target(self, project_id: str, relative_path: str) -> dict:
        relative = _relative(relative_path, {".md", ".txt"})
        root = self._project(project_id)
        target = self._target(root, relative)
        current_sha = _file_sha(target) if target.exists() else None
        now = time.time()
        active_grant = None
        with self._db() as db:
            grants = db.execute(
                """SELECT * FROM document_write_grants
                WHERE project_id=? AND revoked_at IS NULL AND expires_at>?
                ORDER BY created_at DESC""", (project_id, now)
            ).fetchall()
            for grant in grants:
                prefixes = json.loads(grant["prefixes_json"])
                if self._matches_scope(relative, prefixes):
                    active_grant = grant
                    break
        return {
            "project_id": project_id, "path": relative.as_posix(),
            "exists": target.exists(), "current_sha256": current_sha,
            "write_scope": "PASS" if active_grant else "FAIL",
            "grant_id": active_grant["grant_id"] if active_grant else None,
        }

    def propose(self, *, project_id: str, relative_path: str, content: str,
                expected_sha256: str | None, idempotency_key: str, actor: str) -> dict:
        if not isinstance(idempotency_key, str) or not _KEY.fullmatch(idempotency_key):
            raise DocumentWorkflowError("Idempotency-Key must be 16..128 safe characters.")
        if not isinstance(content, str) or not content.strip() or "\x00" in content:
            raise DocumentWorkflowError("Document content must be non-empty UTF-8 text.")
        payload = content.encode("utf-8")
        if len(payload) > _MAX_CONTENT_BYTES:
            raise DocumentWorkflowError("Document content exceeds the 512 KiB limit.", 413)
        if expected_sha256 is not None and not _SHA256.fullmatch(expected_sha256):
            raise DocumentWorkflowError("expected_sha256 must be a lowercase SHA-256 digest.")
        relative = _relative(relative_path, {".md", ".txt"})
        root = self._project(project_id)
        target = self._target(root, relative)
        actual = _sha(target.read_bytes()) if target.exists() else None
        if actual != expected_sha256:
            raise DocumentWorkflowError("Target base SHA changed; refresh before proposing.", 409)
        now = time.time()
        with self._db() as db:
            prior = db.execute(
                "SELECT * FROM document_write_proposals WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            desired = _sha(payload)
            if prior:
                if (prior["project_id"], prior["relative_path"], prior["content_sha256"], prior["expected_sha256"]) != (
                    project_id, relative.as_posix(), desired, expected_sha256
                ):
                    raise DocumentWorkflowError("Idempotency key was reused for a different proposal.", 409)
                return self._public_proposal(prior)
            grants = db.execute(
                """SELECT * FROM document_write_grants
                WHERE project_id=? AND revoked_at IS NULL AND expires_at>?
                ORDER BY created_at DESC""", (project_id, now)
            ).fetchall()
            selected = None
            for grant in grants:
                prefixes = json.loads(grant["prefixes_json"])
                if self._matches_scope(relative, prefixes):
                    selected = grant
                    break
            if selected is None:
                raise DocumentWorkflowError("No active server-side write grant covers this path.", 403)
            proposal_id = str(uuid.uuid4())
            expires = now + 30 * 60
            db.execute(
                """INSERT INTO document_write_proposals
                (proposal_id,idempotency_key,project_id,relative_path,content,content_sha256,
                 expected_sha256,grant_id,created_by,created_at,expires_at,status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,'PENDING')""",
                (proposal_id,idempotency_key,project_id,relative.as_posix(),content,desired,
                 expected_sha256,selected["grant_id"],actor,now,expires),
            )
            row = db.execute("SELECT * FROM document_write_proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            db.execute(
                """INSERT INTO document_workflow_events
                (event_type,project_id,actor,target_path,content_sha256,created_at)
                VALUES('WRITE_PROPOSED',?,?,?,?,?)""",
                (project_id, actor, relative.as_posix(), desired, now),
            )
        return self._public_proposal(row)

    @staticmethod
    def _public_proposal(row) -> dict:
        return {
            "proposal_id": row["proposal_id"], "project_id": row["project_id"],
            "path": row["relative_path"], "content_sha256": row["content_sha256"],
            "expected_sha256": row["expected_sha256"], "created_by": row["created_by"],
            "created_at": row["created_at"], "expires_at": row["expires_at"],
            "status": row["status"], "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }

    def get_proposal(self, proposal_id: str) -> dict:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM document_write_proposals WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
        if row is None:
            raise DocumentWorkflowError("Document proposal not found.", 404)
        return self._public_proposal(row)

    def approve(self, proposal_id: str, *, content_sha256: str, actor: str, confirmation: str) -> dict:
        if confirmation != _WRITE_CONFIRMATION:
            raise DocumentWorkflowError("Explicit write confirmation is required.", 403)
        if not isinstance(content_sha256, str) or not _SHA256.fullmatch(content_sha256):
            raise DocumentWorkflowError("A full content SHA-256 is required.")
        # Hold the workflow DB write lock through filesystem write and result
        # recording. A concurrent scope revocation cannot race an approval.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM document_write_proposals WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
            if row is None:
                raise DocumentWorkflowError("Document proposal not found.", 404)
            if row["status"] == "APPLIED" and row["result_json"]:
                return json.loads(row["result_json"])
            if row["status"] != "PENDING" or row["expires_at"] <= time.time():
                raise DocumentWorkflowError("Proposal is not pending or has expired.", 409)
            if not hmac_compare(row["content_sha256"], content_sha256):
                raise DocumentWorkflowError("Proposal content digest does not match approval.", 409)
            grant = db.execute(
                """SELECT * FROM document_write_grants WHERE grant_id=? AND project_id=?
                AND revoked_at IS NULL AND expires_at>?""",
                (row["grant_id"], row["project_id"], time.time()),
            ).fetchone()
            if grant is None:
                raise DocumentWorkflowError("Write grant expired or was revoked.", 403)
            prefixes = json.loads(grant["prefixes_json"])
            root = self._project(row["project_id"])
            relative = _relative(row["relative_path"], {".md", ".txt"})
            target = self._target(root, relative)
            actual = _file_sha(target) if target.exists() else None
            # A matching desired digest is the safe recovery path for a crash
            # after atomic replacement but before the proposal row was updated.
            if actual not in (row["expected_sha256"], row["content_sha256"]):
                raise DocumentWorkflowError("Target changed after proposal; refusing stale write.", 409)
            try:
                result = write_document(
                    workspace_root=root, journal_path=self.journal_path,
                    project_id=row["project_id"], relative_path=row["relative_path"],
                    content=row["content"], operation_key="document-proposal-" + proposal_id,
                    allowed_paths=prefixes, expected_sha256=row["expected_sha256"],
                )
            except DocumentWriteError as exc:
                raise DocumentWorkflowError(str(exc), 409) from None
            if result.get("status") != "PASS" or result.get("read_back_verified") is not True:
                raise DocumentWorkflowError("Post-write verification did not return PASS.", 503)
            result = {**result, "proposal_id": proposal_id, "approved_by": actor, "status": "PASS"}
            db.execute(
                "UPDATE document_write_proposals SET status='APPLIED',result_json=? WHERE proposal_id=?",
                (json.dumps(result, sort_keys=True), proposal_id),
            )
            db.execute(
                """INSERT INTO document_workflow_events
                (event_type,project_id,actor,target_path,content_sha256,created_at)
                VALUES('WRITE_APPLIED',?,?,?,?,?)""",
                (row["project_id"], actor, row["relative_path"], row["content_sha256"], time.time()),
            )
            return result


def hmac_compare(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left, right)
