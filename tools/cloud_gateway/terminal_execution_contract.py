"""Strict typed request contract for App-authorized Terminal Studio jobs.

This module validates intent only. It does not authorize a user, resolve a
workspace path, create a job, or execute a process. Those decisions remain in
the authenticated Gateway and trusted Runner layers.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from .terminal_catalog import preview_template


class TerminalContractError(ValueError):
    """A Terminal Studio request violates the typed execution contract."""


_REQUEST_FIELDS = {
    "project_id",
    "workspace_id",
    "snapshot_sha256",
    "template_id",
    "parameters",
    "authorization_id",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_uuid(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise TerminalContractError(f"{field} must be a UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise TerminalContractError(f"{field} must be a UUID") from None
    if str(parsed) != value:
        raise TerminalContractError(f"{field} must use canonical lowercase UUID form")
    return value


def template_version_digest(template_id: str, parameters: dict) -> str:
    """Return a deterministic digest of the fully resolved trusted template version."""
    preview = preview_template(template_id, parameters)
    version_fields = (
        "id", "executable", "argv", "platforms", "working_directory_policy",
        "environment_allowlist", "network", "mutation_class", "timeout_seconds",
        "max_output_bytes", "approval_required", "execution_enabled",
    )
    canonical = json.dumps(
        {key: preview[key] for key in version_fields},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_terminal_request(payload: Any) -> dict:
    """Validate a browser request containing identifiers and typed parameters only.

    Deliberately rejects command, executable, argv, cwd, env, shell, runner,
    role, approval, and permission fields. Authorization is resolved separately
    from the authenticated app session; browser claims are never trusted.
    """
    if not isinstance(payload, dict) or set(payload) != _REQUEST_FIELDS:
        raise TerminalContractError("request must contain exactly the approved Terminal fields")

    project_id = _canonical_uuid(payload["project_id"], "project_id")
    workspace_id = _canonical_uuid(payload["workspace_id"], "workspace_id")
    authorization_id = _canonical_uuid(payload["authorization_id"], "authorization_id")

    snapshot_sha256 = payload["snapshot_sha256"]
    if not isinstance(snapshot_sha256, str) or not _SHA256.fullmatch(snapshot_sha256):
        raise TerminalContractError("snapshot_sha256 must be a lowercase SHA-256 digest")

    template_id = payload["template_id"]
    if not isinstance(template_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", template_id):
        raise TerminalContractError("invalid template_id")

    parameters = payload["parameters"]
    if not isinstance(parameters, dict) or len(parameters) > 16:
        raise TerminalContractError("parameters must be an object with at most 16 entries")

    try:
        preview = preview_template(template_id, parameters)
    except (ValueError, TypeError) as exc:
        raise TerminalContractError(str(exc)) from None

    # Keep the browser's data as identifiers and canonical typed values only.
    normalized = {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "snapshot_sha256": snapshot_sha256,
        "template_id": template_id,
        "parameters": preview["parameter_values"],
        "authorization_id": authorization_id,
    }
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return {
        "request": normalized,
        "request_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "template_version_digest": template_version_digest(template_id, parameters),
        "execution_enabled": preview["execution_enabled"] is True,
        "status": "VALIDATED_INTENT_NOT_AUTHORIZED",
    }
