"""Persistent, inert Terminal Studio command-pack import.

Imported templates are data only. They are disabled and pending owner review;
this module never launches a process or interprets a script.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .sqlite_security import prepare_private_sqlite_file


_TEMPLATE_ID = re.compile(r"^custom-[a-z0-9][a-z0-9-]{1,62}$")
_ALLOWED_EXECUTABLES = frozenset({"git", "python", "node"})
_ALLOWED_PLATFORMS = frozenset({"windows", "linux", "macos"})
_ALLOWED_CATEGORIES = frozenset({"Git", "Toolchain", "Build", "Test", "DCP", "Security", "Other"})
_ALLOWED_MUTATIONS = frozenset({
    "read-only", "workspace-write", "dependency-install", "network",
    "destructive", "privileged",
})
_TEMPLATE_FIELDS = frozenset({
    "id", "name", "description", "category", "executable_id", "argv",
    "platforms", "timeout_seconds", "max_output_bytes", "network",
    "mutation_class",
})
_PACK_FIELDS = frozenset({"schema_version", "templates"})
_SHELL_META = re.compile(r"[;&|<>$\x60\r\n\x00]")


class TerminalTemplateError(ValueError):
    """A command pack is invalid or conflicts with an existing template."""


def _text(value, label, maximum, *, minimum=1):
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise TerminalTemplateError(f"{label} must be {minimum}..{maximum} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise TerminalTemplateError(f"{label} contains control characters")
    return value


def validate_command_pack(pack: dict) -> list[dict]:
    """Validate a strict v1 JSON pack; accept only inert argv metadata."""
    if not isinstance(pack, dict) or set(pack) != _PACK_FIELDS:
        raise TerminalTemplateError("command pack must contain only schema_version and templates")
    if type(pack.get("schema_version")) is not int or pack["schema_version"] != 1:
        raise TerminalTemplateError("unsupported command pack schema_version")
    rows = pack.get("templates")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise TerminalTemplateError("templates must contain 1..50 entries")

    normalized = []
    seen = set()
    for index, row in enumerate(rows):
        label = f"templates[{index}]"
        if not isinstance(row, dict) or set(row) != _TEMPLATE_FIELDS:
            raise TerminalTemplateError(f"{label} has missing or unsupported fields")
        template_id = row.get("id")
        if not isinstance(template_id, str) or not _TEMPLATE_ID.fullmatch(template_id):
            raise TerminalTemplateError(f"{label}.id must use the custom- prefix and safe slug format")
        if template_id in seen:
            raise TerminalTemplateError("duplicate template ID in command pack")
        seen.add(template_id)

        name = _text(row.get("name"), f"{label}.name", 80)
        description = _text(row.get("description"), f"{label}.description", 500)
        category = row.get("category")
        if not isinstance(category, str) or category not in _ALLOWED_CATEGORIES:
            raise TerminalTemplateError(f"{label}.category is not supported")
        executable_id = row.get("executable_id")
        if not isinstance(executable_id, str) or executable_id not in _ALLOWED_EXECUTABLES:
            raise TerminalTemplateError(f"{label}.executable_id is not allowlisted")

        argv = row.get("argv")
        if not isinstance(argv, list) or not 1 <= len(argv) <= 16:
            raise TerminalTemplateError(f"{label}.argv must contain 1..16 arguments")
        safe_argv = []
        for arg_index, arg in enumerate(argv):
            value = _text(arg, f"{label}.argv[{arg_index}]", 256)
            if _SHELL_META.search(value):
                raise TerminalTemplateError(f"{label}.argv[{arg_index}] contains shell metacharacters")
            if value in {"-c", "-e", "-p", "--eval", "--exec", "--command", "--require", "--import"}:
                raise TerminalTemplateError(f"{label}.argv[{arg_index}] uses a prohibited code-execution option")
            safe_argv.append(value)

        platforms = row.get("platforms")
        if (not isinstance(platforms, list) or not platforms or len(platforms) > 3
                or any(not isinstance(item, str) or item not in _ALLOWED_PLATFORMS for item in platforms)
                or len(set(platforms)) != len(platforms)):
            raise TerminalTemplateError(f"{label}.platforms must be unique supported platforms")

        timeout = row.get("timeout_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
            raise TerminalTemplateError(f"{label}.timeout_seconds must be 1..300")
        output_cap = row.get("max_output_bytes")
        if (isinstance(output_cap, bool) or not isinstance(output_cap, int)
                or not 1024 <= output_cap <= 1024 * 1024):
            raise TerminalTemplateError(f"{label}.max_output_bytes must be 1024..1048576")
        if row.get("network") != "denied":
            raise TerminalTemplateError(f"{label}.network must be denied")
        mutation = row.get("mutation_class")
        if not isinstance(mutation, str) or mutation not in _ALLOWED_MUTATIONS:
            raise TerminalTemplateError(f"{label}.mutation_class is not supported")

        normalized.append({
            "id": template_id,
            "name": name,
            "description": description,
            "category": category,
            "executable_id": executable_id,
            "argv": safe_argv,
            "platforms": list(platforms),
            "timeout_seconds": timeout,
            "max_output_bytes": output_cap,
            "network": "denied",
            "mutation_class": mutation,
            "working_directory_policy": "assigned_workspace_required",
            "environment_allowlist": [],
            "enabled": False,
            "approval_status": "pending_review",
            "execution_enabled": False,
        })
    return normalized


class TerminalTemplateStore:
    """SQLite store for imported templates and credential-free audit events."""

    def __init__(self, path):
        self.path = str(path)
        prepare_private_sqlite_file(self.path)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS terminal_templates (
                    id TEXT PRIMARY KEY,
                    template_json TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS terminal_template_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def import_pack(self, pack, actor):
        if not isinstance(actor, str) or not actor.strip() or len(actor) > 200:
            raise TerminalTemplateError("authenticated owner identity required")
        rows = validate_command_pack(pack)
        canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        source_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        now = self._now()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            for row in rows:
                exists = db.execute(
                    "SELECT 1 FROM terminal_templates WHERE id=?", (row["id"],)
                ).fetchone()
                if exists:
                    raise TerminalTemplateError("template ID already exists")
            for row in rows:
                db.execute(
                    "INSERT INTO terminal_templates(id,template_json,source_sha256,created_by,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (row["id"], json.dumps(row, sort_keys=True, separators=(",", ":")),
                     source_sha256, actor, now),
                )
                db.execute(
                    "INSERT INTO terminal_template_audit(template_id,event,actor,source_sha256,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (row["id"], "imported_pending_review", actor, source_sha256, now),
                )
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
        return {"imported": rows, "source_sha256": source_sha256}

    def list_imported(self):
        with self._connect() as db:
            rows = db.execute(
                "SELECT template_json,source_sha256,created_by,created_at "
                "FROM terminal_templates ORDER BY id"
            ).fetchall()
        result = []
        for row in rows:
            item = json.loads(row["template_json"])
            item.update({
                "source_sha256": row["source_sha256"],
                "created_by": row["created_by"],
                "created_at": row["created_at"],
            })
            result.append(item)
        return result

    def get_imported(self, template_id):
        with self._connect() as db:
            row = db.execute(
                "SELECT template_json,source_sha256 FROM terminal_templates WHERE id=?",
                (template_id,),
            ).fetchone()
        if row is None:
            return None
        item = json.loads(row["template_json"])
        item["source_sha256"] = row["source_sha256"]
        return item

    def events(self, template_id=None):
        with self._connect() as db:
            if template_id is None:
                rows = db.execute(
                    "SELECT template_id,event,actor,source_sha256,created_at "
                    "FROM terminal_template_audit ORDER BY id"
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT template_id,event,actor,source_sha256,created_at "
                    "FROM terminal_template_audit WHERE template_id=? ORDER BY id",
                    (template_id,),
                ).fetchall()
        return [dict(row) for row in rows]
