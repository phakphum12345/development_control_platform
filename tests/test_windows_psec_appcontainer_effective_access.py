from __future__ import annotations

import ctypes
import json
import os
import shutil
import tempfile
import unittest
import uuid
from ctypes import wintypes
from pathlib import Path

from tools.local_runner_agent.windows_psec_acl_handles import (
    WindowsPsecHandleAclManager,
)
from tools.local_runner_agent.windows_psec_launcher import (
    WindowsPsecError,
    _query_process_token,
    _require_app_container_token,
    _resume_after_filesystem_authorization,
)


CREATE_SUSPENDED = 0x00000004
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_NO_WINDOW = 0x08000000
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", wintypes.LPBYTE),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", _STARTUPINFOW),
        ("lpAttributeList", wintypes.LPVOID),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", wintypes.LPVOID),
        ("Capabilities", wintypes.LPVOID),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
    ]


@unittest.skipUnless(
    os.name == "nt" and os.environ.get("DCP_PSEC_APPCONTAINER_ACL_TEST") == "1",
    "requires opt-in real AppContainer effective-access acceptance",
)
class WindowsPsecAppContainerEffectiveAccessTests(unittest.TestCase):
    def test_real_appcontainer_effective_workspace_and_scratch_access(self):
        from tools.local_runner_agent.windows_psec_launcher import _sid_to_string

        acceptance_parent_value = os.environ.get("DCP_PSEC_ACCEPTANCE_PARENT")
        if not acceptance_parent_value:
            self.fail("DCP_PSEC_ACCEPTANCE_PARENT is required")
        acceptance_parent = Path(acceptance_parent_value).resolve(strict=True)

        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
        userenv = ctypes.WinDLL("userenv.dll", use_last_error=True)

        kernel32.InitializeProcThreadAttributeList.argtypes = [
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
        kernel32.UpdateProcThreadAttribute.argtypes = [
            wintypes.LPVOID, wintypes.DWORD, ctypes.c_size_t, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.LPVOID, ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
        kernel32.DeleteProcThreadAttributeList.argtypes = [wintypes.LPVOID]
        kernel32.DeleteProcThreadAttributeList.restype = None
        kernel32.CreateProcessW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID, wintypes.LPVOID,
            wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID, wintypes.LPCWSTR,
            ctypes.POINTER(_STARTUPINFOEXW), ctypes.POINTER(_PROCESS_INFORMATION),
        ]
        kernel32.CreateProcessW.restype = wintypes.BOOL
        kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel32.ResumeThread.restype = wintypes.DWORD
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [wintypes.LPVOID]
        kernel32.LocalFree.restype = wintypes.LPVOID

        userenv.CreateAppContainerProfile.argtypes = [
            wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID),
        ]
        userenv.CreateAppContainerProfile.restype = ctypes.c_long
        userenv.DeleteAppContainerProfile.argtypes = [wintypes.LPCWSTR]
        userenv.DeleteAppContainerProfile.restype = ctypes.c_long

        advapi32.FreeSid.argtypes = [wintypes.LPVOID]
        advapi32.FreeSid.restype = wintypes.LPVOID

        profile_name = "dcp-psec-acl-" + uuid.uuid4().hex[:24]
        profile_sid = wintypes.LPVOID()
        profile_created = False
        attribute_buffer = None
        attribute_list = None
        process_info = _PROCESS_INFORMATION()
        process_drained = False
        canary = None
        job_root = None
        evidence_path = acceptance_parent / "appcontainer-effective-access.json"
        evidence = {}

        try:
            hr = userenv.CreateAppContainerProfile(
                profile_name,
                "DCP PSEC ACL Acceptance",
                "Disposable AppContainer filesystem authorization test",
                None,
                0,
                ctypes.byref(profile_sid),
            )
            if hr != 0 or not profile_sid:
                raise WindowsPsecError(
                    f"CreateAppContainerProfile failed (HRESULT 0x{hr & 0xFFFFFFFF:08x})"
                )
            profile_created = True
            package_sid = _sid_to_string(advapi32, kernel32, profile_sid)
            if not package_sid.startswith("S-1-15-2-"):
                raise WindowsPsecError("CreateAppContainerProfile returned a non-Package SID")

            job_root = Path(tempfile.mkdtemp(
                prefix="dcp-psec-job-", dir=str(acceptance_parent)
            ))
            workspace = job_root / "workspace"
            scratch = job_root / "scratch"
            workspace.mkdir()
            scratch.mkdir()
            (workspace / "read.txt").write_text(
                "DCP-APPCONTAINER-WORKSPACE-READ", encoding="utf-8"
            )

            user_profile = Path(os.environ["USERPROFILE"]).resolve(strict=True)
            canary = user_profile / f".dcp-appcontainer-canary-{uuid.uuid4().hex}.txt"
            canary.write_text("DCP-APPCONTAINER-HOST-CANARY", encoding="utf-8")

            script = workspace / "acl-probe.cmd"
            script.write_text(
                "\r\n".join([
                    "@echo off",
                    f'type "{workspace / "read.txt"}" > nul',
                    "if errorlevel 1 exit /b 11",
                    f'echo forbidden > "{workspace / "write-probe.txt"}" 2>nul',
                    f'if exist "{workspace / "write-probe.txt"}" exit /b 12',
                    f'echo scratch > "{scratch / "write-probe.txt"}" 2>nul',
                    "if errorlevel 1 exit /b 13",
                    f'type "{scratch / "write-probe.txt"}" > nul',
                    "if errorlevel 1 exit /b 14",
                    f'del "{scratch / "write-probe.txt"}" 2>nul',
                    "if errorlevel 1 exit /b 15",
                    f'if exist "{scratch / "write-probe.txt"}" exit /b 16',
                    f'type "{canary}" > nul 2>nul',
                    "if not errorlevel 1 exit /b 17",
                    "exit /b 0",
                    "",
                ]),
                encoding="utf-8",
            )

            size = ctypes.c_size_t(0)
            kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
            if not size.value:
                raise WindowsPsecError(
                    f"InitializeProcThreadAttributeList size query failed "
                    f"(WinError {ctypes.get_last_error()})"
                )
            attribute_buffer = ctypes.create_string_buffer(size.value)
            attribute_list = ctypes.cast(attribute_buffer, wintypes.LPVOID)
            if not kernel32.InitializeProcThreadAttributeList(
                attribute_list, 1, 0, ctypes.byref(size)
            ):
                raise WindowsPsecError(
                    f"InitializeProcThreadAttributeList failed "
                    f"(WinError {ctypes.get_last_error()})"
                )

            security_capabilities = _SECURITY_CAPABILITIES(
                profile_sid, None, 0, 0
            )
            if not kernel32.UpdateProcThreadAttribute(
                attribute_list,
                0,
                PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                ctypes.byref(security_capabilities),
                ctypes.sizeof(security_capabilities),
                None,
                None,
            ):
                raise WindowsPsecError(
                    f"UpdateProcThreadAttribute(SECURITY_CAPABILITIES) failed "
                    f"(WinError {ctypes.get_last_error()})"
                )

            startup = _STARTUPINFOEXW()
            startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
            startup.lpAttributeList = attribute_list
            process_info = _PROCESS_INFORMATION()
            cmd_exe = str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")
            command_line = ctypes.create_unicode_buffer(
                f'"{cmd_exe}" /d /c call "{script}"'
            )
            if not kernel32.CreateProcessW(
                cmd_exe,
                command_line,
                None,
                None,
                False,
                CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
                None,
                str(workspace),
                ctypes.byref(startup),
                ctypes.byref(process_info),
            ):
                raise WindowsPsecError(
                    f"CreateProcessW(AppContainer) failed "
                    f"(WinError {ctypes.get_last_error()})"
                )

            token = _require_app_container_token(
                _query_process_token(kernel32, process_info.hProcess)
            )
            self.assertEqual(token["app_container_sid"], package_sid)
            evidence = {
                "package_sid": package_sid,
                "token_state": token["state"],
                "se_change_notify_privilege_present": token[
                    "se_change_notify_privilege_present"
                ],
                "se_change_notify_privilege_enabled": token[
                    "se_change_notify_privilege_enabled"
                ],
                "privilege_count": len(token["privileges"]),
            }

            _, acl_evidence = _resume_after_filesystem_authorization(
                kernel32,
                process_info.hThread,
                WindowsPsecHandleAclManager(),
                workspace,
                scratch,
                package_sid,
            )
            evidence["filesystem_acl"] = acl_evidence

            wait_result = kernel32.WaitForSingleObject(process_info.hProcess, 15000)
            if wait_result == WAIT_TIMEOUT:
                kernel32.TerminateProcess(process_info.hProcess, 1)
                wait_result = kernel32.WaitForSingleObject(process_info.hProcess, 5000)
            if wait_result != WAIT_OBJECT_0:
                raise WindowsPsecError(
                    f"AppContainer process did not exit (wait=0x{wait_result:08x})"
                )
            process_drained = True
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(
                process_info.hProcess, ctypes.byref(exit_code)
            ):
                raise WindowsPsecError(
                    f"GetExitCodeProcess failed (WinError {ctypes.get_last_error()})"
                )
            evidence["child_exit_code"] = int(exit_code.value)
            evidence["checks"] = {
                "workspace_read": "PASS" if exit_code.value != 11 else "FAIL",
                "workspace_write_denied": "PASS" if exit_code.value != 12 else "FAIL",
                "scratch_write": "PASS" if exit_code.value != 13 else "FAIL",
                "scratch_read": "PASS" if exit_code.value != 14 else "FAIL",
                "scratch_delete": "PASS" if exit_code.value not in (15, 16) else "FAIL",
                "host_profile_canary_denied": "PASS" if exit_code.value != 17 else "FAIL",
            }
            if exit_code.value != 0:
                raise AssertionError(
                    f"AppContainer filesystem access probe failed with exit code {exit_code.value}"
                )
            self.assertFalse((workspace / "write-probe.txt").exists())
            self.assertFalse((scratch / "write-probe.txt").exists())
            self.assertEqual(
                (workspace / "read.txt").read_text(encoding="utf-8"),
                "DCP-APPCONTAINER-WORKSPACE-READ",
            )
            evidence["state"] = "PASS"
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
            )
        finally:
            if process_info.hProcess:
                if not process_drained:
                    kernel32.TerminateProcess(process_info.hProcess, 1)
                    process_drained = (
                        kernel32.WaitForSingleObject(process_info.hProcess, 5000)
                        == WAIT_OBJECT_0
                    )
                if process_info.hThread:
                    kernel32.CloseHandle(process_info.hThread)
                kernel32.CloseHandle(process_info.hProcess)
            if attribute_list:
                kernel32.DeleteProcThreadAttributeList(attribute_list)
            if profile_sid:
                advapi32.FreeSid(profile_sid)
            if profile_created and process_drained:
                hr = userenv.DeleteAppContainerProfile(profile_name)
                if hr != 0:
                    raise WindowsPsecError(
                        f"DeleteAppContainerProfile failed (HRESULT 0x{hr & 0xFFFFFFFF:08x})"
                    )
            if canary is not None:
                canary.unlink(missing_ok=True)
            if job_root is not None and job_root.exists() and process_drained:
                shutil.rmtree(job_root)
            if job_root is not None and job_root.exists() and not process_drained:
                raise WindowsPsecError(
                    f"AppContainer process was not drained; preserving {job_root}"
                )


if __name__ == "__main__":
    unittest.main()
