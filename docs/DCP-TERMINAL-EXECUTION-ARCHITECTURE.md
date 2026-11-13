# Terminal Studio — App-Controlled Workspace Execution

Status: WP-02 implementation contract (in progress)
Branch: feat/terminal-studio-authorized-workspace-execution
Base: a34281ffc837ac171508df009ff504b4d4dd22b1

## Product outcome

An authenticated user selects a Project, a Project Workspace, and a catalogued Script in Dashboard. The app authorizes that exact operation and submits a typed job. A trusted Runner independently verifies the job and executes the server-resolved template inside the assigned workspace. Output, cancellation, timeout, result, and audit evidence return to Dashboard.

This is an execution-capable project tool, not a preview-only command list and not an arbitrary browser shell.

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

The existing Terminal Studio catalog, preview, JSON import, and Owner review are metadata workflows. Existing Runner Pipeline handles existing build/test job types and is not yet a general terminal executor. Existing Workspace Manager allocates job-scoped directories but is not, by itself, a project ACL or OS sandbox. This work must integrate those components without claiming stronger isolation than they provide.


## Implementation status — 2026-11-13

The current feature branch adds the following foundations:
- a strict typed Terminal request contract that rejects command, shell, executable, argv, cwd, env, runner, role, approval, and permission fields from the browser;
- a durable SQLite Terminal Grant Store with short TTLs, read-only action scope, one-time Job/Runner binding, atomic one-time consumption, expiry, revocation, and exact actor/session/project/workspace/snapshot/template/parameter binding;
- stable `workspace_id` values on registered Local Project records, including migration of older registry entries and preservation across project refresh;
- trusted in-process workspace resolution that verifies project/workspace pairing, enrolled-root containment, and the current source fingerprint before returning a host path;
- safe API exposure of the opaque workspace identifier without exposing host paths;
- Gateway startup configuration for the separate private Terminal Grant database;
- an Owner-only, same-origin, CSRF-protected authorization endpoint that remains fail-closed while templates are disabled;
- a Runner-credential endpoint and client method that consume grants only for an active, unexpired Job lease.

These are storage and identity foundations only. The grant store deliberately does not authenticate callers or decide Project ACLs: only an authenticated Gateway handler may issue or consume grants after verifying the app identity and Runner credential/active Job lease. The authorization and Runner verification endpoints now exist, but they cannot yet be used by a real Terminal job: the Job Store/Pipeline still has no terminal-script target and the Runner Pipeline does not yet call the verification client. The current Project Registry is Owner-only and does not provide a per-user capability/ACL model; any first execution endpoint must preserve that restriction unless a real ACL capability model is added. Per-user Project ACLs are not yet available; the existing Local Project API is Owner-only, so any first execution endpoint must preserve that restriction unless a real ACL capability model is added. All seven catalog templates remain `execution_enabled: false`; actual execution remains unavailable.

Evidence status for this branch: implementation files and tests have been added, but the tests have not yet been executed by a local checkout or CI run. Do not label these tests PASS until a workflow reports success for the exact branch head SHA.
