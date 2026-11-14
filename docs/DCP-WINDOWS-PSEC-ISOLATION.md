# Windows Process Security Environment (PSEC) Isolation

**Protocol:** DCP-CEEP v1.0  
**Workstream:** WP-18B  
**Status:** PSEC v1.1 probe/spec builder and Windows launcher integrated; target-host adversarial acceptance remains BLOCKED

## Decision

Use the Windows Process Security Environment (PSEC) API as the primary Windows process-isolation candidate instead of calling `subprocess.Popen` directly or depending on a user-managed Windows Sandbox feature.

The API surface is exported by `processmodel.dll` and creates a process security environment from a versioned `PSEC` FlatBuffer. The environment is attached to a normal `CreateProcessW` launch through `PROC_THREAD_ATTRIBUTE_SECURITY_ENVIRONMENT`.

The integrated `WindowsPsecLauncher` creates a PSEC environment for the exact Project Workspace, runtime, and per-job scratch paths; creates the workload suspended with an explicit inherited-handle list; assigns it to a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and an active-process ceiling; and resumes it only after Job Object assignment. The process facade tracks Job Object active-process count, not only the root PID.

This is **not LPAC**. PSEC v1.1 does not expose LPAC's all-application-packages opt-out in the reference schema. Do not describe this backend as LPAC or claim LPAC-equivalent least privilege.

## Required enforcement policy

The launcher must fail closed unless all of the following are applied and verified:

- PSEC v1.1 support, including `fs_deny`, `fs_enumerate`, and network-ingress policy support.
- No AppContainer network capabilities; explicit egress and ingress default-deny policy, including host-loopback deny.
- Project Workspace read-only path policy and explicit enumeration permission.
- Per-job scratch read/write path policy only; child `LOCALAPPDATA`, `USERPROFILE`, `HOME`, `TEMP`, and `TMP` are scoped to this scratch root so Windows profile-backed process initialization does not need the host user's profile tree.
- Explicit deny paths for host-sensitive locations; a host canary test must prove that files outside the allowed workspace/runtime/scratch set cannot be read.
- Win32k system calls disabled for the non-UI Terminal workload.
- A Windows Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and an active-process ceiling. Create the process suspended, assign it to the Job Object, then resume it. No breakaway flags.
- Explicit inherited-handle list only; never inherit arbitrary Runner handles.
- Process-tree completion must wait for the Job Object to become empty, not merely for the root process to exit.
- No direct host-process fallback if PSEC policy construction, API calls, Job Object assignment, or process creation fails.

## Capability and policy-creation probe

`tools/local_runner_agent/windows_psec.py` loads `processmodel.dll` only from System32, checks the required exports, queries PSEC support flags, and requires PSEC v1.1. The command-line probe also builds a minimal v1.1 policy using temporary workspace/scratch directories, calls `CreateProcessSecurityEnvironment` with the documented four-argument ABI (including `PROCESS_SECURITY_ENVIRONMENT_FLAG_NONE`), and closes the returned handle.

This validates API availability and policy acceptance only. It does **not** launch a workload process and does not prove filesystem, network, or process-tree enforcement.

Run on the target Windows host from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-DCP-Windows-PSEC.ps1
```

The optional installer installs the pinned FlatBuffers serializer dependency and runs the probe. Exit code 2 / `BLOCKED` means the required API surface or policy creation is unavailable. A READY result only authorizes the next acceptance stage; it does not authorize Terminal execution.

## Target-host adversarial acceptance

After the policy-creation probe reports READY, run the separate host acceptance harness on the target Windows machine:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Run-DCP-Windows-PSEC-Host-Acceptance.ps1
```

Before running acceptance, create a dedicated writable directory on a local volume that is outside all denied roots, then set `DCP_PSEC_ACCEPTANCE_PARENT` to that directory. For example, when `D:\` is a writable data volume:

```powershell
New-Item -ItemType Directory -Force -Path 'D:\DCP-PSEC-Acceptance' | Out-Null
$env:DCP_PSEC_ACCEPTANCE_PARENT = 'D:\DCP-PSEC-Acceptance'
```

The harness rejects a missing or overlapping parent before launching the payload; it does not weaken or remove any deny rule. Keep the host `%TEMP%` unchanged so it remains explicitly denied.

The harness launches only fixed test payloads through `WindowsPsecLauncher`. It checks Project Workspace read access and write denial, per-job scratch write access, denial of a temporary canary file in the host user profile, loopback network denial (after verifying host loopback works outside the sandbox), and Job Object tracking/termination of a spawned descendant. It removes the canary and temporary directories in cleanup. The PowerShell wrapper records the JSON under artifacts/ with the exact repository HEAD and runner exit code; it does not commit or upload the evidence.

A PASS from this harness is evidence for that exact host/build and this exact branch revision only. It does not automatically change `terminal_isolation` to VERIFIED or enable any Terminal template; review the JSON output and the exact commit SHA first.

## Integrated launcher and execution gate

- `tools/local_runner_agent/windows_psec_spec.py` builds the versioned PSEC v1.1 FlatBuffer with explicit filesystem and network policy.
- `tools/local_runner_agent/windows_psec_launcher.py` creates the PSEC environment, starts the fixed executable through `CreateProcessW`, restricts inherited handles, and uses a kill-on-close Job Object.
- `tools/local_runner_agent/terminal_executor.py` routes Windows execution through this launcher; Git filter inspection also runs inside PSEC.
- `tools/local_runner_agent/terminal_isolation.py` may report `READY_FOR_ACCEPTANCE` when the required API features are present. `require_verified_isolation` still rejects that state. Only `VERIFIED` can permit execution.
- No built-in Terminal template has been enabled. No direct `subprocess.Popen` fallback is allowed on Windows.

## Host/build compatibility

Microsoft's MXC process-container support matrix lists Windows 11 26H2 build 26300.9550 as supporting Process Isolation. Runtime API and feature probing remains authoritative; build-number inference is not acceptance evidence.

## Current blockers

- Target Windows host acceptance ran on Windows 11 build 10.0.26300 at repository HEAD `48213cf42537b84bdd1885501793c893a8ec6b1c` and returned FAIL.
- On that run, `workspace_read` and `scratch_write` both returned `PermissionError [Errno 13]`; host-profile denial, loopback denial, and Job Object descendant checks passed. Workspace read-only remains FAIL because the read prerequisite failed.
- The acceptance fixture placed Workspace and Scratch under the host temporary directory, while the launcher explicitly denies that directory and the host profile. The harness now requires a separate, non-overlapping acceptance parent to isolate this path-overlap variable without weakening deny rules.
- The updated acceptance harness must be rerun on the target Windows build and exact current branch HEAD. Timeout/cancellation and Runner-crash cleanup still require separate adversarial tests.
- Built-in Terminal templates remain disabled. No direct-process fallback is permitted.

## References

- [CreateProcessSecurityEnvironment and processmodel.dll API surface](https://learn.microsoft.com/en-us/windows/win32/api/processmodel/)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
- [Microsoft MXC Process Container documentation and reference implementation](https://github.com/microsoft/mxc/tree/main/docs/backends/process-container)
- [Microsoft MXC Windows OS support matrix](https://github.com/microsoft/mxc/blob/main/docs/backends/process-container/os-version-support.md)


## External reference review — Enhanced-PsExec-GUI

**Reference repository:** [phakphum12345/Enhanced-PsExec-GUI](https://github.com/phakphum12345/Enhanced-PsExec-GUI), branch `master`  
**Review scope:** `README.md`, `EnhancedPsExecGUI/epsexecForm.cs`, `EnhancedPsExecGUI/RemoteConsole.cs`, `EnhancedPsExecGUI/EnhancedPsExec.csproj`, `EnhancedPsExecGUI/Program.cs`, and `EnhancedPsExecGUI/app.manifest`.

### Architecture and disposition

The reference is a legacy Windows Forms remote-administration GUI. It starts PsExec/PAExec clients to operate on remote Windows machines over SMB and exposes a remote command console. It is **not** an OS sandbox, a local execution broker, an AppContainer implementation, or a PSEC reference implementation. No source code or binary from this repository is imported into DCP.

### Security findings — do not reproduce

- The README instructs operators to enable SMBv2 and writable `ADMIN$`, create/use an administrator account, set `LocalAccountTokenFilterPolicy=1`, and recommends disabling Windows Firewall. These changes expand remote administrative access and conflict with DCP's local-first, least-privilege boundary. Do not apply them to a DCP host.
- `epsexecForm.cs` writes credentials as plaintext `password=...` values in `.epsx` files and interpolates passwords into external-process command-line arguments (including PsExec/PAExec and helper executables). Do not copy this credential storage or command-line secret handling.
- `RemoteConsole.cs` launches `paexec.exe ... -s ... cmd.exe` and forwards arbitrary text from the console input directly to the remote process standard input. This is an unrestricted administrator/SYSTEM shell, not an allowlisted task interface. It must not be exposed to the browser or Project Workspace UI.
- Process arguments are assembled by string interpolation from IP, username, password, URL, paths, and command fragments. The code also uses `cmd.exe /c` in multiple actions. This is not an acceptable structured-argument boundary for untrusted input.
- The inspected UI includes remote process termination, mouse/keyboard control, screenshot capture, file transfer, sound control, and helper-tool download features. This broad remote-control surface is outside the approved DCP Terminal scope.
- `app.manifest` requests `requireAdministrator`; this elevates the controller rather than isolating a workload. The project targets .NET Framework 4.7.2 and does not provide a PSEC/Job Object containment design.
- Several launch paths start a child process and immediately close the `Process` wrapper without establishing a durable process-tree lifecycle or Job Object ownership. This is not a model for cancellation, descendant cleanup, or evidence collection.

### Limited reusable observations

- The separate stdout/stderr event handlers and explicit stdin/stdout/stderr wiring in `RemoteConsole.cs` illustrate a basic interactive process-I/O shape. They are UI mechanics only; the unrestricted stdin-to-shell design is explicitly rejected.
- DCP already has its own bounded output handling, redaction, fixed-template contract, explicit process creation, inherited-handle allowlist, and Job Object lifecycle. Those controls remain authoritative; this reference contributes no implementation code to them.
- If a future approved interactive workflow is designed, it must still use a named, policy-approved operation, typed/validated arguments, a trusted executable path, an explicit environment/handle allowlist, bounded/redacted output, cancellation, and Job Object descendant containment. It must not provide arbitrary shell input.

### Decision

**REFERENCE ONLY — NO CODE ADOPTION.** Do not install or run this GUI, PsExec, PAExec, or its helper binaries as part of PSEC acceptance. Do not enable SMB, ADMIN$, remote administrator accounts, firewall exceptions, or UAC token-filter registry changes. Continue the DCP design using the PSEC launcher and fail-closed Terminal execution gate documented above.

For Microsoft's documented PsExec `-l` option, note that it strips the Administrators group and runs at Low Integrity on Windows Vista and later; this is still not equivalent to PSEC/AppContainer isolation. See [Microsoft PsExec documentation](https://learn.microsoft.com/en-us/sysinternals/downloads/psexec).

## Latest Windows host acceptance evidence — 2026-11-14

The latest user-provided Windows 11 build 26300 / Python 3.14.6 run remains **FAIL**:

- PASS: PSEC API surface (0xF), PSEC v1.1 policy creation, host-profile canary denial, host-loopback denial, Job Object descendant tracking and termination.
- FAIL: Workspace read, Scratch write, and consequently the derived Workspace read-only check.
- workspace_write_probe=DENIED is **not a valid read-only proof in this run**, because the same token cannot read the workspace prerequisite. It may be denied by the ordinary DACL before the PSEC read-only rule is tested.
- The token was captured from the exact suspended child before ResumeThread; is_app_container=true, with a concrete Package SID and one opaque capability SID. Do not infer the capability name from its hash alone.
- The AppContainer Package SID is absent from the acceptance parent, temporary root, workspace directory, workspace file, and scratch directory ACL evidence. dacl_changed_during_psec_run=false for all captured objects. The temporary root has a protected DACL and the child directories inherit only SYSTEM, Administrators, and OWNER RIGHTS ACEs.
- Therefore the evidence strongly supports an ordinary Windows AppContainer DACL authorization failure as the immediate cause of the read/write PermissionError: AppContainer access is evaluated using both the ordinary user/group grants and the AppContainer Package/Capability SID grants. The PSEC path policy does not make a missing DACL grant appear in these captured security descriptors. This is a root-cause diagnosis, not yet a verified fix.
- whoami.exe returned 0xC0000142 (STATUS_DLL_INIT_FAILED). Token capture from PROCESS_INFORMATION.hProcess succeeded independently; the whoami failure is a separate diagnostic issue and must not be used to dismiss the captured token.
- The opaque capability SID is recorded as evidence only. Network loopback denial passed in this run; do not add network capabilities or change the network policy to address filesystem failures.

### Required next engineering step

Do not weaken host ACLs or grant access to broad principals. Design and test a per-job, Package-SID-scoped filesystem authorization strategy:

1. Provide only the minimum traversal/read grants needed for the read-only workspace and minimum modify grants for the per-job scratch path, scoped to the exact PSEC Package SID.
2. Preserve and restore original security descriptors exactly, with failure-safe cleanup after the Job Object is empty; if safe restoration cannot be guaranteed (including abnormal Runner termination), reject the launch.
3. Ensure protected child DACLs, reparse points, inherited ACEs, concurrent jobs, and cleanup races are handled explicitly. Do not assume one inheritable ACE on a root covers protected descendants.
4. Re-run negative tests proving Workspace write, host profile, denied paths, and host loopback remain denied. A simple DENIED result without a successful Workspace read is insufficient.
5. Keep the production VERIFIED gate and all built-in Terminal templates disabled until the full acceptance matrix passes on the exact source SHA.

Microsoft documents the dual-principal AppContainer access check: both the ordinary user/group and Package/Capability SID permissions must permit access, and the effective permission is their intersection ([Launch an AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)). The MXC policy guide likewise requires validating representative allowed and denied file operations and rejecting startup when required access checks fail ([Author and validate an MXC policy](https://learn.microsoft.com/en-us/windows/apps/develop/mxc/policy)).

**Evidence provenance:** user-provided Windows host acceptance JSON from 2026-11-14, subsequently bound by the user-provided `git rev-parse HEAD` to source commit `cabd3f3ab1a768bb0e10faed4a120e9b9f653285`. GitHub commit comparison confirms PR head `75c683527c121e7a624f10e5e2ea1d075748b020` is exactly one commit ahead of that tested revision and changes only this documentation file (`docs/DCP-WINDOWS-PSEC-ISOLATION.md`, +27 lines, no code changes). Therefore the acceptance result applies to the same implementation code present at the current PR head. The result remains FAIL; it is not a VERIFIED isolation result.
