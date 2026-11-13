"""Durable, one-time grants for app-authorized Terminal Studio execution.

This store is an internal Gateway primitive. It does not authenticate callers,
authorize projects, or verify Runner credentials; those checks must happen in
the authenticated Gateway handler before issue/bind/consume are called.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .sqlite_security import prepare_private_sqlite_file


class TerminalGrantError(RuntimeError):
    """A Terminal execution grant is invalid, expired, revoked, or already used."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WORKER = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
_SUBJECT = re.compile(r"^[A-Za-z0-9._:@/-]{1,256}$")
_SESSION = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_ALLOWED_ACTIONS = frozenset({"terminal.read_only"})


def _uuid(value: str, field: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"{field} must be a canonical UUID") from None
    if str(parsed) != value:
        raise ValueError(f"{field} must be a canonical lowercase UUID")
    return value


def _digest(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _utc(value=None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("now must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


class TerminalGrantStore:
    """SQLite-backed grants, bound once to a durable Job and Runner identity."""

    def __init__(self, path="dcp-terminal-grants.sqlite3"):
        self.path = str(path)
        self.lock = threading.RLock()
        prepare_private_sqlite_file(self.path)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS terminal_grants (
                    grant_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    template_digest TEXT NOT NULL,
                    parameters_sha256 TEXT NOT NULL,
                    action TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    job_id TEXT UNIQUE,
                    worker_id TEXT,
                    consumed_at TEXT,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS terminal_grants_expiry_idx
                    ON terminal_grants(expires_at, revoked_at, consumed_at);
            """)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def parameters_digest(parameters: dict) -> str:
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def issue(
        self, *, subject: str, session_id: str, project_id: str,
        workspace_id: str, snapshot_sha256: str, template_id: str,
        template_digest: str, parameters_sha256: str,
        action: str = "terminal.read_only", ttl_seconds: int = 120, now=None,
    ) -> dict:
        """Issue a short-lived grant after the Gateway has completed app policy checks."""
        if not isinstance(subject, str) or not _SUBJECT.fullmatch(subject):
            raise ValueError("invalid subject")
        if not isinstance(session_id, str) or not _SESSION.fullmatch(session_id):
            raise ValueError("invalid session_id")
        _uuid(project_id, "project_id")
        _uuid(workspace_id, "workspace_id")
        _digest(snapshot_sha256, "snapshot_sha256")
        _digest(template_digest, "template_digest")
        _digest(parameters_sha256, "parameters_sha256")
        if not isinstance(template_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", template_id):
            raise ValueError("invalid template_id")
        if action not in _ALLOWED_ACTIONS:
            raise ValueError("unsupported Terminal grant action")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 15 <= ttl_seconds <= 300:
            raise ValueError("grant TTL must be between 15 and 300 seconds")
        issued = _utc(now)
        expires = issued + timedelta(seconds=ttl_seconds)
        grant_id = str(uuid.uuid4())
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """INSERT INTO terminal_grants(
                    grant_id,subject,session_id,project_id,workspace_id,
                    snapshot_sha256,template_id,template_digest,parameters_sha256,
                    action,issued_at,expires_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (grant_id, subject, session_id, project_id, workspace_id,
                 snapshot_sha256, template_id, template_digest, parameters_sha256,
                 action, issued.isoformat(), expires.isoformat()),
            )
            db.execute("COMMIT")
        return {"authorization_id": grant_id, "expires_at": expires.isoformat(), "action": action}

    def bind_job(self, grant_id: str, *, job_id: str, worker_id: str, now=None) -> dict:
        """Bind a grant exactly once to the queued job and its assigned Runner."""
        _uuid(grant_id, "grant_id")
        _uuid(job_id, "job_id")
        if not isinstance(worker_id, str) or not _WORKER.fullmatch(worker_id):
            raise ValueError("invalid worker_id")
        current = _utc(now).isoformat()
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM terminal_grants WHERE grant_id=?", (grant_id,)).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                raise TerminalGrantError("grant not found")
            if row["revoked_at"] or row["consumed_at"] or row["expires_at"] <= current:
                db.execute("ROLLBACK")
                raise TerminalGrantError("grant is not active")
            if row["job_id"] is not None:
                db.execute("ROLLBACK")
                raise TerminalGrantError("grant is already bound")
            db.execute(
                "UPDATE terminal_grants SET job_id=?,worker_id=? WHERE grant_id=? AND job_id IS NULL",
                (job_id, worker_id, grant_id),
            )
            db.execute("COMMIT")
        return {"authorization_id": grant_id, "job_id": job_id, "worker_id": worker_id}

    def consume(
        self, grant_id: str, *, job_id: str, worker_id: str, subject: str,
        session_id: str, project_id: str, workspace_id: str,
        snapshot_sha256: str, template_id: str, template_digest: str,
        parameters_sha256: str, action: str = "terminal.read_only", now=None,
    ) -> dict:
        """Atomically consume a grant after the Gateway authenticates the Runner and lease."""
        _uuid(grant_id, "grant_id")
        _uuid(job_id, "job_id")
        if not isinstance(worker_id, str) or not _WORKER.fullmatch(worker_id):
            raise ValueError("invalid worker_id")
        current = _utc(now).isoformat()
        expected = {
            "subject": subject, "session_id": session_id, "project_id": project_id,
            "workspace_id": workspace_id, "snapshot_sha256": snapshot_sha256,
            "template_id": template_id, "template_digest": template_digest,
            "parameters_sha256": parameters_sha256, "action": action,
        }
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM terminal_grants WHERE grant_id=?", (grant_id,)).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                raise TerminalGrantError("grant not found")
            if row["revoked_at"] or row["consumed_at"] or row["expires_at"] <= current:
                db.execute("ROLLBACK")
                raise TerminalGrantError("grant is not active")
            if row["job_id"] != job_id or row["worker_id"] != worker_id:
                db.execute("ROLLBACK")
                raise TerminalGrantError("grant is not bound to this Job and Runner")
            if any(row[key] != value for key, value in expected.items()):
                db.execute("ROLLBACK")
                raise TerminalGrantError("grant scope does not match the claimed job")
            changed = db.execute(
                "UPDATE terminal_grants SET consumed_at=? WHERE grant_id=? AND consumed_at IS NULL AND revoked_at IS NULL",
                (current, grant_id),
            ).rowcount
            if changed != 1:
                db.execute("ROLLBACK")
                raise TerminalGrantError("grant has already been consumed")
            db.execute("COMMIT")
        return {"authorization_id": grant_id, "job_id": job_id, "worker_id": worker_id,
                "action": action, "consumed_at": current, "authorized": True}

    def revoke(self, grant_id: str, *, now=None) -> bool:
        """Revoke an unused grant. Consumed grants remain consumed and cannot be revived."""
        _uuid(grant_id, "grant_id")
        current = _utc(now).isoformat()
        with self.lock, self.db() as db:
            changed = db.execute(
                "UPDATE terminal_grants SET revoked_at=? WHERE grant_id=? AND consumed_at IS NULL AND revoked_at IS NULL",
                (current, grant_id),
            ).rowcount
        return changed == 1
