"""Deterministic task planning from DCP project intelligence evidence."""
from __future__ import annotations
from typing import Any


class PlanningError(ValueError):
    pass


def plan_implementation(assessment: dict[str, Any], task_description: str) -> dict[str, Any]:
    if not isinstance(assessment, dict) or assessment.get("schema_version") != 1:
        raise PlanningError("assessment must use project intelligence schema version 1")
    if not isinstance(task_description, str) or not task_description.strip() or len(task_description) > 20_000:
        raise PlanningError("task_description must contain 1 to 20000 characters")
    inventory = assessment.get("inventory")
    if not isinstance(inventory, dict):
        raise PlanningError("assessment inventory is missing")
    profile = assessment.get("runner_profile")
    if not isinstance(profile, dict):
        raise PlanningError("assessment runner profile is missing")

    paths = inventory.get("sample_paths", [])
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise PlanningError("assessment sample_paths must be a list of relative paths")
    modules = sorted({path.split("/", 1)[0] for path in paths if "/" in path})
    stack = profile.get("stack", [])
    tools = profile.get("required_tools", [])
    gaps = assessment.get("gaps", [])
    if not isinstance(stack, list) or not isinstance(tools, list) or not isinstance(gaps, list):
        raise PlanningError("assessment stack, tools, or gaps are malformed")

    text = task_description.lower()
    topics = []
    for topic, terms in {
        "testing": ("test", "coverage", "quality", "verify"),
        "security": ("security", "auth", "permission", "credential", "secret"),
        "runner": ("runner", "build agent", "execution environment", "ci"),
        "api": ("api", "endpoint", "service", "gateway"),
        "dashboard": ("dashboard", "ui", "interface", "control panel"),
        "mobile": ("mobile", "android", "ios", "flutter"),
        "deployment": ("deploy", "release", "hosting", "publish"),
        "documentation": ("docs", "documentation", "readme"),
    }.items():
        if any(term in text for term in terms):
            topics.append(topic)

    steps = [
        {"id": "inspect", "title": "Confirm repository structure and task scope",
         "actions": ["Review detected manifests, modules, and architecture areas",
                     "Confirm the requested behavior and acceptance criteria"],
         "gate": "scope-reviewed"},
        {"id": "design", "title": "Design the smallest compatible change",
         "actions": ["Map affected modules and existing interfaces",
                     "Record assumptions, dependencies, and rollback considerations"],
         "gate": "design-reviewed"},
        {"id": "implement", "title": "Implement in an isolated feature branch",
         "actions": ["Reuse existing modules and contracts before adding new abstractions",
                     "Keep changes scoped to the accepted task"],
         "gate": "patch-reviewed"},
        {"id": "verify", "title": "Run approved validation and collect evidence",
         "actions": ["Verify toolchain availability before running commands",
                     "Run relevant tests and capture exit codes, logs, and exact source SHA"],
         "gate": "evidence-verified"},
        {"id": "handoff", "title": "Prepare reviewable delivery",
         "actions": ["Summarize changed files and remaining risks",
                     "Open or update a pull request for human review"],
         "gate": "owner-review"},
    ]
    if "testing" in topics:
        steps[2]["actions"].append("Add regression tests for the requested behavior")
    if "security" in topics:
        steps[1]["actions"].append("Threat-model trust boundaries, secrets, permissions, and failure modes")
        steps[3]["actions"].append("Run security and policy checks; report unverified checks as UNKNOWN")
    if "runner" in topics:
        steps[1]["actions"].append("Select an OS-specific runner profile from detected toolchain requirements")
        steps[3]["actions"].append("Verify runner isolation, network policy, budget, lifecycle, and cleanup")
    if "api" in topics:
        steps[2]["actions"].append("Preserve API schema and backward compatibility; add contract tests")
    if "dashboard" in topics:
        steps[2]["actions"].append("Preserve accessible navigation, responsive behavior, and explicit unavailable states")
    if "mobile" in topics:
        steps[3]["actions"].append("Validate on the requested target platform; emulator launch alone is not app acceptance")
    if "deployment" in topics:
        steps[4]["actions"].append("Deployment remains a separate owner-approved operation")

    return {
        "schema_version": 1,
        "status": "proposed",
        "task": task_description,
        "detected_topics": topics,
        "project_context": {"stack": stack, "modules": modules,
                            "available_tools": sorted(set(tools)),
                            "inventory_status": assessment.get("status", "unknown")},
        "steps": steps,
        "gaps_to_resolve": gaps,
        "assumptions": [
            "The repository inventory is bounded and may omit paths beyond the scan limit.",
            "Detected frameworks and commands are inferred from manifests, not executed or proven.",
            "The task description is user-provided; scope and acceptance criteria still require review.",
        ],
        "approval_boundaries": {
            "source_changes": "feature-branch-and-pull-request",
            "command_execution": "explicit-owner-approval",
            "cloud_resources": "owner-approval-and-budget-guard",
            "merge_deploy": "human-only",
        },
        "evidence_policy": "Only current, inspectable evidence bound to the exact full commit SHA can satisfy a verification gate.",
    }
