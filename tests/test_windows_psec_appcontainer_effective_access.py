from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
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
        process_drained = True
        canary = None
        job_root = None
        evidence_dir = Path(os.environ.get("RUNNER_TEMP", str(acceptance_parent)))
        evidence_path = evidence_dir / "appcontainer-effective-access.json"
        evidence = {"state": "FAIL"}

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
                    f'del /f /q "{scratch / "write-probe.txt"}" > "{scratch / "delete-result.txt"}" 2>&1',
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
            process_drained = False

            token = _require_app_container_token(
                _query_process_token(kernel32, process_info.hProcess)
            )
            self.assertEqual(token["app_container_sid"], package_sid)
            evidence = {
                "package_sid": package_sid,
                "token_state": token["state"],
                "token_user_sid": token["user_sid"],
                "token_integrity_sid": token["integrity_sid"],
                "token_groups": token["groups"],
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
            first_exit_code = int(exit_code.value)
            evidence["first_child_exit_code"] = first_exit_code
            if first_exit_code in (15, 16):
                diagnostic_delete = subprocess.run(
                    [
                        "icacls", str(scratch), "/grant",
                        f"*{token['user_sid']}:(OI)(CI)(D)", "/t", "/c",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                diagnostic_delete_child = subprocess.run(
                    [
                        "icacls", str(scratch), "/grant",
                        f"*{token['user_sid']}:(CI)(DC)", "/t", "/c",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                diagnostic_all_apps_delete = subprocess.run(
                    [
                        "icacls", str(scratch), "/grant",
                        "*S-1-15-2-1:(OI)(CI)(D)", "/t", "/c",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                diagnostic_all_apps_delete_child = subprocess.run(
                    [
                        "icacls", str(scratch), "/grant",
                        "*S-1-15-2-1:(CI)(DC)", "/t", "/c",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                scratch_acl_result = subprocess.run(
                    ["icacls", str(scratch)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                evidence["diagnostic_user_delete_acl"] = {
                    "delete_returncode": diagnostic_delete.returncode,
                    "delete_output": diagnostic_delete.stdout + diagnostic_delete.stderr,
                    "delete_child_returncode": diagnostic_delete_child.returncode,
                    "delete_child_output": (
                        diagnostic_delete_child.stdout + diagnostic_delete_child.stderr
                    ),
                }
                evidence["diagnostic_all_apps_delete_acl"] = {
                    "delete_returncode": diagnostic_all_apps_delete.returncode,
                    "delete_output": (
                        diagnostic_all_apps_delete.stdout + diagnostic_all_apps_delete.stderr
                    ),
                    "delete_child_returncode": diagnostic_all_apps_delete_child.returncode,
                    "delete_child_output": (
                        diagnostic_all_apps_delete_child.stdout
                        + diagnostic_all_apps_delete_child.stderr
                    ),
                }
                evidence["scratch_root_icacls_after_diagnostics"] = (
                    scratch_acl_result.stdout + scratch_acl_result.stderr
                )
                if (
                    diagnostic_delete.returncode
                    or diagnostic_delete_child.returncode
                    or diagnostic_all_apps_delete.returncode
                    or diagnostic_all_apps_delete_child.returncode
                ):
                    raise WindowsPsecError(
                        "Could not apply diagnostic delete ACEs to disposable scratch"
                    )
                if not kernel32.CloseHandle(process_info.hThread):
                    raise WindowsPsecError(
                        f"CloseHandle(first AppContainer thread) failed "
                        f"(WinError {ctypes.get_last_error()})"
                    )
                process_info.hThread = None
                if not kernel32.CloseHandle(process_info.hProcess):
                    raise WindowsPsecError(
                        f"CloseHandle(first AppContainer process) failed "
                        f"(WinError {ctypes.get_last_error()})"
                    )
                process_info.hProcess = None
                process_info = _PROCESS_INFORMATION()
                retry_command_line = ctypes.create_unicode_buffer(
                    f'"{cmd_exe}" /d /c call "{script}"'
                )
                if not kernel32.CreateProcessW(
                    cmd_exe,
                    retry_command_line,
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
                        f"CreateProcessW(AppContainer retry) failed "
                        f"(WinError {ctypes.get_last_error()})"
                    )
                process_drained = False
                retry_token = _require_app_container_token(
                    _query_process_token(kernel32, process_info.hProcess)
                )
                self.assertEqual(retry_token["app_container_sid"], package_sid)
                previous_suspend_count = kernel32.ResumeThread(process_info.hThread)
                if previous_suspend_count == 0xFFFFFFFF or previous_suspend_count != 1:
                    raise WindowsPsecError(
                        "AppContainer retry thread had an unexpected suspend count"
                    )
                retry_wait = kernel32.WaitForSingleObject(
                    process_info.hProcess, 15000
                )
                if retry_wait == WAIT_TIMEOUT:
                    kernel32.TerminateProcess(process_info.hProcess, 1)
                    retry_wait = kernel32.WaitForSingleObject(
                        process_info.hProcess, 5000
                    )
                if retry_wait != WAIT_OBJECT_0:
                    raise WindowsPsecError(
                        f"AppContainer retry did not exit (wait=0x{retry_wait:08x})"
                    )
                process_drained = True
                retry_exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(
                    process_info.hProcess, ctypes.byref(retry_exit_code)
                ):
                    raise WindowsPsecError(
                        f"GetExitCodeProcess(retry) failed "
                        f"(WinError {ctypes.get_last_error()})"
                    )
                evidence["retry_child_exit_code"] = int(retry_exit_code.value)
                exit_code.value = retry_exit_code.value
                if retry_exit_code.value == 0:
                    evidence["diagnostic_result"] = (
                        "user SID DELETE/DELETE_CHILD ACE resolved AppContainer delete denial"
                    )
                    raise AssertionError(
                        "Diagnostic user-SID ACE resolved delete, but production "
                        "handle-relative ACL manager does not yet install that dual-principal grant"
                    )
            else:
                evidence["retry_child_exit_code"] = None

            evidence["child_exit_code"] = int(exit_code.value)
            scratch_probe = scratch / "write-probe.txt"
            evidence["scratch_probe_exists_after_child"] = scratch_probe.exists()
            delete_log = scratch / "delete-result.txt"
            evidence["scratch_delete_output"] = (
                delete_log.read_text(encoding="utf-8", errors="replace")
                if delete_log.exists() else None
            )
            if scratch_probe.exists():
                owner_result = subprocess.run(
                    [
                        "powershell.exe", "-NoProfile", "-Command",
                        f"Import-Module Microsoft.PowerShell.Security; (Get-Acl -LiteralPath '{scratch_probe}').Owner",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                evidence["scratch_probe_owner"] = {
                    "returncode": owner_result.returncode,
                    "stdout": owner_result.stdout.strip(),
                    "stderr": owner_result.stderr.strip(),
                }
                acl_result = subprocess.run(
                    ["icacls", str(scratch_probe)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                evidence["scratch_probe_acl"] = {
                    "returncode": acl_result.returncode,
                    "stdout": acl_result.stdout,
                    "stderr": acl_result.stderr,
                }
            evidence["scratch_root_sddl"] = next(
                (
                    target["sddl"] for target in acl_evidence["targets"]
                    if target["path"].casefold() == str(scratch).casefold()
                ),
                None,
            )
            check_names = [
                "workspace_read",
                "workspace_write_denied",
                "scratch_write",
                "scratch_read",
                "scratch_delete",
                "host_profile_canary_denied",
            ]
            failed_index = {
                11: 0, 12: 1, 13: 2, 14: 3, 15: 4, 16: 4, 17: 5,
            }.get(int(exit_code.value))
            if exit_code.value == 0:
                evidence["checks"] = {name: "PASS" for name in check_names}
            elif failed_index is not None:
                evidence["checks"] = {
                    name: (
                        "FAIL" if index == failed_index
                        else "PASS" if index < failed_index
                        else "NOT_RUN"
                    )
                    for index, name in enumerate(check_names)
                }
            else:
                evidence["checks"] = {name: "NOT_RUN" for name in check_names}
            if exit_code.value != 0:
                evidence["failure_reason"] = (
                    f"AppContainer filesystem access probe exited {exit_code.value}"
                )
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
        except Exception as exc:
            evidence["state"] = "FAIL"
            evidence["error_type"] = type(exc).__name__
            evidence["error_message"] = str(exc)
            raise
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
            cleanup_errors = []
            if profile_created and process_drained:
                hr = userenv.DeleteAppContainerProfile(profile_name)
                if hr != 0:
                    cleanup_errors.append(
                        f"DeleteAppContainerProfile HRESULT 0x{hr & 0xFFFFFFFF:08x}"
                    )
            if canary is not None and process_drained:
                try:
                    canary.unlink(missing_ok=True)
                except OSError as exc:
                    cleanup_errors.append(f"canary cleanup: {type(exc).__name__}: {exc}")
            if job_root is not None and job_root.exists() and process_drained:
                try:
                    shutil.rmtree(job_root)
                except OSError as exc:
                    cleanup_errors.append(f"job-root cleanup: {type(exc).__name__}: {exc}")
            if evidence:
                evidence["process_drained"] = process_drained
                evidence["cleanup_errors"] = cleanup_errors
                evidence_path.write_text(
                    json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
                )
            if not process_drained:
                raise WindowsPsecError(
                    f"AppContainer process was not drained; preserving {job_root} "
                    f"and {canary}"
                )
            if cleanup_errors:
                raise WindowsPsecError("; ".join(cleanup_errors))


if __name__ == "__main__":
    unittest.main()
