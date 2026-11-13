"""Local-first durable job queue. This module never executes repository code."""
import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .sqlite_security import prepare_private_sqlite_file

class JobConflict(RuntimeError):
    pass

class JobNotFound(KeyError):
    pass

def utcnow():
    return datetime.now(timezone.utc)

class JobStore:
    """SQLite job lifecycle: queued, running, cancel_requested, and terminal states."""
    def __init__(self, path="dcp-jobs.sqlite3"):
        self.path = str(path)
        self.lock = threading.RLock()
        prepare_private_sqlite_file(self.path)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
                    repository TEXT NOT NULL, commit_sha TEXT NOT NULL, target TEXT NOT NULL,
                    state TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, worker TEXT, last_worker TEXT, lease_until TEXT,
                    cancel_at TEXT, result TEXT, error_code TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    checkpoint_json TEXT,
                    checkpoint_seq INTEGER NOT NULL DEFAULT 0,
                    checkpoint_sha256 TEXT,
                    retry_after TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_queue_idx ON jobs(state, created_at);
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, event TEXT NOT NULL,
                    detail TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_logs (
                    id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, stream TEXT NOT NULL,
                    message TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)
            # Preserve execution provenance separately from the active lease owner.
            columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
            if "last_worker" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN last_worker TEXT")
            if "attempt_count" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            if "max_attempts" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3")
            if "checkpoint_json" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN checkpoint_json TEXT")
            if "checkpoint_seq" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN checkpoint_seq INTEGER NOT NULL DEFAULT 0")
            if "checkpoint_sha256" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN checkpoint_sha256 TEXT")
            if "retry_after" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN retry_after TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_retry_idx ON jobs(state,retry_after,created_at)")

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        item = dict(row)
        for key in ("payload", "result"):
            item[key] = json.loads(item[key]) if item[key] else None
        item["checkpoint"] = json.loads(item.pop("checkpoint_json")) if item.get("checkpoint_json") else None
        return item

    @staticmethod
    def _event(db, job_id, event, detail=None):
        db.execute(
            "INSERT INTO job_events(job_id,event,detail,created_at) VALUES(?,?,?,?)",
            (job_id, event, json.dumps(detail or {}, sort_keys=True), utcnow().isoformat()),
        )

    def create(self, payload, idempotency_key):
        if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", idempotency_key):
            raise ValueError("Invalid Idempotency-Key")
        if not isinstance(payload, dict):
            raise ValueError("Job payload must be an object")
        source_type = payload.get("source_type", "github")
        target = payload.get("target", "test")
        if target not in ("test", "build", "package", "build_android", "build_web", "build_windows",
                          "build_linux", "build_macos", "build_ios", "build_static_web", "build_vite", "build_next", "build_angular", "test_static_web"):
            raise ValueError("Unsupported target")
        if source_type == "github":
            if not set(payload).issubset({"source_type", "repository", "commit_sha", "target"}):
                raise ValueError("Unsupported GitHub job payload fields")
            repository, sha = payload.get("repository"), payload.get("commit_sha")
            if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repository):
                raise ValueError("Invalid repository")
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise ValueError("Invalid commit SHA")
            normalized = {
                "source_type": "github", "source_id": repository, "source_sha256": None,
                "repository": repository, "commit_sha": sha, "target": target,
            }
        elif source_type == "local_folder":
            if set(payload) != {"source_type", "project_id", "snapshot_sha256", "target"}:
                raise ValueError("Local Folder jobs require only project_id, snapshot_sha256, and target")
            project_id, snapshot_sha = payload.get("project_id"), payload.get("snapshot_sha256")
            try:
                parsed_project_id = uuid.UUID(project_id)
            except (ValueError, TypeError, AttributeError):
                raise ValueError("Invalid local project ID") from None
            if str(parsed_project_id) != project_id:
                raise ValueError("Local project ID must use canonical lowercase UUID form")
            if not isinstance(snapshot_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha):
                raise ValueError("Invalid local project snapshot SHA-256")
            if target not in ("build_static_web", "test_static_web"):
                raise ValueError("Local Folder jobs support static web build or Playwright test targets only; dependency-managed frameworks are deferred")
            repository = "local-folder/" + project_id
            sha = hashlib.sha1(("dcp-local-folder:" + project_id + ":" + snapshot_sha).encode("utf-8")).hexdigest()
            normalized = {
                "source_type": "local_folder", "source_id": project_id,
                "source_sha256": snapshot_sha, "repository": repository,
                "commit_sha": sha, "target": target,
            }
        else:
            raise ValueError("Unsupported job source type")
        fingerprint = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        job_id, timestamp = str(uuid.uuid4()), utcnow().isoformat()
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM jobs WHERE idem=?", (idempotency_key,)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise JobConflict("Idempotency key conflict")
                db.execute("COMMIT")
                return self._decode(old), False
            db.execute(
                "INSERT INTO jobs(id,idem,fingerprint,repository,commit_sha,target,state,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,'queued',?,?,?)",
                (job_id, idempotency_key, fingerprint, repository, sha, target,
                 json.dumps(normalized), timestamp, timestamp),
            )
            self._event(db, job_id, "queued", {"source_type": normalized["source_type"]})
            db.execute("COMMIT")
        return self.get(job_id), True

    def get(self, job_id):
        with self.lock, self.db() as db:
            return self._decode(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def list_recent(self, limit=50):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("Invalid limit")
        with self.lock, self.db() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
            return [self._decode(row) for row in rows]

    @staticmethod
    def _retry_delay_seconds(job_id, attempt_count):
        base = min(300, 5 * (2 ** max(0, attempt_count - 1)))
        jitter_byte = hashlib.sha256(f"{job_id}:{attempt_count}".encode("utf-8")).digest()[0]
        return min(300, base + (jitter_byte / 255.0) * 2.0)

    def recover_expired_leases(self):
        """Recover only from a declared safe checkpoint; otherwise preserve UNKNOWN."""
        current_dt = utcnow()
        current = current_dt.isoformat()
        recovered = []
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,state,worker,attempt_count,max_attempts,checkpoint_json,checkpoint_seq "
                "FROM jobs WHERE state IN ('running','cancel_requested') "
                "AND lease_until IS NOT NULL AND lease_until<=? ORDER BY lease_until,id",
                (current,),
            ).fetchall()
            for row in rows:
                retry_after = None
                if row["state"] == "cancel_requested":
                    state, event, error_code = "cancelled", "cancelled_after_lease_expiry", None
                elif row["attempt_count"] >= row["max_attempts"]:
                    state, event, error_code = "failed", "lease_expired_failed", "LEASE_EXPIRED"
                else:
                    checkpoint = json.loads(row["checkpoint_json"]) if row["checkpoint_json"] else None
                    replay_data = checkpoint.get("data") if isinstance(checkpoint, dict) else None
                    replayable = (
                        checkpoint
                        and checkpoint.get("safe_to_resume") is True
                        and checkpoint.get("step") == "ready-to-finish"
                        and isinstance(replay_data, dict)
                        and replay_data.get("outcome") in ("succeeded", "failed", "cancelled")
                        and isinstance(replay_data.get("result"), dict)
                    )
                    if replayable:
                        state, event, error_code = "retry_wait", "lease_expired_retry_wait", None
                        retry_after = (
                            current_dt + timedelta(
                                seconds=self._retry_delay_seconds(row["id"], row["attempt_count"])
                            )
                        ).isoformat()
                    else:
                        state, event, error_code = "unknown", "lease_expired_unknown", "OUTCOME_UNKNOWN"
                db.execute(
                    "UPDATE jobs SET state=?,last_worker=worker,worker=NULL,lease_until=NULL,"
                    "retry_after=?,updated_at=?,error_code=? WHERE id=?",
                    (state, retry_after, current, error_code, row["id"]),
                )
                self._event(db, row["id"], event, {
                    "worker": row["worker"],
                    "attempt_count": row["attempt_count"],
                    "max_attempts": row["max_attempts"],
                    "checkpoint_seq": row["checkpoint_seq"],
                    "retry_after": retry_after,
                })
                recovered.append({"id": row["id"], "state": state, "retry_after": retry_after})
            db.execute("COMMIT")
        return recovered

    def claim(self, worker, lease_seconds=30, allowed_targets=None):
        if not isinstance(worker, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", worker):
            raise ValueError("Invalid worker")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 5 <= lease_seconds <= 300:
            raise ValueError("Invalid lease")
        if allowed_targets is not None:
            supported = {"test", "build", "package", "build_android", "build_web",
                         "build_windows", "build_linux", "build_macos", "build_ios",
                         "build_static_web", "build_vite", "build_next", "build_angular", "test_static_web"}
            if (not isinstance(allowed_targets, (list, tuple, set, frozenset))
                    or any(not isinstance(item, str) or item not in supported for item in allowed_targets)):
                raise ValueError("Invalid allowed target list")
            allowed_targets = sorted(set(allowed_targets))
            if not allowed_targets:
                return None
        current = utcnow()
        expiry = (current + timedelta(seconds=lease_seconds)).isoformat()
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if allowed_targets is None:
                row = db.execute(
                    "SELECT * FROM jobs WHERE state IN ('queued','retry_wait') "
                    "AND (retry_after IS NULL OR retry_after<=?) ORDER BY created_at,id LIMIT 1",
                    (current.isoformat(),),
                ).fetchone()
            else:
                placeholders = ",".join("?" for _ in allowed_targets)
                row = db.execute(
                    f"SELECT * FROM jobs WHERE state IN ('queued','retry_wait') AND target IN ({placeholders}) "
                    "AND (retry_after IS NULL OR retry_after<=?) ORDER BY created_at,id LIMIT 1",
                    (*allowed_targets, current.isoformat()),
                ).fetchone()
            if row is None:
                db.execute("COMMIT")
                return None
            changed = db.execute(
                "UPDATE jobs SET state='running',worker=?,lease_until=?,updated_at=?,attempt_count=attempt_count+1,"
                "retry_after=NULL WHERE id=? AND state IN ('queued','retry_wait')",
                (worker, expiry, current.isoformat(), row["id"]),
            ).rowcount
            if changed != 1:
                db.execute("ROLLBACK")
                return None
            self._event(db, row["id"], "running", {
                "worker": worker,
                "attempt_count": row["attempt_count"] + 1,
                "max_attempts": row["max_attempts"],
            })
            db.execute("COMMIT")
        return self.get(row["id"])

    def checkpoint(self, job_id, worker, sequence, checkpoint):
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("Checkpoint sequence must be a positive integer")
        if not isinstance(checkpoint, dict) or set(checkpoint) != {"version", "step", "safe_to_resume", "data"}:
            raise ValueError("Checkpoint must contain version, step, safe_to_resume, and data only")
        if checkpoint.get("version") != 1 or isinstance(checkpoint.get("version"), bool):
            raise ValueError("Unsupported checkpoint version")
        step = checkpoint.get("step")
        if not isinstance(step, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", step):
            raise ValueError("Invalid checkpoint step")
        if not isinstance(checkpoint.get("safe_to_resume"), bool) or not isinstance(checkpoint.get("data"), dict):
            raise ValueError("Invalid checkpoint safety flag or data")
        def reject_sensitive_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if not isinstance(key, str) or re.search(
                        r"(?:secret|password|token|credential|authorization|private.?key)", key, re.I
                    ):
                        raise ValueError("Checkpoint contains a prohibited sensitive field")
                    reject_sensitive_keys(child)
            elif isinstance(value, list):
                for child in value:
                    reject_sensitive_keys(child)
        reject_sensitive_keys(checkpoint)
        encoded = json.dumps(checkpoint, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 32768:
            raise ValueError("Checkpoint exceeds the 32 KiB limit")
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        current = utcnow().isoformat()
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state,worker,lease_until,checkpoint_seq,checkpoint_sha256 FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobNotFound(job_id)
            if (row["state"] != "running" or row["worker"] != worker
                    or not row["lease_until"] or row["lease_until"] <= current):
                raise JobConflict("Worker does not own an active job lease")
            current_seq = row["checkpoint_seq"]
            if sequence == current_seq and row["checkpoint_sha256"] == digest:
                db.execute("COMMIT")
                return self.get(job_id)
            if sequence != current_seq + 1:
                raise JobConflict("Checkpoint sequence must advance by exactly one")
            db.execute(
                "UPDATE jobs SET checkpoint_json=?,checkpoint_seq=?,checkpoint_sha256=?,updated_at=? WHERE id=?",
                (encoded, sequence, digest, current, job_id),
            )
            self._event(db, job_id, "checkpoint_saved", {
                "sequence": sequence, "sha256": digest,
                "step": step, "safe_to_resume": checkpoint["safe_to_resume"],
            })
            db.execute("COMMIT")
        return self.get(job_id)

    def resume_unknown(self, job_id, actor):
        if (not isinstance(actor, str) or not actor or len(actor) > 200
                or any(ord(char) < 32 for char in actor)):
            raise ValueError("Invalid resume actor")
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,attempt_count,max_attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise JobNotFound(job_id)
            if row["state"] != "unknown":
                raise JobConflict("Only UNKNOWN jobs can be explicitly resumed")
            if row["attempt_count"] >= row["max_attempts"]:
                raise JobConflict("Job exhausted its maximum attempt count")
            db.execute(
                "UPDATE jobs SET state='queued',retry_after=NULL,error_code=NULL,updated_at=? WHERE id=?",
                (utcnow().isoformat(), job_id),
            )
            self._event(db, job_id, "owner_resumed_unknown", {
                "actor": actor, "attempt_count": row["attempt_count"],
                "checkpoint_seq": db.execute(
                    "SELECT checkpoint_seq FROM jobs WHERE id=?", (job_id,)
                ).fetchone()["checkpoint_seq"],
            })
            db.execute("COMMIT")
        return self.get(job_id)

    def heartbeat(self, job_id, worker, lease_seconds=30):
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 5 <= lease_seconds <= 300:
            raise ValueError("Invalid lease")
        current = utcnow()
        expiry = (current + timedelta(seconds=lease_seconds)).isoformat()
        with self.lock, self.db() as db:
            changed = db.execute(
                "UPDATE jobs SET lease_until=?,updated_at=? WHERE id=? AND state IN ('running','cancel_requested') AND worker=? AND lease_until>?",
                (expiry, current.isoformat(), job_id, worker, current.isoformat()),
            ).rowcount
            if not changed:
                raise JobConflict("Worker does not own active job lease")
        return self.get(job_id)

    def cancel(self, job_id):
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise JobNotFound(job_id)
            if row["state"] == "queued":
                db.execute("UPDATE jobs SET state='cancelled',updated_at=? WHERE id=?", (utcnow().isoformat(), job_id))
                self._event(db, job_id, "cancelled")
            elif row["state"] == "running":
                timestamp = utcnow().isoformat()
                db.execute("UPDATE jobs SET state='cancel_requested',cancel_at=?,updated_at=? WHERE id=?", (timestamp, timestamp, job_id))
                self._event(db, job_id, "cancel_requested")
            db.execute("COMMIT")
        return self.get(job_id)

    def finish(self, job_id, worker, outcome, result=None, error_code=None):
        if outcome not in ("succeeded", "failed", "cancelled"):
            raise ValueError("Invalid terminal outcome")
        if result is not None and not isinstance(result, dict):
            raise ValueError("result must be an object")
        if error_code is not None and (not isinstance(error_code, str) or not re.fullmatch(r"[A-Z0-9_]{1,64}", error_code)):
            raise ValueError("Invalid error code")
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise JobNotFound(job_id)
            if (row["state"] not in ("running", "cancel_requested") or row["worker"] != worker
                    or not row["lease_until"] or row["lease_until"] <= utcnow().isoformat()):
                raise JobConflict("Worker does not own an active job lease")
            if row["state"] == "cancel_requested" and outcome == "succeeded":
                raise JobConflict("Cancellation must be acknowledged")
            db.execute(
                "UPDATE jobs SET state=?,updated_at=?,worker=NULL,last_worker=?,lease_until=NULL,result=?,error_code=? WHERE id=?",
                (outcome, utcnow().isoformat(), worker,
                 json.dumps(result) if result is not None else None, error_code, job_id),
            )
            self._event(db, job_id, outcome, {"error_code": error_code} if error_code else {})
            db.execute("COMMIT")
        return self.get(job_id)

    def append_log(self, job_id, worker, message, stream="stdout"):
        if stream not in ("stdout", "stderr", "system"):
            raise ValueError("Invalid stream")
        if not isinstance(message, str) or not message or len(message.encode("utf-8")) > 8192:
            raise ValueError("Log message must be 1..8192 bytes")
        with self.lock, self.db() as db:
            row = db.execute("SELECT state,worker,lease_until FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise JobNotFound(job_id)
            if (row["state"] not in ("running", "cancel_requested") or row["worker"] != worker
                    or not row["lease_until"] or row["lease_until"] <= utcnow().isoformat()):
                raise JobConflict("Worker does not own an active job lease")
            db.execute("INSERT INTO job_logs(job_id,stream,message,created_at) VALUES(?,?,?,?)",
                       (job_id, stream, message, utcnow().isoformat()))

    def events(self, job_id):
        with self.lock, self.db() as db:
            if not db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
                raise JobNotFound(job_id)
            return [{"id": r["id"], "event": r["event"], "detail": json.loads(r["detail"]),
                     "created_at": r["created_at"]}
                    for r in db.execute("SELECT * FROM job_events WHERE job_id=? ORDER BY id", (job_id,))]

    def logs(self, job_id, after_id=0, limit=500):
        if isinstance(after_id, bool) or not isinstance(after_id, int) or after_id < 0:
            raise ValueError("Invalid after_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Invalid limit")
        with self.lock, self.db() as db:
            if not db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
                raise JobNotFound(job_id)
            return [dict(row) for row in db.execute(
                "SELECT * FROM job_logs WHERE job_id=? AND id>? ORDER BY id LIMIT ?",
                (job_id, after_id, limit),
            )]
