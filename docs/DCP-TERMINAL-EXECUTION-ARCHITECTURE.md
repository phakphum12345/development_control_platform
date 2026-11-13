# Terminal Studio — App-Controlled Workspace Execution

Status: Implementation merged via PR #112; execution remains fail-closed pending isolation gates
PR #112 merge commit: b0a2cd0d542491886a529666909024af1fb64ced
Current main baseline at this checkpoint: e008844d8c6e6b15c71b7bf36f00f42e66233387

## Product outcome

Target behavior: an authenticated user selects a Project, a Project Workspace, and a catalogued Script in Dashboard. The app authorizes that exact operation and submits a typed job. A trusted Runner independently verifies the job and executes the server-resolved template inside the assigned workspace. Output, cancellation, timeout, result, and audit evidence return to Dashboard.

PR #112 merged the Dashboard grant/confirm/queue workflow, typed Job API, Runner grant binding/consumption, bounded redacted output, and reuse of the existing Job status/log/cancel lifecycle. The code path is present, but all built-in templates remain disabled; therefore the target execution behavior is not currently enabled. This is not an arbitrary browser shell.

## Non-negotiable trust boundary

1. Browser requests contain identifiers and typed data only: project_id, workspace_id, template_id, parameter values, and an idempotency key.
2. Browser requests MUST NOT contain executable paths, command strings, raw argv, shell fragments, environment maps, working-directory paths, runner credentials, or permission claims.
3. Gateway authenticates the app session, enforces same-origin and CSRF, resolves project/workspace ownership, checks the actor's role and project-scoped capability, checks policy and approval, then creates a durable typed job.
4. Runner authenticates with its own runner credential, claims only eligible jobs, validates the signed/server-owned job envelope and policy version, resolves the immutable template from its trusted catalog, validates parameters again, and derives argv itself.
5. Workspace path is derived from the trusted workspace manager and job binding. A path supplied by the browser is never used as cwd.
6. Execution uses a fixed executable registry and argv list. shell=True and browser-controlled shell invocation are prohibited. Any platform shim must be a separately reviewed adapter with fixed semantics.
7. Imported templates remain inert. Owner review, import approval, or catalog visibility alone does not grant execution permission. Imported templates require a separate executable registration and explicit policy authorization.
8. Missing, stale, malformed, revoked, or unverifiable authorization fails closed.

## Authorization model

An execution grant is bound to all of:
- authenticated actor and app session;
- project ID and workspace ID;
- template ID and immutable template version/hash;
- permitted action class (read-only, build/test, workspace-write, install, network, destructive, privileged);
- parameter schema/version and validated parameter digest;
- approval record where required;
- issue time, expiry, nonce, and one-time job/idempotency identity.

The Runner does not trust a browser-supplied role, approval flag, workspace path, or grant. Authorization is created and persisted by the Gateway after policy checks. Revocation and expiry are checked before execution; the job lease is also checked during execution/heartbeat.

## Execution lifecycle

Dashboard -> Gateway authentication/CSRF -> Project ACL -> Workspace binding -> Template resolution -> Parameter validation -> Risk/policy decision -> Approval (if required) -> Durable job creation -> Runner claim -> Runner authorization recheck -> Workspace containment check -> argv execution -> bounded output -> heartbeat/cancel/timeout -> process-tree cleanup -> durable result/audit -> Dashboard history.

## MVP execution scope

First enable only fixed, read-only built-ins already in the trusted catalog:
- Git status
- Git diff
- Git log (bounded integer parameter)
- Inspect commit (full SHA parameter)
- Python version
- Node.js version

All are network-denied, read-only, time-bounded, output-bounded, and require an enrolled project workspace. Tool absence is a failed preflight, not a reason to fall back to arbitrary shell.

Build/test, file mutation, dependency installation, network access, imported templates, and interactive PTY are separate policy scopes and remain disabled until their own controls and tests pass.

## Required controls

- per-project and per-workspace authorization; no cross-project access;
- role and capability checks on every Dashboard request;
- runner authentication independent from browser session;
- immutable template ID/version resolution on Runner;
- idempotent job creation and durable job state;
- fixed executable allowlist, argv arrays, minimal environment;
- no secrets in argv, environment, output, logs, or artifacts;
- strict workspace ownership and path/symlink containment;
- timeout, output byte cap, process-tree termination and cleanup verification;
- bounded concurrency and workspace quota;
- cancellation and lease-loss behavior;
- audit actor, project, workspace, template/version, parameter digest, policy decision, approval reference, job ID, timestamps, exit status, cleanup status;
- imported templates never become runnable merely through import/review;
- no cloud provisioning, paid service, or new runtime dependency without separate approval.

## Work packages

### WP-02 — Trusted execution contract
- Freeze typed request/job/grant schemas.
- Implement parameter validation and immutable built-in template resolution on both Gateway and Runner.
- Implement fixed argv derivation and safe executor primitives.
- Add unit tests proving arbitrary executable/argv/cwd/env fields are rejected.

### WP-03 — App authorization and project/workspace binding
- Integrate existing app identity, CSRF, Project Registry and Workspace Manager.
- Define explicit project-scoped capabilities and approval records.
- Persist a short-lived, one-time execution grant in the durable control plane.
- Ensure Runner can independently verify the grant without trusting browser input.

### WP-04 — Durable Runner integration
- Add a typed terminal job target to existing Job Store/Queue and Runner Pipeline.
- Resolve project snapshot/workspace from trusted server-owned identifiers.
- Add heartbeat, idempotency, retry/recovery and lease-loss handling.
- No parallel or duplicate job engine.

### WP-05 — Output, cancellation and recovery
- Stream bounded, redacted output through existing job logs.
- Add stop/cancel and timeout with process-tree termination.
- Verify cleanup and retain immutable job result/audit records.

### WP-06 — Dashboard
- Project and Workspace selector based on authorized app data.
- Catalog and parameter controls generated from trusted schemas.
- Run requires an explicit app authorization decision; display scope and risk before submission.
- Live job state, output, cancel, exit code, history and audit.
- No raw command editor or browser shell endpoint.

### WP-07 — Security and cross-platform acceptance
- Auth/role/CSRF/project ACL tests.
- Forged grant, expired grant, replay, wrong project/workspace, changed template hash tests.
- Path traversal, symlink, environment leakage, shell injection, timeout, output cap, cancellation and process-tree cleanup tests.
- Linux and Windows CI; macOS only when an eligible runner exists.
- Documentation, traceability, evidence and release gate.

## Acceptance criteria

- A permitted user can choose a built-in script in Dashboard and execute it in the selected Project Workspace.
- The Runner executes only the server-resolved, versioned template.
- No API accepts arbitrary shell strings or browser-supplied argv/executable/cwd/env.
- A user cannot run against another project/workspace by changing request identifiers.
- Missing, revoked, expired, replayed, or mismatched grants never execute.
- Imported scripts remain inert unless separately registered and authorized.
- Stop, timeout, disconnect, and runner restart produce a bounded, auditable outcome.
- Dashboard shows the actual job result; preview-only is not reported as execution success.

## Current implementation boundary

The feature branch now contains a backend execution path through the existing Gateway, Job Store, Runner Registry/Scheduler and Runner Pipeline. It does not yet complete the Dashboard user experience, and it does not enable the built-in templates by default.

The Runner resolves the selected registered Project Workspace directly from its local registry after checking project/workspace identity and the current snapshot fingerprint. This is the user's actual registered project directory, not an arbitrary path supplied by the browser. The fixed executor is intentionally restricted to catalog templates marked read-only and network-denied. This policy is not an OS-level sandbox: the process still runs under the Runner service account and inherits that account's operating-system access. Do not describe the Workspace Manager or template metadata as kernel-enforced isolation.

Terminal output is captured within a strict byte limit, redacted as a complete bounded stream (including credentials split across reader chunks and multi-line private-key blocks), then split into bounded messages and appended to the existing durable Job logs. This is not live streaming while the process is running; there is no PTY or separate Terminal session manager. Existing Job status, log, cancel, lease and recovery primitives are reused; there is no PTY or separate Terminal session manager.

## Implementation status — 2026-11-13

| Work package | Status | Evidence boundary |
|---|---|---|
| WP-01 Foundation audit | PASS — recorded | Existing auth, Project Registry, Job Store, Runner Registry/Scheduler, Workspace Manager and logs identified |
| WP-02 Typed execution contract | IMPLEMENTED | Strict browser request contract; catalog parameter normalization; template and parameter digests; arbitrary command/shell/executable/argv/cwd/env/runner/role/approval fields rejected |
| WP-03 App authorization and workspace binding | IMPLEMENTED — backend | Owner-only same-origin/CSRF grant issuance; short-lived SQLite grant; exact actor/session/project/workspace/snapshot/template/parameter scope; grant reserved to deterministic Job ID before queue visibility; one-time Runner binding and consumption after active lease verification |
| WP-04 Durable Runner integration | IMPLEMENTED — backend | terminal_script Job target; explicit Runner terminal capability; capability-aware scheduling; Runner client grant verification; fixed-template executor; local trusted-project allowlist and workspace/snapshot revalidation |
| WP-05 Output/cancel/recovery | PARTIAL | Bounded output, whole-stream secret redaction, timeout, cancellation polling and process-tree cleanup use existing Job primitives; output is not live-streamed; PTY and terminal-specific history UI are absent |
| WP-06 Dashboard Run workflow | NOT IMPLEMENTED | Catalog/preview/import/review UI exists, but there is no Run control, project/workspace execution selector, grant confirmation UI or job-output panel for Terminal |
| WP-07 Security/cross-platform acceptance | IN_PROGRESS | Unit and API tests added; exact-head CI is still required. No claim of PASS until all required workflows complete successfully |

### Implemented backend path

1. POST /api/terminal/authorize authenticates the app session, enforces Owner role, same-origin and CSRF, resolves the registered Project Workspace and issues a scoped, short-lived grant.
2. POST /api/terminal/jobs accepts only identifiers, a trusted template ID, typed parameters and the opaque grant reference. It validates the grant against the authenticated subject/session and reserves it to a deterministic Job ID before that Job becomes visible to Runner polling. Idempotency is scoped to the authenticated session.
3. The existing Job Store validates the terminal_script payload and the existing Scheduler routes it only to a registered Runner advertising the explicit terminal capability.
4. The Runner verifies the active Job lease through its credential-authenticated Gateway endpoint. The Gateway binds and consumes the grant once for that Job and Runner.
5. The Runner resolves the registered project/workspace pair and current snapshot, then invokes only a trusted catalog template through a fixed executable allowlist, argv array and shell=false.
6. Existing Job logs, status, cancellation, lease and recovery are reused. Terminal output is byte-bounded and redacted before it reaches durable logs.

### Explicitly disabled / outstanding

- All built-in catalog templates still have execution_enabled: false. The API and Runner therefore fail closed by default; this branch does not authorize production execution merely because the code path exists.
- Imported command packs remain inert. Approval/review does not make an imported template executable.
- The Project Registry and browser-facing Local Project API are Owner-only. There is no per-user Project ACL/capability model yet; do not broaden access beyond the existing Owner boundary.
- The Runner execution code path resolves only fixed read-only built-ins in the actual registered Project Workspace, but every built-in template remains `execution_enabled=false`; no Terminal process can currently be started from the catalog.
- No OS sandbox or kernel-level network isolation is claimed. Workspace binding, a temporary HOME, sanitized PATH, fixed argv and process-tree termination are defense-in-depth controls, not an isolation boundary.
- The Dashboard Run flow, separate grant confirmation, idempotent queue submission, Job status/log polling, and cancellation controls are implemented through the existing Job Control Plane. Interactive PTY and independent terminal-specific history remain out of scope.
- Before any template is enabled, complete OS-isolation design and acceptance, Git helper/config hardening, adversarial tests, process-tree cleanup verification, and real supported-host acceptance. Git read-only commands must not invoke repository-configured fsmonitor hooks, external diff helpers, textconv filters or pagers.
- CI must be evaluated against the exact latest PR head. Pending, skipped, missing or cancelled workflows are not PASS.
- No PR merge, deployment or template enablement is implied by these implementation commits.

