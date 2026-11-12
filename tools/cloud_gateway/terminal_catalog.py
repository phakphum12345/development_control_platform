"""Curated, non-executing command templates for Terminal Studio.

This module only describes commands. It never launches a process, accepts an
arbitrary executable, reads a workspace path, or evaluates imported scripts.
"""
from __future__ import annotations

from copy import deepcopy


_TEMPLATES = {
    "git_status": {
        "id": "git_status",
        "name": "Git status",
        "category": "Git",
        "description": "Show changed and untracked files in the assigned project.",
        "executable": "git",
        "argv": ["status", "--short"],
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
        "description": "Show the latest five commits in compact form.",
        "executable": "git",
        "argv": ["log", "-5", "--oneline", "--decorate"],
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
    "python_version": {
        "id": "python_version",
        "name": "Python version",
        "category": "Toolchain",
        "description": "Display the Python interpreter version.",
        "executable": "python",
        "argv": ["--version"],
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


def preview_template(template_id: str) -> dict:
    """Resolve one exact catalog ID into a safe argv preview; never execute it."""
    if not isinstance(template_id, str) or template_id not in _TEMPLATES:
        raise ValueError("unknown terminal template")
    result = deepcopy(_TEMPLATES[template_id])
    result["command_preview"] = [result["executable"], *result["argv"]]
    result["requires_execution_approval"] = False
    result["status"] = "PREVIEW_ONLY"
    return result
