"""Fail-closed OS isolation contract for Terminal jobs.

This module deliberately does not claim to sandbox a process. It records the
platform backend required for a future verified launcher and keeps execution
blocked until that backend has passed host-level acceptance.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Literal


IsolationState = Literal["BLOCKED", "READY_FOR_ACCEPTANCE", "VERIFIED"]
PlatformName = Literal["windows", "linux", "macos"]


@dataclass(frozen=True)
class IsolationAssessment:
    platform: PlatformName | Literal["unsupported"]
    backend: str
    state: IsolationState
    available: bool
    network_isolated: bool
    filesystem_isolated: bool
    process_tree_contained: bool
    reason: str


_BACKENDS: dict[str, tuple[str, str]] = {
    "windows": (
        "appcontainer-lpac",
        "A signed native AppContainer/LPAC launcher with explicit filesystem "
        "capabilities, no network capability, and Job Object containment is required.",
    ),
    "linux": (
        "bubblewrap-namespaces-seccomp",
        "bubblewrap must create user, mount, PID, IPC, UTS and network namespaces; "
        "mount only an explicit read-only runtime plus the assigned workspace and "
        "per-job scratch; apply a reviewed seccomp profile.",
    ),
    "macos": (
        "signed-app-sandbox-helper",
        "A signed, entitlement-scoped App Sandbox helper must launch the child with "
        "explicit file/network entitlements; sandbox-exec is not accepted as a "
        "production security boundary.",
    ),
}


def assess_isolation_backend(
    platform: str | None = None,
    *,
    executable_lookup=shutil.which,
) -> IsolationAssessment:
    """Report backend prerequisites without claiming that isolation is enforced."""
    current = (platform or os.name).lower()
    if current in {"nt", "windows"}:
        name: PlatformName | Literal["unsupported"] = "windows"
    elif current in {"posix", "linux"}:
        import sys
        detected = sys.platform if platform is None or current == "posix" else current
        name = "macos" if detected in {"darwin", "macos"} else "linux"
    elif current in {"darwin", "macos"}:
        name = "macos"
    else:
        return IsolationAssessment(
            platform="unsupported",
            backend="none",
            state="BLOCKED",
            available=False,
            network_isolated=False,
            filesystem_isolated=False,
            process_tree_contained=False,
            reason="No reviewed OS isolation backend exists for this platform.",
        )

    backend, requirement = _BACKENDS[name]
    if name == "linux":
        bwrap = executable_lookup("bwrap", path="/usr/bin")
        if not bwrap:
            return IsolationAssessment(
                platform=name, backend=backend, state="BLOCKED", available=False,
                network_isolated=False, filesystem_isolated=False,
                process_tree_contained=False,
                reason="bubblewrap (bwrap) is not installed; " + requirement,
            )
        return IsolationAssessment(
            platform=name, backend=backend, state="READY_FOR_ACCEPTANCE",
            available=True, network_isolated=False, filesystem_isolated=False,
            process_tree_contained=False,
            reason="bwrap is present, but namespace, mount, seccomp, network-denial "
                   "and process-cleanup acceptance has not been run; " + requirement,
        )

    return IsolationAssessment(
        platform=name,
        backend=backend,
        state="BLOCKED",
        available=False,
        network_isolated=False,
        filesystem_isolated=False,
        process_tree_contained=False,
        reason=requirement,
    )


def require_verified_isolation(assessment: IsolationAssessment) -> None:
    """Reject execution unless a future trusted verifier returns VERIFIED."""
    if not isinstance(assessment, IsolationAssessment):
        raise TypeError("isolation assessment must be an IsolationAssessment")
    if (
        assessment.state != "VERIFIED"
        or not assessment.available
        or not assessment.network_isolated
        or not assessment.filesystem_isolated
        or not assessment.process_tree_contained
    ):
        raise RuntimeError(
            "Terminal execution is blocked: verified OS isolation is unavailable"
        )
