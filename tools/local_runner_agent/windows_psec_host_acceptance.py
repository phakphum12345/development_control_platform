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

# Query the token of this exact PSEC-launched process. Host PowerShell identity
# is not a substitute for this evidence.
try:
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    class TOKEN_GROUPS_HEAD(ctypes.Structure):
        _fields_ = [("GroupCount", wintypes.DWORD), ("Groups", SID_AND_ATTRIBUTES * 1)]

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES_HEAD(ctypes.Structure):
        _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    advapi32.LookupPrivilegeNameW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(LUID), wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.LookupPrivilegeNameW.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    def token_buffer(token_handle, information_class):
        required = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token_handle, information_class, None, 0, ctypes.byref(required))
        if not required.value:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token_handle, information_class, buffer, required.value, ctypes.byref(required)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer

    def sid_string(sid):
        allocated = ctypes.c_void_p()
        if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(allocated)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.wstring_at(allocated.value)
        finally:
            kernel32.LocalFree(allocated)

    def token_dword(token_handle, information_class):
        try:
            buffer = token_buffer(token_handle, information_class)
            return ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
        except OSError:
            return None

    child_token = {
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "environment": {
            key: os.environ.get(key)
            for key in ("USERNAME", "USERPROFILE", "LOCALAPPDATA", "TEMP", "TMP", "SYSTEMROOT", "PATH")
        },
    }
    token_handle = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token_handle)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        user_buffer = token_buffer(token_handle, 1)  # TokenUser
        user_entry = ctypes.cast(user_buffer, ctypes.POINTER(SID_AND_ATTRIBUTES)).contents
        child_token["user_sid"] = sid_string(user_entry.Sid)

        integrity_buffer = token_buffer(token_handle, 25)  # TokenIntegrityLevel
        integrity_entry = ctypes.cast(integrity_buffer, ctypes.POINTER(SID_AND_ATTRIBUTES)).contents
        integrity_sid = sid_string(integrity_entry.Sid)
        count_pointer = advapi32.GetSidSubAuthorityCount(integrity_entry.Sid)
        integrity_rid = None
        if count_pointer and count_pointer.contents.value:
            rid_pointer = advapi32.GetSidSubAuthority(
                integrity_entry.Sid, count_pointer.contents.value - 1
            )
            if rid_pointer:
                integrity_rid = int(rid_pointer.contents.value)
        integrity_names = {
            0x0000: "UNTRUSTED", 0x1000: "LOW", 0x2000: "MEDIUM",
            0x2100: "MEDIUM_PLUS", 0x3000: "HIGH",
            0x4000: "SYSTEM", 0x5000: "PROTECTED",
        }
        child_token["integrity"] = {
            "sid": integrity_sid,
            "rid": integrity_rid,
            "level": integrity_names.get(integrity_rid, "UNKNOWN"),
        }

        groups_buffer = token_buffer(token_handle, 2)  # TokenGroups
        groups_head = ctypes.cast(groups_buffer, ctypes.POINTER(TOKEN_GROUPS_HEAD)).contents
        groups = []
        groups_offset = TOKEN_GROUPS_HEAD.Groups.offset
        for index in range(groups_head.GroupCount):
            entry = ctypes.cast(
                ctypes.addressof(groups_buffer) + groups_offset
                + index * ctypes.sizeof(SID_AND_ATTRIBUTES),
                ctypes.POINTER(SID_AND_ATTRIBUTES),
            ).contents
            attributes = int(entry.Attributes)
            groups.append({
                "sid": sid_string(entry.Sid),
                "attributes": attributes,
                "enabled": bool(attributes & 0x00000004),
                "deny_only": bool(attributes & 0x00000010),
                "owner": bool(attributes & 0x00000008),
                "integrity": bool(attributes & 0x00000020),
            })
        child_token["groups"] = groups

        privileges_buffer = token_buffer(token_handle, 3)  # TokenPrivileges
        privileges_head = ctypes.cast(
            privileges_buffer, ctypes.POINTER(TOKEN_PRIVILEGES_HEAD)
        ).contents
        privileges_offset = TOKEN_PRIVILEGES_HEAD.Privileges.offset
        privileges = []
        for index in range(privileges_head.PrivilegeCount):
            entry = ctypes.cast(
                ctypes.addressof(privileges_buffer) + privileges_offset
                + index * ctypes.sizeof(LUID_AND_ATTRIBUTES),
                ctypes.POINTER(LUID_AND_ATTRIBUTES),
            ).contents
            name_size = wintypes.DWORD(0)
            advapi32.LookupPrivilegeNameW(None, ctypes.byref(entry.Luid), None, ctypes.byref(name_size))
            name_buffer = ctypes.create_unicode_buffer(max(1, name_size.value + 1))
            if name_size.value and advapi32.LookupPrivilegeNameW(
                None, ctypes.byref(entry.Luid), name_buffer, ctypes.byref(name_size)
            ):
                name = name_buffer.value
            else:
                name = "LUID:%08x:%08x" % (entry.Luid.HighPart & 0xffffffff, entry.Luid.LowPart)
            attributes = int(entry.Attributes)
            privileges.append({
                "name": name,
                "attributes": attributes,
                "enabled": bool(attributes & 0x00000002),
                "enabled_by_default": bool(attributes & 0x00000001),
                "removed": bool(attributes & 0x00000004),
            })
        child_token["privileges"] = privileges
        child_token["elevation_type"] = token_dword(token_handle, 18)  # TokenElevationType
        child_token["elevated"] = bool(token_dword(token_handle, 20))  # TokenElevation
        child_token["is_app_container"] = bool(token_dword(token_handle, 29))  # TokenIsAppContainer
    finally:
        kernel32.CloseHandle(token_handle)
    result["child_token"] = child_token
except Exception as exc:
    result["child_token"] = {
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "diagnostic_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "winerror": getattr(exc, "winerror", None),
        },
    }

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

            launcher = WindowsPsecLauncher()
            environment = _environment()
            policy_results = _run_policy_acceptance(
                launcher, workspace, scratch, canary, environment
            )
            tree_results = _run_job_tree_acceptance(
                launcher, workspace, scratch, environment
            )

        results = {**policy_results, **tree_results}
        diagnostics = {"child_token": results.pop("child_token", {})}
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
