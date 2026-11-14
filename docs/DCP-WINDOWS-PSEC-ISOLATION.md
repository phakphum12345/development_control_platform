# Windows Process Security Environment (PSEC) Isolation

**Protocol:** DCP-CEEP v1.0  
**Workstream:** WP-18B  
**Status:** Capability probe added; process-launch integration and host acceptance remain BLOCKED

## Decision

Use the Windows Process Security Environment (PSEC) API as the primary Windows process-isolation candidate instead of calling `subprocess.Popen` directly or depending on a user-managed Windows Sandbox feature.

The API surface is exported by `processmodel.dll` and creates a process security environment from a versioned `PSEC` FlatBuffer. The environment is attached to a normal `CreateProcessW` launch through `PROC_THREAD_ATTRIBUTE_SECURITY_ENVIRONMENT`. The Microsoft MXC reference implementation uses a suspended process, assigns it to a Job Object, and resumes it only after assignment.

This is **not LPAC**. PSEC v1.1 exposes AppContainer-related capabilities and filesystem/network policy, but the reference schema does not expose LPAC's all-application-packages opt-out. Do not describe this backend as LPAC or claim LPAC-equivalent least privilege.

## Required enforcement policy

The eventual launcher must fail closed unless all of the following are applied and verified:

- PSEC v1.1 support, including `fs_deny`, `fs_enumerate`, and network ingress policy support.
- No AppContainer network capabilities; explicit egress and ingress default-deny policy, including host loopback deny.
- Project Workspace read-only path policy and explicit enumeration permission.
- Per-job scratch read/write path policy only.
- Explicit deny paths for host-sensitive locations; a host canary test must prove that files outside the allowed workspace/runtime/scratch set cannot be read.
- Win32k system calls disabled for the non-UI Terminal workload.
- A Windows Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and an active-process ceiling. Create the process suspended, assign it to the Job Object, then resume it. No breakaway flags.
- Explicit inherited-handle list only; never inherit arbitrary Runner handles.
- Process-tree completion must wait for the Job Object to become empty, not merely for the root process to exit.

## Capability probe

`tools/local_runner_agent/windows_psec.py` loads `processmodel.dll` only from System32, checks the required exports, queries PSEC support flags, and requires PSEC v1.1. It returns `READY_FOR_ACCEPTANCE`, not VERIFIED. It does not create a process and does not change the production isolation gate.

Run on the target Windows host:

```powershell
py -3 -m tools.local_runner_agent.windows_psec
```

Exit code 2 / `BLOCKED` means the required OS API surface is unavailable. A READY result only authorizes the next acceptance stage; it does not authorize Terminal execution.

## Host/build compatibility

Microsoft's MXC process-container support matrix lists Windows 11 26H2 build 26300.9550 as supporting Process Isolation. Runtime API and feature probing remains authoritative; build-number inference is not acceptance evidence.

## References

- [CreateProcessSecurityEnvironment and processmodel.dll API surface](https://learn.microsoft.com/en-us/windows/win32/api/processmodel/)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
- [Microsoft MXC Process Container documentation and reference implementation](https://github.com/microsoft/mxc/tree/main/docs/backends/process-container)
- [Microsoft MXC Windows OS support matrix](https://github.com/microsoft/mxc/blob/main/docs/backends/process-container/os-version-support.md)

## Current blockers

- PSEC FlatBuffer construction and actual `CreateProcessW` integration are not yet implemented.
- No Windows host process has been launched under PSEC by this repository.
- Workspace read-only, scratch-only write, host-secret denial, network denial, Job Object descendant cleanup, and crash cleanup require adversarial tests.
- Windows host acceptance has not been run on the target machine.
- Built-in Terminal templates remain disabled. No direct-process fallback is permitted.
