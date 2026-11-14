# Linux Terminal OS-Isolation Host Acceptance

**Protocol:** DCP-CEEP v1.0  
**Scope:** Linux bubblewrap runtime, filesystem/network boundaries, seccomp, and process-tree termination  
**Status:** Harness added; user-host evidence remains UNKNOWN until run on the target host

## Purpose

GitHub-hosted CI proves behavior only on its own ephemeral Linux runner. This procedure captures evidence from the actual Linux host and user account that will run the DCP Local Runner.

The harness runs five real bubblewrap tests:

1. Workspace read-only, scratch writable, and host sentinel not visible.
2. IPv4, IPv6, Unix sockets, socketpair, and io_uring setup denied; effective capabilities are zero.
3. A workspace symlink cannot reach a host file outside the sandbox mounts.
4. The integrated Terminal executor launches a catalog command and passes the seccomp descriptor.
5. A forked child that calls `setsid()` does not survive timeout/termination of the bubblewrap parent.

## Preconditions

- Linux on a supported architecture: x86_64 or aarch64.
- Bubblewrap installed at `/usr/bin/bwrap`.
- Python installed at `/usr/bin/python3` or `/usr/bin/python`.
- Run as the same unprivileged OS account that will run the Local Runner; do not switch to root merely to make the test pass.
- Run from the repository root with the project dependencies available.

## Run

```bash
python3 -m tools.local_runner_agent.linux_host_acceptance
```

The harness writes a JSON evidence object to stdout and unittest detail to stderr. It uses temporary test directories only; it does not modify the project workspace, enable Terminal templates, or change Runner configuration.

## Acceptance criteria

- Exit code is `0`.
- JSON `status` is `PASS`.
- `tests_expected` and `tests_run` are both `5`.
- `skipped`, `failures`, and `errors` are all `0`.
- The evidence records the host kernel, architecture, UID/GID, Python version, and exact bubblewrap path/version.

A missing dependency or unsupported host is `BLOCKED`, not PASS. Any skipped test, failed test, or test error is FAIL. Preserve the JSON output with the host acceptance record. Re-run after changing the kernel, bubblewrap package, user-namespace policy, or Runner account.

## Safety boundary

- Passing this harness is host-specific evidence, not a global guarantee for other machines.
- The harness exercises a test-only verified assessment; it does not change the production isolation detector. Production Terminal execution remains blocked until the required host acceptance and governance gates are reviewed.
- Windows AppContainer/LPAC and macOS sandbox acceptance are separate workstreams and are not covered.
- UNKNOWN and lease-expired workspaces remain preserved; this harness does not authorize their deletion.
