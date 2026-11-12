# Local Job Control Plane — milestones 1–2

The local-first job API adds a durable SQLite queue, authenticated HTTP lifecycle endpoints, and per-job workspace isolation. It does not execute repository code, launch build commands, create VMs, or enable cloud provisioning.

## Dashboard API

Dashboard routes use the existing trusted-proxy HMAC session. Reads require an owner/operator session. Mutations require same-origin plus CSRF validation. Job cancellation is owner-only.

- `POST /api/jobs` — create with `Idempotency-Key`; payload allows only `repository`, immutable lowercase `commit_sha`, and `target` in the Flutter target allowlist plus `build_static_web`, `build_vite`, and `test_static_web` where the source type and Runner capability policy permit them.
- `GET /api/jobs?limit=50` — list recent jobs.
- `GET /api/jobs/{id}` — inspect a job.
- `GET /api/jobs/{id}/events` — lifecycle events.
- `GET /api/jobs/{id}/logs?after_id=0&limit=500` — paginated logs.
- `POST /api/jobs/{id}/cancel` — owner-only cancellation.

## Runner API

Runner routes use credentials separate from the gateway's internal API token and browser session. Configure `DCP_RUNNER_TOKENS` as a JSON object mapping worker IDs to unique tokens of at least 32 characters. Do not commit tokens or put them in dashboard configuration.

- `POST /v1/runner/register` — register host OS and allowlisted build capabilities; worker identity comes from its credential, never the request body.
- `POST /v1/runner/ping` — refresh fleet liveness.
- `POST /v1/runner/claim` — optional `lease_seconds` (5–300); only jobs supported by the registered Runner capabilities are claimable.
- `POST /v1/runner/{id}/heartbeat` — renew the authenticated worker's active lease.
- `POST /v1/runner/{id}/logs` — append a bounded stdout/stderr/system log message.
- `POST /v1/runner/{id}/finish` — report `succeeded|failed|cancelled`; only the current lease owner can finish.
- `POST /v1/runner/{id}/artifacts` — upload one bounded `application/octet-stream` artifact while the authenticated worker owns the active lease.
- `GET /api/artifacts/{artifact_id}/download` — authenticated Dashboard download with SHA-256 integrity verification.

The jobs database defaults to `DCP_GATEWAY_DATABASE + ".jobs"`; override with `DCP_GATEWAY_JOBS_DATABASE`.

## Safety boundary

Expired leases are recovered before a claim. Old workers are fenced by the lease checks in the store. The API accepts no shell command, arbitrary environment, filesystem path, or provider selection. Workspace allocation is local to the Runner host and does not imply repository checkout or build execution. Artifact upload/storage, VM creation, and Cloud Provisioning remain disabled. Flutter build execution is opt-in and restricted to an explicit trusted-repository allowlist. It runs on the Runner host; it is not an OS sandbox, so only repositories approved by the operator may be executed, and production runners should be disposable/isolated hosts.


## M3 — Unified Local Runner Agent and service modes

The supported Local Runner path is tools.local_runner_agent. The Windows launcher
Start-DCP-Gateway-Runner.ps1 invokes this agent (not the legacy tools.runner_agent
entry point) and supports four explicit modes:

- --check: read Gateway health only; no registration, claim, or execution.
- --enroll-only: register the worker as offline; it cannot claim jobs.
- --once: process at most one job; requires explicit execution opt-in.
- --serve: run the local supervisor until Ctrl+C/SIGTERM; requires explicit
  execution opt-in. The current job is allowed to finish, then the supervisor
  stops claiming new work.

The supervisor polls every 5 seconds by default (configurable from 1–60) and
uses bounded exponential backoff (maximum 300 seconds) for transient Gateway
errors. Permanent authorization/policy errors and a draining/offline Runner
stop the service instead of retrying forever. It processes one job at a time.
Execution is disabled by default and is never enabled by --check or
--enroll-only.

Required environment:
- `DCP_GATEWAY_URL` — HTTPS Gateway origin; HTTP is accepted only for loopback development.
- `DCP_RUNNER_WORKER_ID` — worker identity registered by the Gateway credential map.
- `DCP_RUNNER_TOKEN` — dedicated worker token (32+ characters); never pass it as a command-line argument or print it.
- `DCP_RUNNER_TIMEOUT_SECONDS` — optional request timeout (1–60; default 20).

Safe connectivity check:

```powershell
$env:DCP_GATEWAY_URL = "http://127.0.0.1:8789"
$env:DCP_RUNNER_WORKER_ID = "local-worker-01"
$env:DCP_RUNNER_TOKEN = "<dedicated-worker-token>"
python -m tools.local_runner_agent --check
```

The check reads only `/healthz`; it does not claim a job. The client uses Python's standard HTTPS certificate validation for remote Gateway origins. Job execution remains disabled unless the operator explicitly sets DCP_RUNNER_EXECUTION_ENABLED=1 and supplies at least one trusted repository or enrolled Local Project ID.


## M5 — Per-job Workspace Isolation

`tools/local_runner_agent/workspace.py` provides a local `WorkspaceManager` for Runner hosts.

- Every workspace is created beneath one configured absolute root, using the canonical Job UUID as its directory name.
- Workspace directories are mode `0700`; the ownership marker is mode `0600` and binds the directory to the exact Job UUID and authenticated worker ID.
- Duplicate allocation, cross-job/cross-worker access, symlink roots, symlink workspace entries, and path escapes fail closed.
- Active workspace count is bounded (default 8); regular-file bytes are measured against a per-workspace quota (default 2 GiB).
- Cleanup requires a valid ownership marker and removes only the matching Job workspace.
- The workspace manager does not clone a repository, extract an archive, spawn a process, or execute a build.

Example (local Runner process only):

```python
from tools.local_runner_agent.workspace import WorkspaceManager

manager = WorkspaceManager("/var/lib/dcp/workspaces")
workspace = manager.create(job_id, authenticated_worker_id)
# Future checkout/build stages may use this directory after their own policy gates.
manager.check_quota(job_id, authenticated_worker_id)
manager.cleanup(job_id, authenticated_worker_id)
```

The workspace E2E acceptance test creates a Job in the SQLite queue, claims it as a Runner, allocates an isolated workspace, verifies ownership and quota, cleans it, and records a terminal cancellation. It deliberately does not check out or execute untrusted repository content.


## M6 — Flutter Build Execution

The Runner Agent now has a one-job execution pipeline:

`Gateway claim → per-job workspace → immutable GitHub commit archive → Flutter command allowlist → bounded process → Gateway logs/status → workspace cleanup`.

- `GitHubCommitCheckout` downloads only `https://api.github.com/repos/{owner}/{repo}/zipball/{commit_sha}`; redirects are HTTPS-only and restricted to GitHub archive hosts.
- Archive download and expanded size, entry count, paths, and file types are bounded. Path traversal, symlinks, special files, and non-Flutter commits are rejected. No Git hooks, submodules, or repository scripts run during checkout.
- Flutter commands are fixed by target; arbitrary shell commands, command arguments, and environment variables are not accepted. The Runner performs a read-only host preflight before execution and rejects configured capabilities that were not detected locally.
- Supported targets: `test`, `build` (Android APK), `package` (Android App Bundle), `build_android`, `build_web`, `build_windows`, `build_linux`, `build_macos`, and `build_ios`.
- macOS/iOS targets require a macOS host; Windows and Linux targets require their corresponding host OS.
- Process execution has a bounded timeout, bounded combined output, process-group termination, and periodic Runner lease heartbeat/cancellation checks.
- Execution is disabled by default. `--check` remains health-only and `--enroll-only` registers the worker offline. `--once` processes at most one job; `--serve` runs the explicit long-lived supervisor. Both require `DCP_RUNNER_EXECUTION_ENABLED=1`, an absolute `DCP_RUNNER_WORKSPACE_ROOT`, and at least one non-empty allowlist in `DCP_RUNNER_TRUSTED_REPOSITORIES` or `DCP_RUNNER_TRUSTED_LOCAL_PROJECTS`, plus a successful local preflight. `DCP_RUNNER_CAPABILITIES`, when supplied, must be a unique subset of preflight-detected capabilities.
- Set `DCP_GITHUB_TOKEN` only as a host environment secret when private-repository read access is required. It is not stored in a job, logged, or passed in a URL.
- Build outputs are packaged by `FlutterArtifactPackager`, uploaded through the authenticated Runner endpoint, indexed with SHA-256 metadata, and downloadable through the authenticated Dashboard Artifact Center.

Example PowerShell configuration (use a dedicated, disposable Runner host and an operator-approved repository):

```powershell
$env:DCP_GATEWAY_URL = "https://<your-gateway-origin>"
$env:DCP_RUNNER_WORKER_ID = "local-worker-01"
$env:DCP_RUNNER_TOKEN = "<dedicated-runner-token>"
$env:DCP_RUNNER_EXECUTION_ENABLED = "1"
$env:DCP_RUNNER_WORKSPACE_ROOT = "D:\\DCP\\workspaces"
$env:DCP_RUNNER_TRUSTED_REPOSITORIES = '["owner/repository"]'
$env:DCP_RUNNER_CAPABILITIES = '["flutter","android","web"]' # Add windows only when Visual Studio C++ toolchain preflight passes
python -m tools.local_runner_agent --once
```

The command processes no more than one queued job. The host must have the Flutter SDK installed and on PATH. The Flutter process runs on the Runner host rather than inside an OS sandbox; do not add repositories to the trusted list unless their build/test code is approved for execution on that host.


## M7 — Artifact Center

- Flutter build output is collected from target-specific output paths. Single-file outputs (APK/AAB) are stored directly; directory outputs (Web, Windows, Linux, macOS, iOS) are packaged into a bounded ZIP.
- Runner uploads use a dedicated bearer-authenticated endpoint and a sanitized filename header; browser credentials are never used for Runner upload.
- Gateway storage uses a private absolute directory (default: `<DCP_GATEWAY_DATABASE>.artifacts`) configurable with `DCP_GATEWAY_ARTIFACTS_ROOT`.
- `DCP_GATEWAY_MAX_ARTIFACT_BYTES` controls the per-artifact upload limit (default 100 MiB; maximum 1 GiB).
- Each artifact receives a UUID, job/worker ownership record, size, creation timestamp, and SHA-256 digest. Upload requires a current Job lease and verifies it again after writing.
- Files are written to private temporary files and atomically moved into storage. Download verifies the stored SHA-256 before streaming the file.
- Dashboard APIs expose metadata only; the download route requires an authenticated owner/operator session and sets private/no-store and nosniff headers.
- The Dashboard Build Jobs panel displays successful Job artifacts with authenticated download links. Artifacts are not exposed for failed or cancelled Jobs.
- Retention pruning is available through `ArtifactStore.prune(retention_days=30)`; scheduling retention is an operator responsibility and is not enabled automatically in this increment.


## Local Windows Runner setup

The local Windows stack can provision a dedicated Runner credential without placing the token in source control or printing it to the console.

1. Run `Setup-DCP-Local-Runner.cmd`. It creates or reuses a worker credential in `%LOCALAPPDATA%\DCP\runner-tokens.json`, protects the file with a current-user/SYSTEM/Administrators Windows ACL, and does not display the token.
2. Stop the existing DCP stack with Ctrl+C in its stack PowerShell window, then restart it with `Start-DCP-Local.cmd`. The Local Auth Proxy loads the protected credential map into the Gateway process at startup.
3. Enroll the host offline first:

   ```powershell
   .\Start-DCP-Gateway-Runner.cmd -WorkerId windows-local-01
   ```

   This calls `--enroll-only`; the Runner appears offline and cannot claim jobs.
4. Only after reviewing the trusted repository and host preflight, explicitly enable execution for one repository:

   ```powershell
   .\Start-DCP-Gateway-Runner.cmd -WorkerId windows-local-01 -EnableExecution -TrustedRepository "owner/repository" -Once
   ```

   Omit `-Once` to run the worker loop until Ctrl+C. Execution is never enabled by the setup command or offline-enrollment default.

The Gateway listens on loopback port 18790; the Dashboard remains on 8789. The Gateway reads the protected token map at startup; Runner tokens are never injected into build subprocesses. Build subprocesses receive only the safe OS/toolchain environment allowlist. Cloud Provisioning remains disabled.

If the credential file is created or changed while the Gateway is running, restart the local stack before enrollment so the Gateway reloads the worker token map.


## M8 — Local Runner Fleet Registry

- The Gateway keeps a persistent inventory of local Runner workers, host OS, declared capabilities, registration time, last-seen time, and state (`online`, `draining`, `offline`). Configure its database with `DCP_GATEWAY_RUNNERS_DATABASE` (default `<DCP_GATEWAY_DATABASE>.runners`) and stale timeout with `DCP_GATEWAY_RUNNER_STALE_SECONDS`.
- Worker identity is derived from its dedicated Runner token; the client never supplies its own worker ID in registration or heartbeat payloads.
- A Runner must register before claiming work. Job claims are filtered by the Runner's registered capabilities: Flutter test, Android, Web, Windows, Linux, macOS, and iOS.
- Unsupported platform jobs remain queued for a compatible worker instead of being claimed and failing on the wrong OS.
- Runner liveness is refreshed during active builds. Workers older than `DCP_GATEWAY_RUNNER_STALE_SECONDS` (default 60 seconds; allowed 15–3600) are reported offline.
- Dashboard operators can Drain a worker to stop new claims while allowing its active Job to finish, then Enable it again. A stale worker becomes online again only after it checks in.
- `host_os` is recorded separately from build capabilities. Configure `DCP_RUNNER_CAPABILITIES` as a JSON array containing only targets actually detected by local preflight (for example `flutter`, `android`, `web`, `windows`, `linux`, `macos`, `ios`). A Windows host without Visual Studio may still register for Android/Web work but will not advertise Windows desktop builds. The default uses the full preflight-detected capability set; cross-platform targets are never assumed.
- The CLI remains one-shot (`--once`); continuous polling/daemon supervision is a separate deployment decision.


## M7 — Explicit Local Folder project registry

`tools/local_runner_agent/local_project.py` provides the first Local Folder intake foundation.

- An operator explicitly enrolls an existing absolute directory as an allowed root.
- A project must be selected beneath an enrolled root; the root itself and paths outside it are rejected.
- The registry stores a local project ID, root ID, relative path and SHA-256 source fingerprint.
- Fingerprints include sorted relative paths and file contents; known generated/dependency directories are excluded.
- Symlinks/junctions and special filesystem entries are rejected; file count and total bytes are bounded.
- Files are opened without following symlinks where the platform supports `O_NOFOLLOW`, and metadata is checked for mutation during hashing.
- Registry writes are atomic and use restrictive POSIX file permissions.
- Registration and refresh are metadata/read operations only. They do not copy, execute, install dependencies, or contact GitHub/cloud services.

This is a Local Agent library capability, not yet a complete Dashboard import workflow. A later integration must expose only enrolled project IDs through an authenticated, owner-authorized API; the browser must never submit arbitrary local paths. A stable snapshot fingerprint identifies observed content but does not freeze files against subsequent edits, so jobs must revalidate or materialize an immutable snapshot before execution.


## M8 — Local Folder enrollment CLI and owner-only read API

The Local Runner Agent now exposes explicit local CLI operations:

```powershell
python -m tools.local_runner_agent --enroll-root "D:\\Development\\Projects"
python -m tools.local_runner_agent --register-project "<ROOT_ID>" "D:\\Development\\Projects\\sample-app"
python -m tools.local_runner_agent --list-projects
```

The registry file defaults to `%LOCALAPPDATA%\\DCP\\local-projects.json` on Windows (or `~/DCP/local-projects.json` when LOCALAPPDATA is absent). The Local Auth Proxy configures the Gateway to use the same file. These CLI commands do not connect to the Gateway and do not execute imported project code.

Owner-only, read-only Gateway endpoints:

- `GET /api/local-projects/roots` — enrolled root IDs and display labels (never absolute host paths).
- `GET /api/local-projects` — registered project IDs, relative paths, fingerprints and bounded file metadata.
- `GET /api/local-projects/{project_id}` — one registered project by ID.

The Local Auth Proxy allowlists only these GET paths. The Gateway independently verifies the signed owner session and returns no absolute filesystem paths. Operators are denied. No browser-facing POST endpoint accepts a filesystem path; enrollment and project selection remain explicit local CLI actions until a safe local folder-picker/agent workflow is designed.

The Gateway registry is opt-in through `DCP_LOCAL_PROJECT_REGISTRY`; a standalone Gateway with no configured registry does not create a registry in the user's home directory and reports the API unavailable. Registry updates are reloaded on each read so CLI enrollment becomes visible without restarting the Gateway.


## M9 — Dashboard Project Import workspace

The Dashboard now has a Project Import view with separate authenticated read-only source catalogs:

- GitHub App installation repository list, branch/tag references, full commit SHA verification and bounded project inspection.
- Local enrolled root labels and project IDs, relative paths and SHA-256 fingerprints.
- Owner-session checks before catalog reads.
- No browser-provided filesystem paths, source download, dependency installation, build, runtime launch or job creation from this view.
- Public GitHub research remains a separate tokenless public API feature; private repository reads use the Local Auth Proxy and GitHub App server-side credentials.
- GitHub App import catalog and ref/commit/project inspection routes are owner-only at the Gateway.

The selected source evidence is currently a Dashboard view state only. It is not yet a persisted unified project record or an immutable job snapshot. That requires the next Project Snapshot/Import-to-Job workstream.


## M10 — Verified Local Project Snapshot Materialization

`LocalProjectRegistry.materialize_project(project_id, destination, expected_sha256)` creates a new, bounded, read-only-permissions snapshot copy for a future job workspace.

- Requires an existing registered project ID and the exact SHA-256 fingerprint captured at queue time.
- Revalidates root containment and source fingerprint before copying.
- Copies only regular files; rejects symlinks, special entries, unsafe relative paths and destination links.
- Uses no-follow file opens where supported, exclusive destination creation, streaming SHA-256 and file metadata checks.
- Revalidates the source after copying and verifies the materialized snapshot has the exact expected fingerprint, file count and byte count.
- Refuses to overwrite an existing destination and cleans up only the newly created partial snapshot on failure.
- Applies read-only file/directory permissions as a best-effort integrity guard. This is not an OS sandbox and does not make the snapshot tamper-proof against the same local user.
- Does not execute source, install dependencies, contact the network or create a job.

The next integration step is to bind the project ID and expected fingerprint into the durable job payload, then have the Local Runner materialize the verified snapshot before executing only an explicitly approved, supported build adapter.


## M11 — Local Web Build, Runtime and Static Playwright

The Local Runner pipeline now supports:
- `build_static_web` for detected dependency-free Static HTML/CSS/JS projects.
- `build_vite` for supported React/Vite and Vue/Vite projects when the Vite CLI and dependencies are already present locally. DCP does not run package installation or npm lifecycle scripts.
- `test_static_web` for detected dependency-free static projects only, requiring both `web` and `playwright` Runner capabilities and the explicit `DCP_RUNNER_PLAYWRIGHT_ENABLED=1` opt-in.

The static RuntimeManager binds to `127.0.0.1`, serves only generated output, checks health, records bounded logs, and stops its owned process. The authenticated Preview Proxy provides owner/job-bound static preview sessions, but the current `test_static_web` implementation starts RuntimeManager directly; Playwright-through-Preview-Proxy E2E is not yet established.

Playwright uses a fixed DCP-owned test plan, Chromium sandboxing, exact loopback HTTP origin routing, WebSocket blocking, WebRTC API denial and service-worker blocking. These browser controls are defense-in-depth, not OS-level process isolation or a host firewall. Only trusted projects on a suitably isolated Runner may be tested.

The test evidence currently consists of three viewport screenshots, a JSON report and a bounded ZIP artifact. It does not include traces, cross-browser results, visual baselines, full WCAG conformance or authenticated preview-proxy browser coverage. See `docs/DCP-PLAYWRIGHT-TESTING.md` and `docs/DCP-ACCEPTANCE-TEST-PLAN.md`.

## Lease retry and worker-crash policy

Every new job starts with attempt_count=0 and max_attempts=3. A successful
claim increments attempt_count inside the same SQLite transaction that moves
the job to running. The retry limit is server-owned; clients cannot raise it.

- An expired running lease is requeued while attempts remain.
- When the third claimed attempt expires, the job becomes failed with
  error_code LEASE_EXPIRED instead of returning to the queue forever.
- An expired cancel_requested lease becomes cancelled and is never retried.
- Lease recovery preserves last_worker provenance and emits an audit event
  containing worker ID and attempt counters.
- Old workers remain fenced: heartbeat, log, or finish calls after lease expiry
  cannot mutate the recovered job.
- Claims use SQLite BEGIN IMMEDIATE and a conditional state transition so two
  independent Gateway/Store instances cannot own the same queued job.

The Dashboard job API returns attempt_count and max_attempts as operational
metadata. This is retry accounting, not a guarantee that an interrupted
workspace was cleaned; workspace reconciliation remains a separate acceptance
requirement before treating Runner crash recovery as fully production-ready.


## HTTP lease-recovery acceptance

The authenticated Runner API acceptance flow registers two independent workers,
lets the first worker claim a job, expires its lease, and lets the second worker
claim the recovered job. It verifies attempt counters and last_worker
provenance in the public claim response, rejects the first worker's stale
heartbeat with HTTP 409, and allows only the current lease owner to finish.
This validates the complete Gateway HTTP path in addition to the JobStore unit
tests. It uses temporary SQLite stores and test-only Runner credentials.


## M8 — Unified Windows Runner launcher and supervised mode

The supported Windows launcher is Start-DCP-Gateway-Runner.ps1. It loads the
worker token from the protected LocalAppData credential file, maps WorkerId to
DCP_RUNNER_WORKER_ID, uses the unified tools.local_runner_agent module, and
restores the caller's process environment after exit.

- Default invocation without -EnableExecution performs offline enrollment only.
- -EnableExecution requires at least one explicit -TrustedRepository or
  -TrustedLocalProject. Local Project IDs must be canonical UUIDs.
- -Once runs one job. Without -Once, the launcher uses --serve.
- Playwright and custom capability overrides are cleared from inherited process
  environment; they are not enabled implicitly by the launcher.
- The service stops taking new jobs after Ctrl+C/SIGTERM and lets the current
  pipeline call return before exiting. Transient Gateway errors use bounded
  backoff; permanent authorization/policy errors stop the service.
- The legacy tools.runner_agent.agent implementation remains for compatibility
  tests but is no longer invoked by the supported Windows launcher.
