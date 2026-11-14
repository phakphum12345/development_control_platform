"""Explicit target-Windows acceptance harness for the PSEC Terminal candidate.

This script launches only fixed, locally-authored test payloads. It does not
enable Terminal templates or change the production VERIFIED gate.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from tools.local_runner_agent.windows_psec import probe_psec, probe_psec_spec
from tools.local_runner_agent.windows_psec_launcher import (
    WindowsPsecError,
    WindowsPsecLauncher,
)


def _environment() -> dict[str, str]:
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
    if not system_root:
        raise WindowsPsecError("SYSTEMROOT is unavailable")
    return {
        "SYSTEMROOT": system_root,
        "PATH": os.environ.get("PATH", ""),
        "CI": "true",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


def _read_only_network_payload() -> str:
    return r'''
import json, pathlib, socket, sys
workspace = pathlib.Path(sys.argv[1])
scratch = pathlib.Path(sys.argv[2])
canary = pathlib.Path(sys.argv[3])
port = int(sys.argv[4])
result = {}

try:
    result["workspace_read"] = "PASS" if (workspace / "read.txt").read_text(encoding="utf-8") == "DCP-WORKSPACE-READ" else "FAIL"
except Exception:
    result["workspace_read"] = "FAIL"

try:
    (workspace / "write-probe.txt").write_text("must-not-write", encoding="utf-8")
    result["workspace_read_only"] = "FAIL"
except OSError:
    result["workspace_read_only"] = "PASS"

try:
    (scratch / "scratch-probe.txt").write_text("scratch-write-ok", encoding="utf-8")
    result["scratch_write"] = "PASS"
except Exception:
    result["scratch_write"] = "FAIL"

try:
    value = canary.read_text(encoding="utf-8")
    result["host_profile_deny"] = "FAIL" if value == "DCP-HOST-CANARY" else "UNKNOWN"
except OSError:
    result["host_profile_deny"] = "PASS"

connection = None
try:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(1.5)
    connection.connect(("127.0.0.1", port))
    result["network_loopback_deny"] = "FAIL"
except OSError:
    result["network_loopback_deny"] = "PASS"
finally:
    if connection is not None:
        connection.close()

print(json.dumps(result, sort_keys=True))
'''


def _run_policy_acceptance(launcher, workspace: Path, scratch: Path, canary: Path, environment):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(2.0)
    port = server.getsockname()[1]
    accepted = []

    def accept_once():
        try:
            connection, _ = server.accept()
            accepted.append(True)
            connection.close()
        except OSError:
            pass

    listener = threading.Thread(target=accept_once, name="dcp-psec-loopback-canary", daemon=True)
    listener.start()
    command = [
        sys.executable,
        "-c",
        _read_only_network_payload(),
        str(workspace),
        str(scratch),
        str(canary),
        str(port),
    ]
    process = None
    try:
        process = launcher.launch(
            command,
            workspace=workspace,
            scratch=scratch,
            environment=environment,
        )
        return_code = process.wait(timeout=15)
        output = process.stdout.read()
        if return_code != 0:
            raise WindowsPsecError("PSEC policy acceptance payload exited non-zero")
        lines = [line for line in output.decode("utf-8", "replace").splitlines() if line.strip()]
        result = json.loads(lines[-1])
        if accepted:
            result["network_loopback_deny"] = "FAIL"
        return result
    finally:
        if process is not None:
            process.close()
        server.close()
        listener.join(timeout=3)


def _run_job_tree_acceptance(launcher, workspace: Path, scratch: Path, environment):
    marker = scratch / "escaped-child-marker.txt"
    parent_code = (
        "import subprocess,sys; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL, close_fds=True); "
        "print('DCP_PARENT_EXITED', flush=True)"
    )
    child_code = (
        "import pathlib,sys,time; time.sleep(4); "
        "pathlib.Path(sys.argv[1]).write_text('child-survived', encoding='utf-8')"
    )
    process = launcher.launch(
        [sys.executable, "-c", parent_code, child_code, str(marker)],
        workspace=workspace,
        scratch=scratch,
        environment=environment,
    )
    try:
        try:
            process.wait(timeout=2.0)
            tracked = False
        except subprocess.TimeoutExpired:
            tracked = True
        process.terminate_tree()
        process.wait(timeout=8)
        output = process.stdout.read().decode("utf-8", "replace")
        time.sleep(4.5)
        return {
            "job_object_tracks_descendant": "PASS" if tracked and "DCP_PARENT_EXITED" in output else "FAIL",
            "job_object_terminates_descendant": "PASS" if not marker.exists() else "FAIL",
        }
    finally:
        process.close()


def main() -> int:
    if os.name != "nt":
        print(json.dumps({"state": "BLOCKED", "reason": "Windows host required"}, sort_keys=True))
        return 2

    api = probe_psec()
    if api.state != "READY_FOR_ACCEPTANCE":
        print(json.dumps({"state": "BLOCKED", "psec_api": api.to_dict()}, sort_keys=True))
        return 2
    spec_ok, spec_reason = probe_psec_spec()
    if not spec_ok:
        print(json.dumps({
            "state": "BLOCKED",
            "psec_api": api.to_dict(),
            "psec_spec": {"state": "FAIL", "reason": spec_reason},
        }, sort_keys=True))
        return 2

    canary = None
    try:
        user_profile = Path(os.environ["USERPROFILE"]).resolve(strict=True)
        canary = user_profile / f".dcp-psec-canary-{uuid.uuid4().hex}.txt"
        canary.write_text("DCP-HOST-CANARY", encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="dcp-psec-host-acceptance-") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            scratch = root / "scratch"
            workspace.mkdir()
            scratch.mkdir()
            (workspace / "read.txt").write_text("DCP-WORKSPACE-READ", encoding="utf-8")

            launcher = WindowsPsecLauncher()
            environment = _environment()
            policy_results = _run_policy_acceptance(
                launcher, workspace, scratch, canary, environment
            )
            tree_results = _run_job_tree_acceptance(
                launcher, workspace, scratch, environment
            )

        results = {**policy_results, **tree_results}
        failures = [name for name, state in results.items() if state != "PASS"]
        output = {
            "state": "PASS" if not failures else "FAIL",
            "host": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "python": sys.version.split()[0],
                "build": platform.version(),
            },
            "psec_api": api.to_dict(),
            "psec_spec": {"state": "PASS", "reason": spec_reason},
            "checks": results,
            "failures": failures,
            "note": "This host acceptance result does not automatically set terminal isolation to VERIFIED.",
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if not failures else 1
    except Exception as exc:
        print(json.dumps({
            "state": "FAIL",
            "error_type": type(exc).__name__,
            "note": "No Terminal templates were enabled; the production VERIFIED gate remains closed.",
        }, indent=2, sort_keys=True))
        return 1
    finally:
        if canary is not None:
            try:
                canary.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
