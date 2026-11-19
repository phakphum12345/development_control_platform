# DCP Architecture and Dependency Map — 2026-11-19

**Baseline:** `985a78d5fba459c8a0cbcf47e5d00a858c6e6228`  
**Architecture rule:** extend the existing Gateway, Auth Proxy, Job Control Plane, Runner, workspace and artifact contracts. Do not create parallel queues, registries or command executors without an approved architecture decision.

## 1. Logical architecture

```text
User / Browser
   |
   v
Static Dashboard (dashboard/index.html)
   | same-origin authenticated /api/*
   v
Local Auth Proxy (tools/local_auth_proxy.py)
   | validated owner session, CSRF/Origin and bounded API forwarding
   v
Cloud Gateway HTTP service (tools/cloud_gateway/server.py)
   |
   +--> Owner / OIDC / proxy assertion / policy
   |
   +--> Project intake
   |      +--> GitHub App catalog, refs and immutable commit inspection
   |      +--> Local Project registry and approved roots
   |
   +--> Job Control Plane / SQLite Store / Scheduler
   |      +--> Job state, leases, checkpoints, cancellation
   |
   +--> Local Runner Agent
   |      +--> Checkout / snapshot materialization
   |      +--> Workspace / file safety
   |      +--> Fixed build adapters / runtime / browser test
   |      +--> Artifact upload and cleanup
   |
   +--> Terminal catalog / grants / execution contract
   |      +--> Fail-closed OS isolation assessment
   |
   +--> Optional Cloud Runner control plane
          +--> Provider Router / Azure / Orka / budget / cleanup
          +--> Explicit provisioning and VM gates (OFF by default)
   |
   +--> Document Workflow / scoped write proposal
   +--> MCP engine (separate local STDIO, read-only tools)
   |
   v
SQLite metadata + bounded workspaces + logs + SHA-256 artifacts
```

## 2. Main component boundaries

| Layer | Main files | Responsibility | Security boundary |
|---|---|---|---|
| Dashboard | `dashboard/index.html`, `dashboard/recon-back-box/index.html` | User-facing project, job, infrastructure, terminal, document and review tools | Browser UI is not an authorization boundary; server must verify every action |
| Local Auth Proxy | `tools/local_auth_proxy.py` | Same-origin session/login/logout, CSRF/Origin, dashboard/API routing | Owns browser session; do not trust browser role or raw forwarded identity headers |
| Gateway | `tools/cloud_gateway/server.py`, `service.py` | API dispatch, owner/policy enforcement and service composition | Authentication, request schema, role, origin and operation-specific checks |
| Persistence / Job Control | `store.py`, `sqlite_security.py`, `job_control.py`, `scheduler.py` | Durable jobs, leases, checkpoints, state and audit | SQLite permissions, transactions, idempotency and recovery |
| Project intake | `github_app.py`, `github_app_runtime.py`, `public_github.py`, `local_project.py`, `checkout.py` | Authorized GitHub inspection and enrolled local-folder snapshots | Immutable SHA/fingerprint, approved roots, no execution on import |
| Local Runner | `tools/local_runner_agent/`, `tools/runner_agent/` | Claim/execute jobs, materialize snapshots, build/test, runtime and cleanup | Fixed argv, trust allowlist, scoped workspace, limits and process supervision |
| Artifact subsystem | `tools/cloud_gateway/artifacts.py`, `tools/local_runner_agent/artifacts.py` | Upload/download, digest and artifact metadata | Authenticated access, digest verification and provenance |
| Terminal subsystem | `terminal_catalog.py`, `terminal_grants.py`, `terminal_execution_contract.py`, `terminal_executor.py` | Inert templates, approval/grants and bounded execution contract | Execution remains blocked until OS isolation is verified; workspace is not a sandbox |
| OS isolation | `linux_sandbox.py`, `terminal_isolation.py`; candidate Windows PSEC on PR #140/#149 | Platform-specific process boundary | Only actual-host evidence can promote a backend to VERIFIED |
| Cloud control | `tools/cloud_gateway/azure_*.py`, `orka.py`, `provider_router.py`, `tools/cloud_runner/backend.py` | Optional provider lifecycle, budgets, bootstrap and cleanup | Multiple independent OFF gates; no automatic cloud fallback |
| Document workflow | `tools/document_workflow/gateway.py`, `writer.py` | Scope grants, write proposal, approval and read-back verification | Project/path scope and exact content hash, explicit owner approval |
| MCP | `tools/mcp_engine/engine.py`, `server.py` | Bounded local source inspection | Read-only; no shell, Git write, network listener or source write |
| Packaging | `packaging/package-release.ps1`, `packaging/windows/DCP.iss` | PWA/portable ZIP/Windows installer | Installation and upgrade must be separately tested |

## 3. Core data flows

### Project intake to job
1. Dashboard requests repository catalog or enrolled Local Project list.
2. Auth Proxy authenticates the Owner session and forwards a same-origin request.
3. Gateway validates repository installation/ref/commit or Local Project ID and current snapshot fingerprint.
4. Job request binds immutable source identity, target, policy and approval.
5. Runner claims a lease and materializes the verified snapshot.
6. Runner executes only a supported fixed adapter under existing trust and policy checks.

### Build/test to artifact
1. Runner pipeline validates project/target and required toolchain.
2. Fixed adapter builds supported output.
3. Optional static runtime/browser test produces bounded report/screenshots.
4. Artifact Store records digest and verifies bytes on download.
5. Dashboard displays backend-confirmed job/artifact state.

### Terminal command
1. Dashboard previews an inert typed template.
2. Owner authorizes a project/workspace-scoped grant.
3. Gateway binds grant to a durable Job and Runner lease.
4. Runner must pass the fail-closed isolation gate before process creation.
5. Until a platform backend is VERIFIED by actual-host acceptance, built-in templates stay disabled.

### Cloud runner
1. Owner explicitly requests a supported provider/OS/repository/commit.
2. Gateway validates independent provisioning, VM creation, provider, budget and Owner approval gates.
3. Provider bootstrap creates an ephemeral runner only when all approved gates pass.
4. Runner online/job/teardown and orphan cleanup require separate evidence.
5. No automatic local-to-cloud fallback.

## 4. Dependency order

```text
Owner Identity + Auth Proxy + Gateway Policy
                |
                v
      Project Intake + Immutable Snapshot
                |
                v
       Job Control + Durable Checkpoints
                |
                v
          Local Runner + Workspace
                |
          +-----+------+
          |            |
          v            v
      Build/Test    Terminal Broker
          |            |
          v            v
      Artifacts    Verified OS Isolation
          |            |
          +-----+------+
                |
                v
       Dashboard E2E + Evidence
                |
                v
     Release / Install / Recovery Audit

Cloud Provider Path is a separate optional branch and remains OFF until explicitly authorized.
```

## 5. Known architecture risks / gaps

- Gateway and Auth Proxy use custom `BaseHTTPRequestHandler` dispatch; decorator-only route scanning will miss actual method/path handling. Build a source-backed method/path/role/CSRF matrix from the dispatch functions.
- Dashboard is a large static HTML/JavaScript file (2,639 lines at baseline). Element IDs are not view count; route metadata and actual handlers need explicit mapping.
- Mainline terminal isolation is fail-closed. Candidate Windows PSEC implementation is on unmerged PR branches and must not be treated as mainline behavior.
- Workspace boundaries and browser restrictions are defense-in-depth, not OS sandboxing.
- Provider adapter tests/mocks do not establish live VM creation or cleanup.
- Document writer and MCP are separate security surfaces; MCP remains read-only and document writes require scoped owner approval.
- The current docs contain dated inventories with stale counts; the 2026-11-19 baseline is authoritative for this branch only.

## 6. Next architecture validation

- Extract all Gateway and Auth Proxy dispatch cases into endpoint contracts.
- Trace each Dashboard view/action to API and backend service.
- Trace Job state transitions through Gateway, Store, Scheduler and Runner.
- Verify source identity from import to artifact manifest.
- Verify cleanup paths for success, failure, cancellation, lease loss and crash.
- Verify no terminal process can start when isolation is BLOCKED.
- Verify all cloud/VM gates default OFF after restart and on provider failure.
