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
import shutil
import sys
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path

from tools.local_runner_agent.windows_psec import probe_psec, probe_psec_spec
from tools.local_runner_agent.windows_psec_launcher import (
    WindowsPsecError,
    WindowsPsecLauncher,
)
from tools.local_runner_agent.windows_psec_projection import create_workspace_projection


def _paths_overlap(left: str, right: str) -> bool:
    import ntpath

    a = ntpath.normcase(ntpath.normpath(left))
    b = ntpath.normcase(ntpath.normpath(right))
    try:
        common = ntpath.commonpath((a, b))
    except ValueError:
        return False
    return common == a or common == b


def _acceptance_parent() -> Path:
    configured = os.environ.get("DCP_PSEC_ACCEPTANCE_PARENT")
    if not configured:
        raise WindowsPsecError(
            "DCP_PSEC_ACCEPTANCE_PARENT must name an existing writable directory "
            "outside USERPROFILE, PROGRAMDATA, PUBLIC, TEMP, and SYSTEMROOT\\Temp"
        )
    parent = Path(configured)
    if not parent.is_absolute():
        raise WindowsPsecError("DCP_PSEC_ACCEPTANCE_PARENT must be an absolute path")
    try:
        parent = parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise WindowsPsecError("DCP_PSEC_ACCEPTANCE_PARENT must already exist") from None
    if not parent.is_dir():
        raise WindowsPsecError("DCP_PSEC_ACCEPTANCE_PARENT must be a directory")

    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
    denied_candidates = (
        os.environ.get("USERPROFILE"),
        os.environ.get("PROGRAMDATA"),
        os.environ.get("PUBLIC"),
        tempfile.gettempdir(),
        str(Path(system_root) / "Temp") if system_root else None,
    )
    for value in denied_candidates:
        if not value:
            continue
        try:
            denied = Path(value).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if _paths_overlap(str(parent), str(denied)):
            raise WindowsPsecError(
                "DCP_PSEC_ACCEPTANCE_PARENT overlaps a denied filesystem root: "
                + str(denied)
            )
    return parent



def _filesystem_acl(path: Path) -> dict:
    """Capture the host-visible ACL without changing any filesystem permissions."""
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
    if not system_root:
        return {"state": "UNKNOWN", "reason": "SYSTEMROOT is unavailable"}
    icacls = Path(system_root) / "System32" / "icacls.exe"
    if not icacls.is_file():
        return {"state": "UNKNOWN", "reason": "icacls.exe is unavailable"}
    try:
        completed = subprocess.run(
            [str(icacls), str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            shell=False,
        )
    except Exception as exc:
        return {
            "state": "ERROR",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    result = {
        "state": "CAPTURED" if completed.returncode == 0 else "ERROR",
        "path": str(path),
        "returncode": int(completed.returncode),
        "stdout": completed.stdout[:12000],
        "stderr": completed.stderr[:4000],
    }

    # icacls shows ACEs but not the security descriptor owner or whether the
    # DACL is protected from inheritance. Capture those fields read-only.
    powershell = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        result["security_descriptor"] = {
            "state": "UNKNOWN",
            "reason": "Windows PowerShell is unavailable",
        }
        return result
    script = (
        "$targetPath = $env:DCP_PSEC_ACL_PATH; "
        "if ([string]::IsNullOrWhiteSpace($targetPath)) { "
        "throw 'DCP_PSEC_ACL_PATH was not supplied' }; "
        "$acl = Get-Acl -LiteralPath $targetPath; "
        "[pscustomobject]@{ owner = $acl.Owner; "
        "dacl_protected = $acl.AreAccessRulesProtected; "
        "sddl = $acl.Sddl } | ConvertTo-Json -Compress"
    )
    try:
        descriptor = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            shell=False,
            env={**os.environ, "DCP_PSEC_ACL_PATH": str(path)},
        )
        if descriptor.returncode == 0:
            try:
                parsed = json.loads(descriptor.stdout)
                result["security_descriptor"] = {
                    "state": "CAPTURED",
                    "owner": parsed.get("owner"),
                    "dacl_protected": parsed.get("dacl_protected"),
                    "sddl": parsed.get("sddl"),
                }
            except (ValueError, AttributeError):
                result["security_descriptor"] = {
                    "state": "ERROR",
                    "reason": "PowerShell returned invalid descriptor JSON",
                    "stdout": descriptor.stdout[:4000],
                }
        else:
            result["security_descriptor"] = {
                "state": "ERROR",
                "returncode": int(descriptor.returncode),
                "stderr": descriptor.stderr[:4000],
            }
    except Exception as exc:
        result["security_descriptor"] = {
            "state": "ERROR",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    return result



def _app_container_profile_evidence(package_sid: str, child_token: dict) -> dict:
    """Read the Windows-managed AppContainer LocalAppData path and its ACL.

    GetAppContainerFolderPath is diagnostic only: the API returns a path, not
    proof that a profile is registered, that the directory exists, or that
    the child can access it. This function never creates a profile or changes
    filesystem permissions.
    """
    import ctypes
    from ctypes import wintypes

    if not isinstance(package_sid, str) or not package_sid.startswith("S-1-"):
        return {"state": "UNKNOWN", "reason": "Package SID is unavailable or invalid"}

    try:
        userenv = ctypes.WinDLL("userenv.dll", use_last_error=True)
        ole32 = ctypes.WinDLL("ole32.dll", use_last_error=True)
        get_folder = userenv.GetAppContainerFolderPath
        get_folder.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_wchar_p)]
        get_folder.restype = ctypes.c_long
        free_memory = ole32.CoTaskMemFree
        free_memory.argtypes = [ctypes.c_void_p]
        free_memory.restype = None

        folder = ctypes.c_wchar_p()
        hr = int(get_folder(package_sid, ctypes.byref(folder)))
        if hr != 0:
            return {
                "state": "UNKNOWN",
                "hresult": f"0x{hr & 0xFFFFFFFF:08X}",
                "reason": "GetAppContainerFolderPath did not return S_OK",
            }
        try:
            value = folder.value
            if not value:
                return {"state": "UNKNOWN", "reason": "API returned an empty path"}
            path = Path(value)
            try:
                exists = path.is_dir()
            except OSError:
                exists = False
            environment = child_token.get("environment", {})
            child_local_app_data = (
                environment.get("LOCALAPPDATA")
                if isinstance(environment, dict) else None
            )
            import ntpath
            matches = (
                ntpath.normcase(ntpath.normpath(child_local_app_data))
                == ntpath.normcase(ntpath.normpath(value))
                if isinstance(child_local_app_data, str) else None
            )
            return {
                "state": "CAPTURED",
                "path": value,
                "directory_exists": exists,
                "child_localappdata_matches": matches,
                "acl": _filesystem_acl(path) if exists else {
                    "state": "UNKNOWN",
                    "reason": "AppContainer folder path does not currently resolve to a directory",
                },
                "interpretation": (
                    "Path lookup only; profile registration and child access require "
                    "independent verification."
                ),
            }
        finally:
            if folder:
                free_memory(ctypes.cast(folder, ctypes.c_void_p))
    except Exception as exc:
        return {
            "state": "ERROR",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


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
import json, os, pathlib, socket, subprocess, sys, sysconfig
workspace = pathlib.Path(sys.argv[1])
scratch = pathlib.Path(sys.argv[2])
canary = pathlib.Path(sys.argv[3])
port = int(sys.argv[4])
base_home = pathlib.Path(sys.base_prefix)
venv_root = pathlib.Path(sys.prefix)
stdlib = pathlib.Path(sysconfig.get_path("stdlib"))
result = {}

def _read_probe(paths):
    for path in paths:
        with path.open("rb") as stream:
            stream.read(1)
    return "PASS"

def _write_probe(directory, label):
    probe = directory / f".dcp-psec-{label}-{os.getpid()}-{id(result)}.probe"
    try:
        with probe.open("xb") as stream:
            stream.write(b"must-not-write")
    except OSError:
        return "DENIED"
    try:
        probe.unlink()
    except OSError as exc:
        result[label + "_write_cleanup"] = "FAIL"
        result[label + "_write_cleanup_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    return "UNEXPECTED_WRITE"

# Query the token from inside this exact PSEC-launched process without
# importing ctypes/_ctypes, whose extension initialization may itself be
# restricted by the process security environment.
child_token = {
    "pid": os.getpid(),
    "parent_pid": os.getppid(),
    "environment": {
        key: os.environ.get(key)
        for key in ("USERNAME", "USERPROFILE", "LOCALAPPDATA", "TEMP", "TMP", "SYSTEMROOT", "PATH")
    },
}
try:
    whoami = pathlib.Path(os.environ["SYSTEMROOT"]) / "System32" / "whoami.exe"
    token_result = subprocess.run(
        [str(whoami), "/all"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=False,
        shell=False,
    )
    child_token["whoami"] = {
        "executable": str(whoami),
        "returncode": token_result.returncode,
        "stdout": token_result.stdout[:20000],
        "stderr": token_result.stderr[:4000],
    }
except Exception as exc:
    child_token["whoami_error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
        "winerror": getattr(exc, "winerror", None),
    }
result["child_token"] = child_token

try:
    base_executable = pathlib.Path(getattr(sys, "_base_executable", sys.executable))
    result["base_runtime_read"] = _read_probe((
        base_executable,
        base_home / "python312.dll",
    ))
except Exception as exc:
    result["base_runtime_read"] = "FAIL"
    result["base_runtime_read_error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }

try:
    result["standard_library_read"] = _read_probe((
        stdlib / "os.py",
        stdlib / "encodings" / "__init__.py",
    ))
except Exception as exc:
    result["standard_library_read"] = "FAIL"
    result["standard_library_read_error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }

try:
    result["venv_runtime_read"] = _read_probe((
        venv_root / "pyvenv.cfg",
        pathlib.Path(sys.executable),
    ))
except Exception as exc:
    result["venv_runtime_read"] = "FAIL"
    result["venv_runtime_read_error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }

result["base_runtime_write_probe"] = _write_probe(base_home, "base-runtime")
result["standard_library_write_probe"] = _write_probe(stdlib, "standard-library")
result["venv_runtime_write_probe"] = _write_probe(venv_root, "venv-runtime")
result["base_runtime_read_only"] = (
    "PASS" if result["base_runtime_read"] == "PASS"
    and result["base_runtime_write_probe"] == "DENIED" else "FAIL"
)
result["standard_library_read_only"] = (
    "PASS" if result["standard_library_read"] == "PASS"
    and result["standard_library_write_probe"] == "DENIED" else "FAIL"
)
result["venv_runtime_read_only"] = (
    "PASS" if result["venv_runtime_read"] == "PASS"
    and result["venv_runtime_write_probe"] == "DENIED" else "FAIL"
)

try:
    workspace_value = (workspace / "read.txt").read_text(encoding="utf-8")
    result["workspace_read"] = "PASS" if workspace_value == "DCP-WORKSPACE-READ" else "FAIL"
except Exception as exc:
    result["workspace_read"] = "FAIL"
    result["workspace_read_error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }

try:
    (workspace / "write-probe.txt").write_text("must-not-write", encoding="utf-8")
    result["workspace_write_probe"] = "UNEXPECTED_WRITE"
    result["workspace_read_only"] = "FAIL"
except OSError as exc:
    result["workspace_write_probe"] = "DENIED"
    result["workspace_read_only"] = (
        "PASS" if result["workspace_read"] == "PASS" else "FAIL"
    )
    result["workspace_write_error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }

try:
    (scratch / "scratch-probe.txt").write_text("scratch-write-ok", encoding="utf-8")
    result["scratch_write"] = "PASS"
except Exception as exc:
    result["scratch_write"] = "FAIL"
    result["scratch_write_error"] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }

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


_EXPECTED_WRITE_DENIALS = frozenset({
    "workspace_write_probe",
    "base_runtime_write_probe",
    "standard_library_write_probe",
    "venv_runtime_write_probe",
})


def _acceptance_failures(results: dict) -> list[str]:
    """Treat explicit denied-write probes as success; all other checks must PASS."""
    return [
        name for name, state in results.items()
        if state != "PASS" and not (
            name in _EXPECTED_WRITE_DENIALS and state == "DENIED"
        )
    ]


def _parse_policy_payload_output(return_code: int, output: bytes) -> dict:
    """Parse child evidence while preserving exit code and bounded raw output."""
    decoded = output.decode("utf-8", "replace") if isinstance(output, bytes) else str(output)
    evidence_tail = decoded[-16000:]
    if return_code != 0:
        raise WindowsPsecError(
            "PSEC policy acceptance payload exited non-zero; "
            f"exit_code={return_code}; child_output_tail={evidence_tail!r}"
        )
    lines = [line for line in decoded.splitlines() if line.strip()]
    if not lines:
        raise WindowsPsecError(
            "PSEC policy acceptance payload returned no JSON; "
            f"child_output_tail={evidence_tail!r}"
        )
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise WindowsPsecError(
            "PSEC policy acceptance payload returned invalid JSON; "
            f"child_output_tail={evidence_tail!r}"
        ) from exc
    if not isinstance(result, dict):
        raise WindowsPsecError(
            "PSEC policy acceptance payload JSON must be an object; "
            f"child_output_tail={evidence_tail!r}"
        )
    return result


def _run_policy_acceptance(launcher, workspace: Path, scratch: Path, canary: Path, environment, cleanup_state):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(2.0)
    port = server.getsockname()[1]
    accepted = []

    # Prove that loopback is reachable from the host before using it as a
    # sandbox network-denial canary.
    try:
        baseline = socket.create_connection(("127.0.0.1", port), timeout=1.0)
        host_connection, _ = server.accept()
        baseline.close()
        host_connection.close()
    except OSError:
        server.close()
        raise WindowsPsecError("host loopback baseline is unavailable; network policy cannot be assessed")

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
        cleanup_state["safe_to_cleanup"] = False
        process = launcher.launch(
            command,
            workspace=workspace,
            scratch=scratch,
            environment=environment,
        )
        return_code = process.wait(timeout=15)
        output = process.stdout.read()
        result = _parse_policy_payload_output(return_code, output)
        result["child_process_token"] = process.token_diagnostics
        if accepted:
            result["network_loopback_deny"] = "FAIL"
        return result
    finally:
        try:
            if process is not None:
                process.close()
                cleanup_state["safe_to_cleanup"] = True
        finally:
            server.close()
            listener.join(timeout=3)


def _run_job_tree_acceptance(launcher, workspace: Path, scratch: Path, environment, cleanup_state):
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
    cleanup_state["safe_to_cleanup"] = False
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
        cleanup_state["safe_to_cleanup"] = True


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
    source_root = None
    private_parent = None
    projection = None
    cleanup_state = {"safe_to_cleanup": True}
    output = None
    exit_code = 1
    cleanup_evidence = {"state": "NOT_STARTED"}
    canary_cleanup = {"state": "NOT_CREATED"}

    try:
        user_profile = Path(os.environ["USERPROFILE"]).resolve(strict=True)
        canary = user_profile / f".dcp-psec-canary-{uuid.uuid4().hex}.txt"
        canary.write_text("DCP-HOST-CANARY", encoding="utf-8")

        acceptance_parent = _acceptance_parent()
        source_root = Path(tempfile.mkdtemp(
            prefix="dcp-psec-source-", dir=str(acceptance_parent)
        ))
        private_parent = Path(tempfile.mkdtemp(
            prefix="dcp-psec-host-acceptance-", dir=str(acceptance_parent)
        ))
        source_workspace = source_root / "workspace"
        source_workspace.mkdir()
        (source_workspace / "read.txt").write_text(
            "DCP-WORKSPACE-READ", encoding="utf-8"
        )
        (source_workspace / "nested").mkdir()
        (source_workspace / "nested" / "nested.txt").write_text(
            "DCP-WORKSPACE-NESTED", encoding="utf-8"
        )

        # Use the production projection primitive so the ACL manager receives
        # the exact dcp-psec-job-*/workspace + scratch layout.
        projection = create_workspace_projection(source_workspace, private_parent)
        root = projection.root
        workspace = projection.workspace
        scratch = projection.scratch

        filesystem_acl_before = {
            "acceptance_parent": _filesystem_acl(acceptance_parent),
            "source_root": _filesystem_acl(source_root),
            "private_parent": _filesystem_acl(private_parent),
            "job_root": _filesystem_acl(root),
            "workspace_directory": _filesystem_acl(workspace),
            "workspace_read_file": _filesystem_acl(workspace / "read.txt"),
            "scratch_directory": _filesystem_acl(scratch),
        }

        launcher = WindowsPsecLauncher()
        environment = _environment()
        policy_results = _run_policy_acceptance(
            launcher, workspace, scratch, canary, environment, cleanup_state
        )
        tree_results = _run_job_tree_acceptance(
            launcher, workspace, scratch, environment, cleanup_state
        )

        child_process_token = policy_results.get("child_process_token", {})
        app_container_sid = child_process_token.get("app_container_sid")
        filesystem_acl = {
            "acceptance_parent": _filesystem_acl(acceptance_parent),
            "source_root": _filesystem_acl(source_root),
            "private_parent": _filesystem_acl(private_parent),
            "job_root": _filesystem_acl(root),
            "workspace_directory": _filesystem_acl(workspace),
            "workspace_read_file": _filesystem_acl(workspace / "read.txt"),
            "scratch_directory": _filesystem_acl(scratch),
        }
        if app_container_sid:
            for snapshot in (filesystem_acl_before, filesystem_acl):
                for evidence in snapshot.values():
                    acl_text = (
                        evidence.get("stdout", "") + evidence.get("stderr", "")
                    ).casefold()
                    evidence["app_container_sid_literal_present"] = (
                        app_container_sid.casefold() in acl_text
                    )

        for name, evidence in filesystem_acl.items():
            before_descriptor = filesystem_acl_before.get(name, {}).get(
                "security_descriptor", {}
            )
            after_descriptor = evidence.get("security_descriptor", {})
            before_sddl = before_descriptor.get("sddl")
            after_sddl = after_descriptor.get("sddl")
            evidence["dacl_changed_during_psec_run"] = (
                before_sddl != after_sddl
                if before_sddl is not None and after_sddl is not None
                else None
            )
        filesystem_acl["before_launch"] = filesystem_acl_before

        results = {**policy_results, **tree_results}
        child_process_token = results.pop("child_process_token", {})
        child_token = results.pop("child_token", {})
        diagnostics = {
            "child_token": child_token,
            "child_process_token": child_process_token,
            "filesystem_acl": filesystem_acl,
            "workspace_projection": {
                "manifest_sha256": projection.manifest_sha256,
                "manifest_entries": len(projection.manifest),
                "root": str(projection.root),
            },
            "app_container_profile": (
                _app_container_profile_evidence(app_container_sid, child_token)
                if app_container_sid else {
                    "state": "UNKNOWN",
                    "reason": "Package SID was not captured",
                }
            ),
        }
        failures = _acceptance_failures(results)
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
            "diagnostics": diagnostics,
            "failures": failures,
            "note": "This host acceptance result does not automatically set terminal isolation to VERIFIED.",
        }
        exit_code = 0 if not failures else 1
    except Exception as exc:
        output = {
            "state": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
            "note": "No Terminal templates were enabled; the production VERIFIED gate remains closed.",
        }
        exit_code = 1
    finally:
        if cleanup_state["safe_to_cleanup"]:
            try:
                if projection is not None:
                    cleanup_state["safe_to_cleanup"] = False
                    projection.close()
                    cleanup_state["safe_to_cleanup"] = True
                for directory in (private_parent, source_root):
                    if directory is not None and directory.exists():
                        shutil.rmtree(directory)
                    if directory is not None and directory.exists():
                        raise WindowsPsecError(
                            f"acceptance temporary directory cleanup incomplete: {directory}"
                        )
                cleanup_evidence = {"state": "PASS"}
            except Exception as exc:
                cleanup_state["safe_to_cleanup"] = False
                cleanup_evidence = {
                    "state": "FAIL",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "orphan_roots": [
                        str(path) for path in (projection.root if projection else None,
                                               private_parent, source_root)
                        if path is not None and path.exists()
                    ],
                }
                exit_code = 1
        else:
            cleanup_evidence = {
                "state": "BLOCKED",
                "reason": "Job Object drain was not proven; preserving the disposable tree",
                "orphan_roots": [
                    str(path) for path in (projection.root if projection else None,
                                           private_parent, source_root)
                    if path is not None and path.exists()
                ],
            }
            exit_code = 1

        if canary is not None:
            try:
                canary.unlink(missing_ok=True)
                canary_cleanup = {"state": "PASS"}
            except OSError as exc:
                canary_cleanup = {
                    "state": "FAIL",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "path": str(canary),
                }
                exit_code = 1

        if output is None:
            output = {"state": "FAIL", "error_message": "acceptance produced no result"}
        output["cleanup"] = cleanup_evidence
        output["canary_cleanup"] = canary_cleanup

    print(json.dumps(output, indent=2, sort_keys=True))
    return exit_code

if __name__ == "__main__":
    raise SystemExit(main())
