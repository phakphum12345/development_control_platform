"""Run the real Linux bubblewrap host-acceptance suite and emit JSON evidence.

Run from the repository root as the same unprivileged account used by the Runner:
    python3 -m tools.local_runner_agent.linux_host_acceptance

This harness never enables Terminal templates or changes Runner configuration.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.test_linux_sandbox import LinuxBubblewrapLauncherTests
from tests.test_terminal_executor import TerminalScriptExecutorTests


_REQUIRED_TESTS = (
    (LinuxBubblewrapLauncherTests, "test_actual_bubblewrap_enforces_filesystem_network_and_scratch_boundaries"),
    (LinuxBubblewrapLauncherTests, "test_actual_bubblewrap_denies_socket_families_io_uring_and_capabilities"),
    (LinuxBubblewrapLauncherTests, "test_actual_bubblewrap_does_not_follow_workspace_symlink_to_host_secret"),
    (TerminalScriptExecutorTests, "test_real_bubblewrap_executor_launches_catalog_command_with_seccomp_fd"),
    (TerminalScriptExecutorTests, "test_real_bubblewrap_timeout_kills_forked_child_after_new_session"),
)


def _evidence_base() -> dict:
    return {
        "protocol": "DCP-CEEP v1.0",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "kernel_release": platform.release(),
        "machine": platform.machine(),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "harness_python_version": platform.python_version(),
        "tests_expected": len(_REQUIRED_TESTS),
        "tests_run": 0,
        "skipped": 0,
        "failures": 0,
        "errors": 0,
    }


def main() -> int:
    evidence = _evidence_base()
    if not sys.platform.startswith("linux"):
        evidence.update({"status": "BLOCKED", "reason": "Linux host required"})
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 2

    bwrap = shutil.which("bwrap", path="/usr/bin")
    python = shutil.which("python", path="/usr/bin")
    python3 = shutil.which("python3", path="/usr/bin")
    if not bwrap or not python or not python3:
        evidence.update({
            "status": "BLOCKED",
            "reason": "approved /usr/bin bubblewrap, python and python3 runtimes are required",
            "bubblewrap_path": bwrap,
            "python_path": python,
            "python3_path": python3,
        })
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 2

    approved_root = Path("/usr/bin").resolve(strict=True)
    bwrap_path = Path(bwrap).resolve(strict=True)
    python_path = Path(python).resolve(strict=True)
    python3_path = Path(python3).resolve(strict=True)
    if (
        approved_root not in bwrap_path.parents
        or approved_root not in python_path.parents
        or approved_root not in python3_path.parents
    ):
        evidence.update({
            "status": "FAIL",
            "reason": "bubblewrap, python or python3 resolved outside approved /usr/bin",
            "bubblewrap_path": str(bwrap_path),
            "python_path": str(python_path),
            "python3_path": str(python3_path),
        })
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 1

    try:
        version = subprocess.run(
            [str(bwrap_path), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=True,
            shell=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        evidence.update({
            "status": "FAIL",
            "reason": f"bubblewrap version check failed: {type(exc).__name__}",
        })
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 1

    try:
        terminal_python_version = subprocess.run(
            [str(python_path), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=True,
            shell=False,
        )
        sandbox_python_version = subprocess.run(
            [str(python3_path), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=True,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        evidence.update({"status": "FAIL", "reason": f"Python runtime version check failed: {type(exc).__name__}"})
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 1

    suite = unittest.TestSuite(
        test_case(test_name) for test_case, test_name in _REQUIRED_TESTS
    )
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)
    evidence.update({
        "bubblewrap_path": str(bwrap_path),
        "bubblewrap_version": version,
        "terminal_python_path": str(python_path),
        "terminal_python_version": terminal_python_version.stdout.strip() or terminal_python_version.stderr.strip(),
        "sandbox_test_python3_path": str(python3_path),
        "sandbox_test_python3_version": sandbox_python_version.stdout.strip() or sandbox_python_version.stderr.strip(),
        "tests_run": result.testsRun,
        "skipped": len(result.skipped),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "failed_tests": [case.id() for case, _ in result.failures],
        "errored_tests": [case.id() for case, _ in result.errors],
        "skipped_tests": [case.id() for case, _ in result.skipped],
    })
    passed = (
        result.wasSuccessful()
        and result.testsRun == len(_REQUIRED_TESTS)
        and not result.skipped
    )
    evidence["status"] = "PASS" if passed else "FAIL"
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
