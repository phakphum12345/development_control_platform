"""App-side policy gate for issuing Terminal execution grants."""
from __future__ import annotations

from .terminal_catalog import preview_template
from .terminal_execution_contract import template_version_digest
from .terminal_grants import TerminalGrantStore
from tools.local_runner_agent.local_project import LocalProjectError


class TerminalAuthorizationError(RuntimeError):
    """A trusted app identity or requested Terminal scope is not authorized."""


def issue_terminal_grant(identity: dict, payload: dict, registry, grants: TerminalGrantStore,
                         *, now=None) -> dict:
    """Issue a grant only after trusted identity, workspace and template policy checks.

    This function is called only from the authenticated, same-origin, CSRF-protected
    Gateway endpoint. It never accepts caller-supplied role, actor, path, executable,
    argv, approval, or Runner identity fields.
    """
    if not isinstance(identity, dict) or identity.get("role") != "owner":
        raise TerminalAuthorizationError("owner role is required for Terminal execution")
    subject = identity.get("subject")
    session_id = identity.get("session_id")
    if not isinstance(payload, dict) or set(payload) != {
        "project_id", "workspace_id", "snapshot_sha256", "template_id", "parameters",
    }:
        raise TerminalAuthorizationError("Terminal authorization fields are invalid")
    if registry is None or grants is None:
        raise TerminalAuthorizationError("Terminal authorization services are unavailable")

    try:
        workspace = registry.resolve_workspace(
            payload["project_id"], payload["workspace_id"], payload["snapshot_sha256"]
        )
        preview = preview_template(payload["template_id"], payload["parameters"])
    except (LocalProjectError, ValueError, TypeError) as exc:
        raise TerminalAuthorizationError(str(exc)) from None

    # Keep the first executable scope deliberately narrow. All current catalog
    # templates are disabled, so this rejects until Runner-side acceptance lands.
    if (preview.get("execution_enabled") is not True
            or preview.get("mutation_class") != "read-only"
            or preview.get("network") != "denied"
            or preview.get("approval_required") is not False):
        raise TerminalAuthorizationError("Terminal template is not enabled for safe execution")

    normalized_parameters = preview.get("parameter_values")
    if not isinstance(normalized_parameters, dict):
        raise TerminalAuthorizationError("Terminal template returned invalid normalized parameters")
    return grants.issue(
        subject=subject,
        session_id=session_id,
        project_id=workspace["project_id"],
        workspace_id=workspace["workspace_id"],
        snapshot_sha256=workspace["snapshot_sha256"],
        template_id=preview["id"],
        template_digest=template_version_digest(payload["template_id"], payload["parameters"]),
        parameters_sha256=grants.parameters_digest(normalized_parameters),
        action="terminal.read_only",
        ttl_seconds=120,
        now=now,
    )
