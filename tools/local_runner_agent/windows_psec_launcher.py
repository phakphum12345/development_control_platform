"""Windows PSEC process launcher with Job Object process-tree containment.

This launcher is a candidate backend only. Production Terminal execution remains
blocked by terminal_isolation.require_verified_isolation until host acceptance.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Mapping, Sequence

from tools.local_runner_agent.windows_psec import (
    LOAD_LIBRARY_SEARCH_SYSTEM32,
    PSEC_CREATE_FLAG_NONE,
    probe_psec,
)


HANDLE = ctypes.c_void_p
DWORD = ctypes.c_uint32
BOOL = ctypes.c_int
WORD = ctypes.c_uint16
SIZE_T = ctypes.c_size_t
ULONG_PTR = ctypes.c_size_t

CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NO_WINDOW = 0x08000000
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
STARTF_USESTDHANDLES = 0x00000100

HANDLE_FLAG_INHERIT = 0x00000001
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
PROC_THREAD_ATTRIBUTE_SECURITY_ENVIRONMENT = 0x00020023

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
WAIT_TIMEOUT = 0x00000102
WAIT_OBJECT_0 = 0x00000000
INFINITE = 0xFFFFFFFF
STILL_ACTIVE = 259


class WindowsPsecError(RuntimeError):
    """Windows PSEC launch or containment failed closed."""


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", DWORD),
        ("lpSecurityDescriptor", HANDLE),
        ("bInheritHandle", BOOL),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", DWORD),
        ("lpReserved", ctypes.c_wchar_p),
        ("lpDesktop", ctypes.c_wchar_p),
        ("lpTitle", ctypes.c_wchar_p),
        ("dwX", DWORD),
        ("dwY", DWORD),
        ("dwXSize", DWORD),
        ("dwYSize", DWORD),
        ("dwXCountChars", DWORD),
        ("dwYCountChars", DWORD),
        ("dwFillAttribute", DWORD),
        ("dwFlags", DWORD),
        ("wShowWindow", WORD),
        ("cbReserved2", WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
        ("hStdInput", HANDLE),
        ("hStdOutput", HANDLE),
        ("hStdError", HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", STARTUPINFOW),
        ("lpAttributeList", HANDLE),
    ]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", HANDLE),
        ("hThread", HANDLE),
        ("dwProcessId", DWORD),
        ("dwThreadId", DWORD),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", DWORD),
        ("MinimumWorkingSetSize", SIZE_T),
        ("MaximumWorkingSetSize", SIZE_T),
        ("ActiveProcessLimit", DWORD),
        ("Affinity", ULONG_PTR),
        ("PriorityClass", DWORD),
        ("SchedulingClass", DWORD),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", SIZE_T),
        ("JobMemoryLimit", SIZE_T),
        ("PeakProcessMemoryUsed", SIZE_T),
        ("PeakJobMemoryUsed", SIZE_T),
    ]


class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", DWORD),
        ("TotalProcesses", DWORD),
        ("ActiveProcesses", DWORD),
        ("TotalTerminatedProcesses", DWORD),
    ]


def _win_error(operation: str) -> WindowsPsecError:
    return WindowsPsecError(f"{operation} failed (WinError {ctypes.get_last_error()})")


def _load_system_dll(name: str):
    return ctypes.WinDLL(name, use_last_error=True, winmode=LOAD_LIBRARY_SEARCH_SYSTEM32)


def _configure_kernel32(kernel32):
    kernel32.CreateJobObjectW.argtypes = [HANDLE, ctypes.c_wchar_p]
    kernel32.CreateJobObjectW.restype = HANDLE
    kernel32.SetInformationJobObject.argtypes = [HANDLE, ctypes.c_int, HANDLE, DWORD]
    kernel32.SetInformationJobObject.restype = BOOL
    kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(HANDLE), ctypes.POINTER(HANDLE),
        ctypes.POINTER(SECURITY_ATTRIBUTES), DWORD,
    ]
    kernel32.CreatePipe.restype = BOOL
    kernel32.SetHandleInformation.argtypes = [HANDLE, DWORD, DWORD]
    kernel32.SetHandleInformation.restype = BOOL
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, DWORD, DWORD, ctypes.POINTER(SECURITY_ATTRIBUTES),
        DWORD, DWORD, HANDLE,
    ]
    kernel32.CreateFileW.restype = HANDLE
    kernel32.InitializeProcThreadAttributeList.argtypes = [HANDLE, DWORD, DWORD, ctypes.POINTER(SIZE_T)]
    kernel32.InitializeProcThreadAttributeList.restype = BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [
        HANDLE, DWORD, ULONG_PTR, HANDLE, SIZE_T, HANDLE, ctypes.POINTER(SIZE_T),
    ]
    kernel32.UpdateProcThreadAttribute.restype = BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [HANDLE]
    kernel32.DeleteProcThreadAttributeList.restype = None
    kernel32.CreateProcessW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_wchar_p, HANDLE, HANDLE, BOOL, DWORD,
        HANDLE, ctypes.c_wchar_p, HANDLE, ctypes.POINTER(PROCESS_INFORMATION),
    ]
    kernel32.CreateProcessW.restype = BOOL
    kernel32.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
    kernel32.AssignProcessToJobObject.restype = BOOL
    kernel32.ResumeThread.argtypes = [HANDLE]
    kernel32.ResumeThread.restype = DWORD
    kernel32.QueryInformationJobObject.argtypes = [
        HANDLE, ctypes.c_int, HANDLE, DWORD, ctypes.POINTER(DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = BOOL
    kernel32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
    kernel32.GetExitCodeProcess.restype = BOOL
    kernel32.TerminateJobObject.argtypes = [HANDLE, DWORD]
    kernel32.TerminateJobObject.restype = BOOL
    kernel32.TerminateProcess.argtypes = [HANDLE, DWORD]
    kernel32.TerminateProcess.restype = BOOL
    kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    kernel32.WaitForSingleObject.restype = DWORD
    kernel32.CloseHandle.argtypes = [HANDLE]
    kernel32.CloseHandle.restype = BOOL




class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", HANDLE), ("Attributes", DWORD)]


def _token_information(advapi32, token: HANDLE, information_class: int):
    required = DWORD(0)
    advapi32.GetTokenInformation(token, information_class, None, 0, ctypes.byref(required))
    if not required.value:
        raise _win_error(f"GetTokenInformation({information_class}) size")
    buffer = ctypes.create_string_buffer(required.value)
    if not advapi32.GetTokenInformation(
        token, information_class, ctypes.cast(buffer, HANDLE),
        required, ctypes.byref(required),
    ):
        raise _win_error(f"GetTokenInformation({information_class})")
    return buffer


def _sid_to_string(advapi32, kernel32, sid: HANDLE) -> str:
    if not sid:
        return ""
    rendered = ctypes.c_wchar_p()
    if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(rendered)):
        raise _win_error("ConvertSidToStringSidW")
    try:
        return rendered.value or ""
    finally:
        kernel32.LocalFree(ctypes.cast(rendered, HANDLE))


def _query_process_token(kernel32, process_handle: HANDLE) -> dict:
    """Read the suspended target process token; never changes token or policy."""
    TOKEN_QUERY = 0x0008
    TOKEN_USER = 1
    TOKEN_GROUPS = 2
    TOKEN_INTEGRITY_LEVEL = 25
    TOKEN_ELEVATION_TYPE = 18
    TOKEN_IS_APP_CONTAINER = 29
    TOKEN_CAPABILITIES = 30
    TOKEN_APP_CONTAINER_SID = 31
    advapi32 = _load_system_dll("advapi32.dll")
    advapi32.OpenProcessToken.argtypes = [HANDLE, DWORD, ctypes.POINTER(HANDLE)]
    advapi32.OpenProcessToken.restype = BOOL
    advapi32.GetTokenInformation.argtypes = [
        HANDLE, ctypes.c_int, HANDLE, DWORD, ctypes.POINTER(DWORD),
    ]
    advapi32.GetTokenInformation.restype = BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = BOOL
    kernel32.LocalFree.argtypes = [HANDLE]
    kernel32.LocalFree.restype = HANDLE

    token = HANDLE()
    if not advapi32.OpenProcessToken(process_handle, TOKEN_QUERY, ctypes.byref(token)):
        return {
            "state": "UNKNOWN",
            "error": f"OpenProcessToken failed (WinError {ctypes.get_last_error()})",
        }

    result = {
        "state": "PARTIAL",
        "source": "PROCESS_INFORMATION.hProcess before ResumeThread",
        "captured_before_resume": True,
    }
    try:
        try:
            user = _token_information(advapi32, token, TOKEN_USER)
            user_entry = ctypes.cast(user, ctypes.POINTER(SID_AND_ATTRIBUTES)).contents
            result["user_sid"] = _sid_to_string(advapi32, kernel32, user_entry.Sid)
        except Exception as exc:
            result["user_sid_error"] = f"{type(exc).__name__}: {exc}"

        try:
            integrity = _token_information(advapi32, token, TOKEN_INTEGRITY_LEVEL)
            integrity_entry = ctypes.cast(
                integrity, ctypes.POINTER(SID_AND_ATTRIBUTES)
            ).contents
            result["integrity_sid"] = _sid_to_string(
                advapi32, kernel32, integrity_entry.Sid
            )
        except Exception as exc:
            result["integrity_sid_error"] = f"{type(exc).__name__}: {exc}"

        try:
            elevation = _token_information(advapi32, token, TOKEN_ELEVATION_TYPE)
            result["elevation_type"] = int(ctypes.cast(
                elevation, ctypes.POINTER(DWORD)
            ).contents.value)
        except Exception as exc:
            result["elevation_type_error"] = f"{type(exc).__name__}: {exc}"

        try:
            app_container = _token_information(advapi32, token, TOKEN_IS_APP_CONTAINER)
            result["is_app_container"] = bool(ctypes.cast(
                app_container, ctypes.POINTER(DWORD)
            ).contents.value)
        except Exception as exc:
            result["is_app_container_error"] = f"{type(exc).__name__}: {exc}"

        try:
            app_container = _token_information(
                advapi32, token, TOKEN_APP_CONTAINER_SID
            )
            app_container_sid = ctypes.cast(
                app_container, ctypes.POINTER(HANDLE)
            ).contents.value
            result["app_container_sid"] = _sid_to_string(
                advapi32, kernel32, app_container_sid
            )
        except Exception as exc:
            result["app_container_sid_error"] = f"{type(exc).__name__}: {exc}"

        def read_sid_attributes(information_class: int) -> list[dict]:
            token_groups = _token_information(advapi32, token, information_class)
            group_count = ctypes.cast(
                token_groups, ctypes.POINTER(DWORD)
            ).contents.value
            if group_count > 512:
                raise WindowsPsecError(
                    "process token reports an unreasonable SID count"
                )
            offset = (ctypes.sizeof(DWORD) + ctypes.alignment(HANDLE) - 1) & ~(
                ctypes.alignment(HANDLE) - 1
            )
            items = []
            base = ctypes.addressof(token_groups) + offset
            for index in range(group_count):
                entry = ctypes.cast(
                    base + index * ctypes.sizeof(SID_AND_ATTRIBUTES),
                    ctypes.POINTER(SID_AND_ATTRIBUTES),
                ).contents
                items.append({
                    "sid": _sid_to_string(advapi32, kernel32, entry.Sid),
                    "attributes": int(entry.Attributes),
                })
            return items

        try:
            result["capabilities"] = read_sid_attributes(TOKEN_CAPABILITIES)
        except Exception as exc:
            result["capabilities_error"] = f"{type(exc).__name__}: {exc}"

        try:
            result["groups"] = read_sid_attributes(TOKEN_GROUPS)
        except Exception as exc:
            result["groups_error"] = f"{type(exc).__name__}: {exc}"

        required = {"user_sid", "integrity_sid", "elevation_type", "is_app_container", "app_container_sid", "groups", "capabilities"}
        result["state"] = "CAPTURED" if required.issubset(result) else "PARTIAL"
        return result
    finally:
        kernel32.CloseHandle(token)




def _valid_sid_string(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split("-")
    if (len(parts) < 4 or len(parts) > 18 or parts[:2] != ["S", "1"]
            or any(not part.isascii() or not part.isdecimal() for part in parts[2:])):
        return False
    try:
        authority = int(parts[2], 10)
        subauthorities = [int(part, 10) for part in parts[3:]]
    except ValueError:
        return False
    return 0 <= authority <= 0xFFFFFFFFFFFF and all(
        0 <= item <= 0xFFFFFFFF for item in subauthorities
    )


def _require_app_container_token(token: object) -> dict:
    """Require complete, pre-resume AppContainer identity evidence.

    This validates identity only; it does not grant filesystem access or prove
    that Package-SID ACL authorization has been installed.
    """
    if not isinstance(token, dict):
        raise WindowsPsecError("PSEC process token diagnostics are unavailable")
    required = {
        "state", "captured_before_resume", "is_app_container", "app_container_sid",
        "user_sid", "integrity_sid", "elevation_type", "groups", "capabilities",
    }
    if not required.issubset(token):
        raise WindowsPsecError("PSEC process token diagnostics are incomplete")
    if token["state"] != "CAPTURED" or token["captured_before_resume"] is not True:
        raise WindowsPsecError("PSEC process token was not completely captured before resume")
    if token["is_app_container"] is not True:
        raise WindowsPsecError("PSEC process token is not an AppContainer token")
    if not _valid_sid_string(token["app_container_sid"]):
        raise WindowsPsecError("PSEC AppContainer Package SID is invalid")
    if not _valid_sid_string(token["user_sid"]) or not _valid_sid_string(token["integrity_sid"]):
        raise WindowsPsecError("PSEC process token contains an invalid user or integrity SID")
    if (isinstance(token["elevation_type"], bool)
            or not isinstance(token["elevation_type"], int)
            or token["elevation_type"] not in (1, 2, 3)):
        raise WindowsPsecError("PSEC process token elevation type is invalid")
    if not isinstance(token["groups"], list) or not isinstance(token["capabilities"], list):
        raise WindowsPsecError("PSEC process token SID collections are invalid")
    for collection_name in ("groups", "capabilities"):
        for entry in token[collection_name]:
            if (not isinstance(entry, dict) or not _valid_sid_string(entry.get("sid"))
                    or isinstance(entry.get("attributes"), bool)
                    or not isinstance(entry.get("attributes"), int)):
                raise WindowsPsecError(f"PSEC process token {collection_name} are invalid")
    return token


def _environment_block(environment: Mapping[str, str]):
    normalized = {}
    for key, value in environment.items():
        if (not isinstance(key, str) or not key or "=" in key or "\x00" in key
                or not isinstance(value, str) or "\x00" in value):
            raise WindowsPsecError("sandbox environment contains an invalid entry")
        folded = key.casefold()
        if folded in normalized:
            raise WindowsPsecError("sandbox environment contains duplicate variable names")
        normalized[folded] = (key, value)
    entries = [f"{key}={value}" for key, value in sorted(normalized.values(), key=lambda pair: pair[0].casefold())]
    return ctypes.create_unicode_buffer("\x00".join(entries) + "\x00")


def _trusted_directory(value: str | os.PathLike, label: str) -> Path:
    raw = Path(value)
    if not raw.is_absolute():
        raise WindowsPsecError(f"{label} must be absolute")
    current = Path(raw.anchor)
    for part in raw.parts[1:]:
        current = current / part
        try:
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                raise WindowsPsecError(f"{label} path contains a reparse point")
        except OSError:
            raise WindowsPsecError(f"{label} path cannot be inspected") from None
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError):
        raise WindowsPsecError(f"{label} is unavailable") from None
    if resolved != raw or not resolved.is_dir():
        raise WindowsPsecError(f"{label} must be a canonical directory")
    return resolved


def _apply_sandbox_profile_environment(environment: dict[str, str], scratch: Path) -> None:
    """Keep Windows profile-backed process initialization inside job scratch."""
    scratch_path = str(scratch)
    environment["HOME"] = scratch_path
    environment["USERPROFILE"] = scratch_path
    # PSEC process initialization resolves its per-user package/profile state
    # through LOCALAPPDATA. Keep that state in the authorized per-job scratch
    # root rather than exposing the host user's LocalAppData tree.
    environment["LOCALAPPDATA"] = scratch_path
    environment["TEMP"] = scratch_path
    environment["TMP"] = scratch_path

def _runtime_root(executable: str) -> Path:
    binary = Path(executable).resolve(strict=True)
    if not binary.is_file():
        raise WindowsPsecError("sandbox executable is not a regular file")
    parent = binary.parent
    if parent.name.casefold() in {"cmd", "bin", "scripts"}:
        return parent.parent
    return parent


def _existing_directories(values: Sequence[str | os.PathLike]) -> tuple[str, ...]:
    result = []
    seen = set()
    for value in values:
        if not value:
            continue
        try:
            path = Path(value).resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if not path.is_dir():
            continue
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            result.append(str(path))
    return tuple(result)


def _build_environment_spec(workspace: Path, scratch: Path, executable: str) -> bytes:
    try:
        from tools.local_runner_agent.windows_psec_spec import build_psec_spec
    except ImportError:
        raise WindowsPsecError(
            "optional flatbuffers dependency is missing; run Install-DCP-Windows-PSEC.ps1"
        ) from None
    runtime_root = _runtime_root(executable)
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
    if not system_root:
        raise WindowsPsecError("SYSTEMROOT is unavailable")
    system_root_path = Path(system_root).resolve(strict=True)
    system_directories = _existing_directories((
        system_root_path / "System32",
        system_root_path / "WinSxS",
        system_root_path / "SysWOW64",
    ))
    read_only = _existing_directories((workspace, runtime_root, *system_directories))
    denied = _existing_directories((
        os.environ.get("USERPROFILE"),
        os.environ.get("PROGRAMDATA"),
        os.environ.get("PUBLIC"),
        tempfile.gettempdir(),
        system_root_path / "Temp",
    ))
    enumerate_paths = tuple((*read_only, str(scratch)))
    return build_psec_spec(
        read_only_paths=read_only,
        read_write_paths=(str(scratch),),
        denied_paths=denied,
        enumerate_paths=enumerate_paths,
        disallow_win32k_system_calls=True,
        ui_restrictions=0x3FF,
    )


class WindowsPsecProcess:
    """Popen-like process facade whose liveness tracks the entire Job Object."""

    def __init__(self, *, kernel32, process_handle, job_handle, psec_dll,
                 psec_handle, stdout, pid: int, args: Sequence[str],
                 token_diagnostics: dict | None = None):
        self._kernel32 = kernel32
        self._process_handle = process_handle
        self._job_handle = job_handle
        self._psec_dll = psec_dll
        self._psec_handle = psec_handle
        self.stdout = stdout
        self.pid = pid
        self.args = tuple(args)
        self.token_diagnostics = token_diagnostics or {"state": "UNKNOWN"}
        self.returncode = None
        self._closed = False

    def _active_processes(self) -> int:
        info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
        if not self._kernel32.QueryInformationJobObject(
            self._job_handle,
            JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.cast(ctypes.byref(info), HANDLE),
            ctypes.sizeof(info),
            None,
        ):
            raise _win_error("QueryInformationJobObject")
        return int(info.ActiveProcesses)

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        if self._active_processes() > 0:
            return None
        exit_code = DWORD()
        if not self._kernel32.GetExitCodeProcess(self._process_handle, ctypes.byref(exit_code)):
            raise _win_error("GetExitCodeProcess")
        if exit_code.value == STILL_ACTIVE:
            return None
        self.returncode = int(exit_code.value)
        return self.returncode

    def wait(self, timeout: float | None = None):
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            result = self.poll()
            if result is not None:
                return result
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.args, timeout)
            time.sleep(0.05)

    def terminate_tree(self):
        if self.poll() is None:
            if not self._kernel32.TerminateJobObject(self._job_handle, 1):
                raise _win_error("TerminateJobObject")

    def kill(self):
        self.terminate_tree()

    def close(self):
        if self._closed:
            return
        try:
            if self.poll() is None:
                self.terminate_tree()
                try:
                    self.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Closing a KILL_ON_JOB_CLOSE handle remains the final
                    # fail-safe if TerminateJobObject or wait cannot complete.
                    pass
        finally:
            try:
                if self.stdout:
                    self.stdout.close()
            finally:
                if self._process_handle:
                    self._kernel32.CloseHandle(self._process_handle)
                    self._process_handle = None
                if self._job_handle:
                    self._kernel32.CloseHandle(self._job_handle)
                    self._job_handle = None
                if self._psec_handle:
                    self._psec_dll.CloseProcessSecurityEnvironment(self._psec_handle)
                    self._psec_handle = None
                self._closed = True


class WindowsPsecLauncher:
    """Launch one fixed command inside PSEC with a kill-on-close Job Object."""

    def __init__(self):
        if os.name != "nt":
            raise WindowsPsecError("Windows PSEC launcher is supported only on Windows")
        assessment = probe_psec()
        if assessment.state != "READY_FOR_ACCEPTANCE":
            raise WindowsPsecError("required Windows PSEC v1.1 API features are unavailable")
        self.kernel32 = _load_system_dll("kernel32.dll")
        _configure_kernel32(self.kernel32)
        self.psec_dll = _load_system_dll("processmodel.dll")

    def launch(
        self,
        command: Sequence[str],
        *,
        workspace: str | os.PathLike,
        scratch: str | os.PathLike,
        environment: Mapping[str, str],
    ) -> WindowsPsecProcess:
        if not command or any(not isinstance(item, str) or "\x00" in item for item in command):
            raise WindowsPsecError("sandbox command is invalid")
        if not Path(command[0]).is_absolute():
            raise WindowsPsecError("sandbox executable must be an absolute path")
        work = _trusted_directory(workspace, "Project Workspace")
        temp = _trusted_directory(scratch, "Terminal scratch")
        if work == temp or work in temp.parents or temp in work.parents:
            raise WindowsPsecError("workspace and scratch must be separate directory trees")

        env = dict(environment)
        runtime_root = _runtime_root(command[0])
        system_root = os.environ.get("SYSTEMROOT") or os.environ.get("SystemRoot")
        if not system_root:
            raise WindowsPsecError("SYSTEMROOT is unavailable")
        system32 = Path(system_root) / "System32"
        env["SYSTEMROOT"] = system_root
        _apply_sandbox_profile_environment(env, temp)
        env["PATH"] = ";".join(_existing_directories((runtime_root, system32)))

        specification = _build_environment_spec(work, temp, command[0])
        create = self.psec_dll.CreateProcessSecurityEnvironment
        # Microsoft ABI: (BYTE *specification, DWORD sizeBytes,
        # PROCESS_SECURITY_ENVIRONMENT_FLAGS creationFlags, HANDLE *environment).
        create.argtypes = [
            ctypes.c_void_p, DWORD, DWORD, ctypes.POINTER(HANDLE),
        ]
        create.restype = ctypes.c_long
        close_psec = self.psec_dll.CloseProcessSecurityEnvironment
        close_psec.argtypes = [HANDLE]
        close_psec.restype = None
        specification_buffer = ctypes.create_string_buffer(specification, len(specification))
        psec_handle = HANDLE()
        hr = int(create(
            ctypes.cast(specification_buffer, HANDLE),
            len(specification),
            PSEC_CREATE_FLAG_NONE,
            ctypes.byref(psec_handle),
        ))
        if hr < 0 or not psec_handle.value:
            raise WindowsPsecError(
                f"CreateProcessSecurityEnvironment failed (HRESULT 0x{hr & 0xffffffff:08x})"
            )

        kernel32 = self.kernel32
        job_handle = HANDLE()
        stdout_read = HANDLE()
        stdout_write = HANDLE()
        stdin_handle = HANDLE()
        process_info = PROCESS_INFORMATION()
        attribute_buffer = None
        attribute_list = HANDLE()
        attribute_list_initialized = False
        stdout_file = None
        process_created = False
        try:
            job_handle = kernel32.CreateJobObjectW(None, None)
            if not job_handle:
                raise _win_error("CreateJobObjectW")
            limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            limits.BasicLimitInformation.LimitFlags = (
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            )
            limits.BasicLimitInformation.ActiveProcessLimit = 16
            if not kernel32.SetInformationJobObject(
                job_handle,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.cast(ctypes.byref(limits), HANDLE),
                ctypes.sizeof(limits),
            ):
                raise _win_error("SetInformationJobObject")

            security = SECURITY_ATTRIBUTES(
                ctypes.sizeof(SECURITY_ATTRIBUTES), None, 1
            )
            if not kernel32.CreatePipe(
                ctypes.byref(stdout_read), ctypes.byref(stdout_write),
                ctypes.byref(security), 0,
            ):
                raise _win_error("CreatePipe")
            if not kernel32.SetHandleInformation(stdout_read, HANDLE_FLAG_INHERIT, 0):
                raise _win_error("SetHandleInformation(stdout read)")
            stdin_handle = kernel32.CreateFileW(
                "NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                ctypes.byref(security), OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None,
            )
            if not stdin_handle or stdin_handle == INVALID_HANDLE_VALUE:
                raise _win_error("CreateFileW(NUL)")

            attribute_size = SIZE_T(0)
            kernel32.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(attribute_size))
            if not attribute_size.value:
                raise _win_error("InitializeProcThreadAttributeList(size)")
            attribute_buffer = ctypes.create_string_buffer(attribute_size.value)
            attribute_list = ctypes.cast(attribute_buffer, HANDLE)
            if not kernel32.InitializeProcThreadAttributeList(
                attribute_list, 2, 0, ctypes.byref(attribute_size)
            ):
                raise _win_error("InitializeProcThreadAttributeList")
            attribute_list_initialized = True

            if not kernel32.UpdateProcThreadAttribute(
                attribute_list, 0, PROC_THREAD_ATTRIBUTE_SECURITY_ENVIRONMENT,
                ctypes.cast(ctypes.byref(psec_handle), HANDLE), ctypes.sizeof(psec_handle), None, None,
            ):
                raise _win_error("UpdateProcThreadAttribute(PSEC)")
            inherited_handles = (HANDLE * 2)(stdin_handle, stdout_write)
            if not kernel32.UpdateProcThreadAttribute(
                attribute_list, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                ctypes.cast(ctypes.byref(inherited_handles), HANDLE), ctypes.sizeof(inherited_handles), None, None,
            ):
                raise _win_error("UpdateProcThreadAttribute(HANDLE_LIST)")

            startup = STARTUPINFOEXW()
            startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
            startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput = stdin_handle
            startup.StartupInfo.hStdOutput = stdout_write
            startup.StartupInfo.hStdError = stdout_write
            startup.lpAttributeList = attribute_list

            command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(command)))
            environment_block = _environment_block(env)
            if not kernel32.CreateProcessW(
                command[0],
                command_line,
                None,
                None,
                True,
                CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
                | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
                ctypes.cast(environment_block, HANDLE),
                str(work),
                ctypes.cast(ctypes.byref(startup), HANDLE),
                ctypes.byref(process_info),
            ):
                raise _win_error("CreateProcessW(PSEC)")

            process_created = True
            kernel32.CloseHandle(stdin_handle)
            stdin_handle = None
            kernel32.CloseHandle(stdout_write)
            stdout_write = None
            kernel32.DeleteProcThreadAttributeList(attribute_list)
            attribute_list_initialized = False

            # Capture and validate the exact PSEC-created AppContainer token
            # while its initial thread is suspended. Identity evidence is a
            # prerequisite for any later Package-SID authorization step.
            # Missing or malformed evidence must never be downgraded to a
            # diagnostic warning or allowed to reach ResumeThread.
            try:
                token_diagnostics = _require_app_container_token(
                    _query_process_token(kernel32, process_info.hProcess)
                )
            except Exception as exc:
                if isinstance(exc, WindowsPsecError):
                    raise
                raise WindowsPsecError(
                    f"PSEC process token validation failed: {type(exc).__name__}: {exc}"
                ) from exc
            if not kernel32.AssignProcessToJobObject(job_handle, process_info.hProcess):
                raise _win_error("AssignProcessToJobObject")
            previous_suspend_count = kernel32.ResumeThread(process_info.hThread)
            if previous_suspend_count == 0xFFFFFFFF:
                raise _win_error("ResumeThread")
            kernel32.CloseHandle(process_info.hThread)
            process_info.hThread = None

            import msvcrt
            descriptor = msvcrt.open_osfhandle(
                int(stdout_read.value), os.O_RDONLY | os.O_BINARY
            )
            stdout_file = os.fdopen(descriptor, "rb", buffering=0)
            stdout_read = None
            return WindowsPsecProcess(
                kernel32=kernel32,
                process_handle=process_info.hProcess,
                job_handle=job_handle,
                psec_dll=self.psec_dll,
                psec_handle=psec_handle,
                stdout=stdout_file,
                pid=int(process_info.dwProcessId),
                args=command,
                token_diagnostics=token_diagnostics,
            )
        except Exception:
            if process_created and process_info.hProcess:
                if job_handle:
                    kernel32.TerminateJobObject(job_handle, 1)
                # If Job assignment itself failed, the suspended root is not
                # a member of the Job yet; terminate it explicitly as well.
                kernel32.TerminateProcess(process_info.hProcess, 1)
                kernel32.WaitForSingleObject(process_info.hProcess, 5000)
            if stdout_file:
                stdout_file.close()
            for handle in (stdout_read, stdout_write, stdin_handle):
                if handle:
                    kernel32.CloseHandle(handle)
            if process_info.hThread:
                kernel32.CloseHandle(process_info.hThread)
            if process_info.hProcess:
                kernel32.CloseHandle(process_info.hProcess)
            if attribute_list_initialized:
                kernel32.DeleteProcThreadAttributeList(attribute_list)
            if job_handle:
                kernel32.CloseHandle(job_handle)
            close_psec(psec_handle)
            raise
