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
| Linux | bubblewrap + user/mount/PID/IPC/UTS/network namespaces + seccomp | Empty namespace root, explicit read-only runtime mounts, assigned workspace only, per-job scratch, private network namespace, reviewed syscall policy, child cleanup | BLOCKED — preflight contract only; no verified launcher |
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
- TerminalScriptExecutor now calls require_verified_isolation() before workspace resolution or process launch. The default platform assessment cannot return VERIFIED, so the executor fails closed on every host until a trusted verifier is implemented and accepted.
- Unit tests inject a test-only VERIFIED assessment to exercise the executor's existing process-control behavior; this is not production evidence.
- This module is a gate contract, not a process launcher and not a security boundary.

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
