# DCP Terminal — OS Isolation Design and Acceptance

**Status:** WP-18 in progress; no platform is currently verified  
**Execution policy:** fail closed; all built-in Terminal templates remain disabled

## Why this work exists

Project/workspace binding, a temporary HOME, a sanitized environment, fixed argv,
and Job Objects/process groups are defense-in-depth. They do not independently
prevent a child process from reading other host files, opening network connections,
or accessing resources available to the Runner service account.

WP-18 adds an explicit OS isolation boundary. A platform is not considered isolated
because a helper binary is installed or a process starts successfully.

## Platform design

| Platform | Candidate backend | Required boundary | Current state |
|---|---|---|---|
| Windows 10/11 | Native AppContainer or LPAC launcher + Job Object | Restricted token/package SID, explicit read-only workspace and runtime capabilities, no network capability, child-process containment and verified cleanup | BLOCKED — native launcher and host acceptance not implemented |
| Linux | bubblewrap + user/mount/PID/IPC/UTS/network namespaces + seccomp | Empty namespace root, explicit read-only runtime mounts, assigned workspace only, per-job scratch, private network namespace, reviewed syscall policy, child cleanup | READY_FOR_ACCEPTANCE when bwrap is present; integrated launcher is not host-verified |
| macOS | Signed App Sandbox helper with explicit entitlements | Signed helper, explicit file access, network client/server entitlements disabled, process lifecycle and cleanup evidence | BLOCKED — helper and signing/entitlement acceptance not implemented |

Windows AppContainer/LPAC is the selected Windows security boundary. Job Objects
remain necessary for resource and process-tree lifecycle, but are not a substitute
for AppContainer access control.

Linux bubblewrap is a candidate because it can construct mount and network namespaces,
PID/IPC/UTS isolation and seccomp filtering. Its safety depends on the exact mounts and
arguments; exposing host directories or IPC sockets can undermine the boundary.

macOS must use the supported App Sandbox entitlement model in a signed app/helper.
Do not use the deprecated sandbox-exec interface as a production substitute.

## Implementation in this WP-18 slice

- tools/local_runner_agent/terminal_isolation.py records the platform backend and
  returns only BLOCKED or READY_FOR_ACCEPTANCE from current detection.
- Presence of bwrap is explicitly not reported as network/filesystem/process isolation.
- Windows and macOS remain blocked until their native helper implementations exist.
- require_verified_isolation() rejects every state except a complete VERIFIED
  assessment with all three enforcement claims.
- TerminalScriptExecutor calls require_verified_isolation() before workspace resolution or process launch. The default platform assessment cannot return VERIFIED, so production execution remains blocked.
- WP-18A now connects the Linux executor path to LinuxBubblewrapLauncher: it resolves only tools from the approved /usr/bin runtime, mounts the assigned workspace read-only and per-job scratch separately, passes the seccomp descriptor with pass_fds, and closes the parent descriptor immediately after process creation.
- The Linux executor does not fall back to a host Popen command if bubblewrap is missing, command construction fails, or the seccomp descriptor cannot be inherited. Non-Linux VERIFIED assessments are also rejected until their native launchers are integrated.
- The bubblewrap host process receives only the executor's template-allowlisted environment and fixed safety settings, never the ambient host environment or Runner credentials; the workload environment is reconstructed after --clearenv.
- Git repository filter discovery also runs as a fixed `git config --name-only` command inside bubblewrap before the requested Git command. No Git process is launched on the host against project-controlled repository configuration.
- Both backend detection and launcher construction resolve bubblewrap only from the approved /usr/bin runtime. The launcher rejects a resolved bubblewrap binary outside that runtime tree.
- Executor unit tests use an explicitly test-only passthrough launcher to exercise bounded process/output/cancellation behavior. They do not assert or prove OS isolation.
- terminal_isolation.py remains the gate contract; linux_sandbox.py constructs the candidate launch boundary. Neither module promotes a host to VERIFIED.

## Mandatory acceptance matrix

A platform backend may be promoted to VERIFIED only after all applicable tests pass
on that actual host and exact helper build:

1. **Filesystem boundary**
   - Read/write outside assigned workspace and per-job scratch is denied.
   - Parent directories, sibling projects, user profile, credential stores, runner
     configuration and application secrets are inaccessible.
   - Symlink, junction, hard-link and mount traversal attempts fail closed.
2. **Network boundary**
   - DNS, IPv4, IPv6, loopback-to-host, LAN, metadata endpoints and public egress
     are denied for the no-network template class.
   - No inherited proxy, socket, named pipe or IPC endpoint bypasses policy.
3. **Process boundary**
   - Child/grandchild creation is contained.
   - Cancel, timeout, lease loss, Runner shutdown and forced termination leave no
     surviving descendants.
   - Resource limits are enforced and cleanup is independently verified.
4. **Identity and capability boundary**
   - Workload has no owner, Gateway, GitHub App or Runner credentials.
   - No unnecessary devices, IPC sockets, service managers or privileged capabilities
     are exposed.
5. **Adversarial acceptance**
   - Test direct syscalls, alternate path forms, environment poisoning, helper
     substitution, race conditions, malformed paths and attempted sandbox escape.
   - Capture host, OS build/kernel, backend/helper version, test result and evidence.
6. **Operational recovery**
   - Scratch and mounts are removed after normal exit, crash, cancellation and reboot.
   - The durable job record reports cleanup as verified only after independent checks.

## Promotion rules

- Missing backend, unsupported OS, unavailable namespace feature, policy compilation
  failure, helper signature failure, or incomplete evidence => BLOCKED.
- A helper being present => at most READY_FOR_ACCEPTANCE.
- CI unit tests are contract evidence only; they do not establish actual host isolation.
- Windows self-hosted runner acceptance marked SKIPPED/UNKNOWN is not a PASS.
- Do not enable any built-in Terminal template until the applicable platform acceptance
  gates pass and the security review is recorded.
- Do not claim that network isolation is enforced by metadata, environment variables,
  workspace binding, or Job Objects alone.

## References

- Microsoft, Windows application isolation:
  https://learn.microsoft.com/en-us/windows/security/book/application-security-application-isolation
- Microsoft, launching AppContainer/LPAC:
  https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer
- Bubblewrap upstream documentation:
  https://github.com/containers/bubblewrap
- Apple, App Sandbox:
  https://developer.apple.com/documentation/security/app-sandbox


## WP-18A implementation checkpoint — Linux bubblewrap command builder

- Added `tools/local_runner_agent/linux_sandbox.py` with a Linux-only bubblewrap command builder.
- The builder uses explicit read-only `/usr/bin` and shared-library trees `/usr/lib`, `/usr/lib64`, `/lib` and `/lib64` (never the broad `/usr/local` tree), a read-only assigned workspace at `/workspace`, a separate per-job scratch mount at `/tmp`, a private network namespace, PID/IPC/UTS/user namespaces, a cleared environment, and a seccomp BPF filter that denies socket-related syscalls and io_uring setup.
- The user namespace is mapped to UID/GID 0 inside the namespace, all capabilities are dropped, and further user namespaces are disabled/asserted disabled. The host-side workspace remains read-only and scratch remains job-scoped.
- Added `tests/test_linux_sandbox.py` for argument policy, seccomp program alignment, unsupported architectures, path validation and workspace/scratch separation. These are command-construction tests, not proof that the kernel accepted or enforced the sandbox.
- Added the Linux policy tests to the Ubuntu/Windows Cross-platform Recovery Acceptance matrix. Windows marks this Linux-only test class skipped; that skip is not a Windows pass for Linux isolation.
- The command builder is now integrated into TerminalScriptExecutor, including seccomp FD inheritance and fail-closed launch errors. No user-host acceptance has been run. Linux remains BLOCKED/READY_FOR_ACCEPTANCE only; `require_verified_isolation()` still blocks production execution. All seven built-in templates remain disabled.
- Upstream behavior reference: bubblewrap's own option parser documents `--unshare-user`, `--uid`, `--gid`, `--unshare-net`, `--seccomp`, `--disable-userns` and `--cap-drop`: https://github.com/containers/bubblewrap/blob/main/bubblewrap.c


- Added an opt-in actual bubblewrap runtime test to the Linux-only suite. The Ubuntu CI job installs bubblewrap and attempts to verify workspace read-only behavior, isolation of an unmounted host sentinel, writable per-job scratch, and socket denial through seccomp. This is acceptance on the ephemeral GitHub-hosted Ubuntu runner only; it does not replace acceptance on the user's Linux host.


## WP-18C — process-tree containment and conservative workspace recovery

- Linux Terminal launch continues to use bubblewrap's `--die-with-parent`, a private PID namespace and a separate session. The executor terminates the outer launcher process group; the sandbox parent-death boundary is responsible for terminating descendants that create a new session inside the PID namespace.
- Added a Linux-only adversarial timeout test that forks a child, calls `setsid()` in the child to leave the process group, then verifies that no running descendants remain after the bubblewrap parent is terminated. This is CI-host evidence, not user-host acceptance.
- Added an authenticated Runner-only `GET /v1/runner/{job_id}/workspace-cleanup-status` endpoint. It reveals only minimal status for a Terminal job whose current/last worker matches the calling Runner.
- The Gateway attests `cleanup_safe` only when the job is terminal, has no active worker/lease, and is either succeeded/cancelled or failed specifically because workspace cleanup failed. Lease-expired failures and UNKNOWN outcomes are not cleanup-safe.
- Runner startup now performs expired-preview cleanup and asks the Gateway to attest candidate Terminal workspaces. The reconciler requires a valid ownership marker, matching job/worker, terminal target, an elapsed 120-second grace period, and explicit `cleanup_safe=true`.
- Active, queued, retrying, UNKNOWN, LEASE_EXPIRED, recent, mismatched, unowned, malformed, unavailable, and preview-retained workspaces are preserved. A missing Gateway response never authorizes deletion.
- This is conservative recovery for known terminal Terminal jobs, not a universal orphan cleaner. UNKNOWN workspaces intentionally remain for investigation; Windows Job Object/AppContainer and macOS process cleanup remain unimplemented. WP-18C therefore remains PARTIAL until host-level acceptance and broader crash recovery are proven.
