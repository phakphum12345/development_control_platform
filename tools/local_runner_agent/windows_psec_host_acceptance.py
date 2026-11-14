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
import traceback
import uuid
from pathlib import Path

from tools.local_runner_agent.windows_psec import probe_psec, probe_psec_spec
from tools.local_runner_agent.windows_psec_launcher import (
    WindowsPsecError,
    WindowsPsecLauncher,
)


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
import json, os, pathlib, socket, subprocess, sys
workspace = pathlib.Path(sys.argv[1])
scratch = pathlib.Path(sys.argv[2])
canary = pathlib.Path(sys.argv[3])
port = int(sys.argv[4])
result = {}

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


def _run_policy_acceptance(launcher, workspace: Path, scratch: Path, canary: Path, environment):
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
        result["child_process_token"] = process.token_diagnostics
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

        with tempfile.TemporaryDirectory(
            prefix="dcp-psec-host-acceptance-", dir=str(_acceptance_parent())
        ) as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            scratch = root / "scratch"
            workspace.mkdir()
            scratch.mkdir()
            (workspace / "read.txt").write_text("DCP-WORKSPACE-READ", encoding="utf-8")

            # Capture fixture ACLs before PSEC creation so the acceptance
            # report can distinguish pre-existing host ACL restrictions from
            # changes made while creating/running the PSEC environment.
            filesystem_acl_before = {
                "acceptance_parent": _filesystem_acl(_acceptance_parent()),
                "temporary_root": _filesystem_acl(root),
                "workspace_directory": _filesystem_acl(workspace),
                "workspace_read_file": _filesystem_acl(workspace / "read.txt"),
                "scratch_directory": _filesystem_acl(scratch),
            }

            launcher = WindowsPsecLauncher()
            environment = _environment()
            policy_results = _run_policy_acceptance(
                launcher, workspace, scratch, canary, environment
            )
            tree_results = _run_job_tree_acceptance(
                launcher, workspace, scratch, environment
            )
            # Capture ACLs while the temporary acceptance tree still exists.
            child_process_token = policy_results.get("child_process_token", {})
            app_container_sid = child_process_token.get("app_container_sid")
            filesystem_acl = {
                "acceptance_parent": _filesystem_acl(_acceptance_parent()),
                "temporary_root": _filesystem_acl(root),
                "workspace_directory": _filesystem_acl(workspace),
                "workspace_read_file": _filesystem_acl(workspace / "read.txt"),
                "scratch_directory": _filesystem_acl(scratch),
            }
            if app_container_sid:
                for snapshot in (filesystem_acl_before, filesystem_acl):
                    for evidence in snapshot.values():
                        acl_text = (evidence.get("stdout", "") + evidence.get("stderr", "")).casefold()
                        evidence["app_container_sid_literal_present"] = (
                            app_container_sid.casefold() in acl_text
                        )

            for name, evidence in filesystem_acl.items():
                before_descriptor = filesystem_acl_before.get(name, {}).get("security_descriptor", {})
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
        diagnostics = {
            "child_token": results.pop("child_token", {}),
            "child_process_token": child_process_token,
            "filesystem_acl": filesystem_acl,
            "app_container_profile": (
                _app_container_profile_evidence(app_container_sid, results.get("child_token", {}))
                if app_container_sid else {
                    "state": "UNKNOWN",
                    "reason": "Package SID was not captured",
                }
            ),
        }
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
            "diagnostics": diagnostics,
            "failures": failures,
            "note": "This host acceptance result does not automatically set terminal isolation to VERIFIED.",
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if not failures else 1
    except Exception as exc:
        print(json.dumps({
            "state": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
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
