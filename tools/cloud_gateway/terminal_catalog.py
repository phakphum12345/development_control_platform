"""Curated, non-executing command templates for Terminal Studio.

This module only describes commands. It never launches a process, accepts an
arbitrary executable, reads a workspace path, or evaluates imported scripts.
"""
from __future__ import annotations

import re
from copy import deepcopy


_TEMPLATES = {
    "git_status": {
        "id": "git_status",
        "name": "Git status",
        "category": "Git",
        "description": "Show changed and untracked files in the assigned project.",
        "executable": "git",
        "argv": ["status", "--short"],
        "parameters": [],
        "platforms": ["windows", "linux", "macos"],
        "working_directory_policy": "assigned_workspace_required",
        "environment_allowlist": ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT"],
        "network": "denied",
        "mutation_class": "read-only",
        "timeout_seconds": 15,
        "max_output_bytes": 65536,
        "approval_required": False,
        "execution_enabled": False,
    },
    "git_diff": {
        "id": "git_diff",
        "name": "Git diff",
        "category": "Git",
        "description": "Show tracked working-tree changes without changing files.",
        "executable": "git",
        "argv": ["diff", "--no-ext-diff", "--"],
        "parameters": [],
        "platforms": ["windows", "linux", "macos"],
        "working_directory_policy": "assigned_workspace_required",
        "environment_allowlist": ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT"],
        "network": "denied",
        "mutation_class": "read-only",
        "timeout_seconds": 20,
        "max_output_bytes": 262144,
        "approval_required": False,
        "execution_enabled": False,
    },
    "git_log": {
        "id": "git_log",
        "name": "Recent Git history",
        "category": "Git",
        "description": "Show a bounded number of recent commits in compact form.",
        "executable": "git",
        "argv": ["log", "-{limit}", "--oneline", "--decorate"],
        "parameters": [{
            "name": "limit", "label": "Maximum commits", "type": "integer",
            "required": False, "default": 5, "minimum": 1, "maximum": 50,
        }],
        "platforms": ["windows", "linux", "macos"],
        "working_directory_policy": "assigned_workspace_required",
        "environment_allowlist": ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT"],
        "network": "denied",
        "mutation_class": "read-only",
        "timeout_seconds": 15,
        "max_output_bytes": 65536,
        "approval_required": False,
        "execution_enabled": False,
    },
    "git_show_commit": {
        "id": "git_show_commit",
        "name": "Inspect a commit",
        "category": "Git",
        "description": "Show a bounded summary of one exact full commit SHA.",
        "executable": "git",
        "argv": ["show", "--no-ext-diff", "--stat", "--oneline", "{commit_sha}"],
        "parameters": [{
            "name": "commit_sha", "label": "Full commit SHA", "type": "commit_sha",
            "required": True, "placeholder": "40 hexadecimal characters",
        }],
        "platforms": ["windows", "linux", "macos"],
        "working_directory_policy": "assigned_workspace_required",
        "environment_allowlist": ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT"],
        "network": "denied",
        "mutation_class": "read-only",
        "timeout_seconds": 15,
        "max_output_bytes": 65536,
        "approval_required": False,
        "execution_enabled": False,
    },
    "git_diff_commit": {
        "id": "git_diff_commit",
        "name": "Compare working tree to commit",
        "category": "Git",
        "description": "Compare the assigned working tree with one exact full commit SHA.",
        "executable": "git",
        "argv": ["diff", "--no-ext-diff", "--no-color", "{commit_sha}", "--"],
        "parameters": [{
            "name": "commit_sha", "label": "Base commit SHA", "type": "commit_sha",
            "required": True, "placeholder": "40 hexadecimal characters",
        }],
        "platforms": ["windows", "linux", "macos"],
        "working_directory_policy": "assigned_workspace_required",
        "environment_allowlist": ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT"],
        "network": "denied",
        "mutation_class": "read-only",
        "timeout_seconds": 20,
        "max_output_bytes": 262144,
        "approval_required": False,
        "execution_enabled": False,
    },
    "python_version": {
        "id": "python_version",
        "name": "Python version",
        "category": "Toolchain",
        "description": "Display the Python interpreter version.",
        "executable": "python",
        "argv": ["--version"],
        "parameters": [],
        "platforms": ["windows", "linux", "macos"],
        "working_directory_policy": "assigned_workspace_required",
        "environment_allowlist": ["PATH"],
        "network": "denied",
        "mutation_class": "read-only",
        "timeout_seconds": 10,
        "max_output_bytes": 8192,
        "approval_required": False,
        "execution_enabled": False,
    },
    "node_version": {
        "id": "node_version",
        "name": "Node.js version",
        "category": "Toolchain",
        "description": "Display the Node.js runtime version.",
        "executable": "node",
        "argv": ["--version"],
        "parameters": [],
        "platforms": ["windows", "linux", "macos"],
        "working_directory_policy": "assigned_workspace_required",
        "environment_allowlist": ["PATH"],
        "network": "denied",
        "mutation_class": "read-only",
        "timeout_seconds": 10,
        "max_output_bytes": 8192,
        "approval_required": False,
        "execution_enabled": False,
    },
}


def list_templates() -> list[dict]:
    """Return defensive copies of the built-in, read-only template catalog."""
    return [deepcopy(_TEMPLATES[key]) for key in sorted(_TEMPLATES)]


def _validate_parameters(template: dict, parameters: dict) -> dict:
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    specs = {item["name"]: item for item in template.get("parameters", [])}
    if set(parameters) - set(specs):
        raise ValueError("unknown command parameter")
    values = {}
    for name, spec in specs.items():
        if name not in parameters:
            if spec.get("required"):
                raise ValueError("missing required parameter: " + name)
            raw = spec.get("default")
        else:
            raw = parameters[name]
        if spec["type"] == "integer":
            if isinstance(raw, bool):
                raise ValueError("parameter must be an integer: " + name)
            if isinstance(raw, str) and not re.fullmatch(r"[0-9]{1,2}", raw):
                raise ValueError("parameter must be a bounded integer: " + name)
            if not isinstance(raw, (str, int)):
                raise ValueError("parameter must be an integer: " + name)
            value = int(raw)
            if not spec["minimum"] <= value <= spec["maximum"]:
                raise ValueError("parameter is outside allowed bounds: " + name)
            values[name] = str(value)
        elif spec["type"] == "commit_sha":
            if not isinstance(raw, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", raw):
                raise ValueError("parameter must be a full 40-character commit SHA: " + name)
            values[name] = raw.lower()
        else:
            raise ValueError("unsupported command parameter type")
    return values



def validate_preview_payload(payload: dict) -> tuple[str, dict]:
    """Accept only a template ID and a bounded parameter object."""
    if (not isinstance(payload, dict) or "template_id" not in payload
            or not set(payload).issubset({"template_id", "parameters"})):
        raise ValueError("only template_id and optional parameters are accepted")
    template_id = payload["template_id"]
    if not isinstance(template_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", template_id):
        raise ValueError("invalid template_id")
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    return template_id, parameters


def preview_template(template_id: str, parameters: dict | None = None) -> dict:
    """Resolve one exact catalog ID into a safe argv preview; never execute it."""
    if not isinstance(template_id, str) or template_id not in _TEMPLATES:
        raise ValueError("unknown terminal template")
    result = deepcopy(_TEMPLATES[template_id])
    values = _validate_parameters(result, {} if parameters is None else parameters)
    argv = []
    for argument in result["argv"]:
        value = argument
        for name, parameter in values.items():
            value = value.replace("{" + name + "}", parameter)
        if "{" in value or "}" in value:
            raise ValueError("unresolved command parameter")
        argv.append(value)
    result["argv"] = argv
    result["parameter_values"] = values
    result["command_preview"] = [result["executable"], *argv]
    result["requires_execution_approval"] = False
    result["status"] = "EXECUTION_ENABLED" if result["execution_enabled"] is True else "PREVIEW_ONLY"
    return result
