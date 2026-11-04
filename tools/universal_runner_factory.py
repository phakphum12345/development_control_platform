"""Policy-bound runner profile generation.

This module generates a reviewable execution plan only. It does not provision
cloud resources, install tools, launch processes, or execute repository code.
"""
from __future__ import annotations
import hashlib
import json
import re
from typing import Any

SUPPORTED_OS = {"linux", "windows", "macos"}
MAX_TOOLS = 80
MAX_COMMANDS = 40


class RunnerProfileError(ValueError):
    pass


def generate_runner_profile(assessment: dict[str, Any], target_os: str = "linux") -> dict[str, Any]:
    if target_os not in SUPPORTED_OS:
        raise RunnerProfileError("target_os must be linux, windows, or macos")
    if not isinstance(assessment, dict) or assessment.get("schema_version") != 1:
        raise RunnerProfileError("assessment must be a DCP project intelligence schema v1 object")
    profile = assessment.get("runner_profile")
    if not isinstance(profile, dict):
        raise RunnerProfileError("assessment does not contain a runner profile")
    tools = profile.get("required_tools", [])
    builds = profile.get("build_commands", [])
    tests = profile.get("test_commands", [])
    if not isinstance(tools, list) or len(tools) > MAX_TOOLS or any(
        not isinstance(x, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,80}", x) for x in tools
    ):
        raise RunnerProfileError("required_tools contains invalid entries")
    if not isinstance(builds, list) or not isinstance(tests, list) or len(builds) + len(tests) > MAX_COMMANDS:
        raise RunnerProfileError("command plan exceeds supported limits")
    for command in builds + tests:
        if not isinstance(command, list) or not command or any(
            not isinstance(part, str) or not part or len(part) > 300 for part in command
        ):
            raise RunnerProfileError("each command must be a nonempty argument array")
        if any(part in {";", "&&", "||", "|", ">", "<", "$("} or chr(96) in part for part in command):
            raise RunnerProfileError("shell operators are not allowed in generated command arguments")
    material = {
        "profile_version": 1,
        "workspace": assessment.get("workspace"),
        "target_os": target_os,
        "stack": profile.get("stack", []),
        "required_tools": sorted(set(tools)),
        "build_commands": builds,
        "test_commands": tests,
        "execution": {
            "mode": "dry-run", "shell": False, "network": "disabled-by-default",
            "ephemeral": True, "workspace_isolation": "required",
            "credential_injection": "prohibited", "owner_approval_required": True,
            "budget_guard_required": True, "evidence_gate_required": True,
        },
        "lifecycle": ["plan", "owner-approve", "prepare-isolated-workspace",
                      "verify-toolchain", "execute-approved-steps", "collect-logs",
                      "cleanup", "evidence-review"],
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    material["profile_id"] = hashlib.sha256(canonical).hexdigest()
    material["status"] = "proposed"
    material["notes"] = [
        "Profile generation does not execute commands or create infrastructure.",
        "The command list is inferred from manifests and must be reviewed for this repository.",
        "Real execution requires an isolated runner, explicit owner approval, policy checks, budget approval, and cleanup verification.",
    ]
    return material
