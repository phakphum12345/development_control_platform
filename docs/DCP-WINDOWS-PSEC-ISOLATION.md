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

Before running acceptance, set `DCP_PSEC_ACCEPTANCE_PARENT` to an existing writable directory on a local drive that does not overlap any denied root (for example, a dedicated directory on a separate data volume). The harness rejects a missing or overlapping parent before launching the payload; it does not weaken or remove any deny rule. Keep the host `%TEMP%` unchanged so it remains explicitly denied.

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

- No target Windows host process has yet been launched and accepted under PSEC by this repository.
- Workspace read-only, scratch-only write, host-secret denial, network denial, Job Object descendant cleanup, timeout/cancellation, and Runner-crash cleanup require adversarial host tests.
- PSEC's effective access-control semantics for denied parent paths with explicitly allowed workspace/scratch descendants must be verified on the target Windows build.
- Windows host acceptance has not been run on the target machine.
- Built-in Terminal templates remain disabled. No direct-process fallback is permitted.

## References

- [CreateProcessSecurityEnvironment and processmodel.dll API surface](https://learn.microsoft.com/en-us/windows/win32/api/processmodel/)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
- [Microsoft MXC Process Container documentation and reference implementation](https://github.com/microsoft/mxc/tree/main/docs/backends/process-container)
- [Microsoft MXC Windows OS support matrix](https://github.com/microsoft/mxc/blob/main/docs/backends/process-container/os-version-support.md)
