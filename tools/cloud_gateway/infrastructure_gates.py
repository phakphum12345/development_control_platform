"""Persistent, independent owner-controlled infrastructure feature gates.

The switches are additional policy controls, never substitutes for provider
readiness, budget checks, or the static fail-closed configuration.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


GATE_CONFIRMATIONS = {
    "cloud_provisioning": "ENABLE CLOUD PROVISIONING",
    "vm_creation": "ENABLE VM CREATION",
}


class InfrastructureGateError(ValueError):
    pass


class GateUnavailable(InfrastructureGateError):
    pass


class InfrastructureGateStore:
    def __init__(self, path):
        self.path = str(path)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS infrastructure_gates (
                    gate TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
                    updated_by TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS infrastructure_gate_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gate TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            now = self._now()
            for gate in GATE_CONFIRMATIONS:
                db.execute(
                    "INSERT OR IGNORE INTO infrastructure_gates(gate,enabled,updated_by,updated_at) VALUES(?,0,'',?)",
                    (gate, now),
                )

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def status(self, readiness=None):
        readiness = readiness or {}
        with self._connect() as db:
            rows = db.execute(
                "SELECT gate,enabled,updated_by,updated_at FROM infrastructure_gates ORDER BY gate"
            ).fetchall()
        result = {}
        for row in rows:
            ready = readiness.get(row["gate"]) is True
            enabled = bool(row["enabled"])
            result[row["gate"]] = {
                "enabled": enabled,
                "effective_enabled": enabled and ready,
                "ready": ready,
                "updated_by": row["updated_by"] or None,
                "updated_at": row["updated_at"],
            }
        return result

    def set_enabled(self, gate, enabled, actor, confirmation="", capability_ready=False):
        if gate not in GATE_CONFIRMATIONS:
            raise InfrastructureGateError("Unknown infrastructure gate")
        if type(enabled) is not bool:
            raise InfrastructureGateError("enabled must be a boolean")
        if not isinstance(actor, str) or not actor.strip():
            raise InfrastructureGateError("authenticated owner identity required")
        if enabled:
            if confirmation != GATE_CONFIRMATIONS[gate]:
                raise InfrastructureGateError("explicit gate confirmation does not match")
            if capability_ready is not True:
                raise GateUnavailable("provider capability is not ready; gate remains OFF")
        now = self._now()
        with self._connect() as db:
            db.execute(
                "UPDATE infrastructure_gates SET enabled=?,updated_by=?,updated_at=? WHERE gate=?",
                (int(enabled), actor, now, gate),
            )
            db.execute(
                "INSERT INTO infrastructure_gate_audit(gate,enabled,actor,created_at) VALUES(?,?,?,?)",
                (gate, int(enabled), actor, now),
            )
        return self.status({gate: capability_ready})[gate]

    def events(self, gate=None):
        with self._connect() as db:
            if gate is None:
                rows = db.execute(
                    "SELECT gate,enabled,actor,created_at FROM infrastructure_gate_audit ORDER BY id"
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT gate,enabled,actor,created_at FROM infrastructure_gate_audit WHERE gate=? ORDER BY id",
                    (gate,),
                ).fetchall()
        return [dict(row) for row in rows]
