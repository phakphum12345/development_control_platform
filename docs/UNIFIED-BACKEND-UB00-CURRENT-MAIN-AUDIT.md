# UB-00 — Unified Backend Current-Main Source Audit

**Repository:** `phakphum12345/development_control_platform`  
**Branch:** `feat/unified-backend-multi-account-foundation`  
**Source baseline:** `main` at `57589873583c706d4af9756709596fdba7c22de9`  
**Protocol:** DCP-CEEP v1.0  
**Status:** IN_PROGRESS — source/schema review only; no runtime or database changes.

## 1. Purpose and evidence boundary

This checkpoint continues the all-account Unified Backend work from the exact current `main` SHA. It reconciles the earlier 2026-11-23 audit baseline (`eaa9ceb91088c39b90d9b11b3817dc793e40005a`) with the two later main commits and inspects the current identity, Gateway, job, runner, artifact and provider boundaries.

The repository is the shared Control Plane / Runner Infrastructure. It is not a replacement for each application's domain API or database.

This is a static source review. It is not an implementation, penetration test, migration rehearsal, deployment acceptance or proof that an OIDC provider is configured in production.

## 2. Baseline reconciliation

- Current `main`: `57589873583c706d4af9756709596fdba7c22de9`.
- Compared with the previous live-audit baseline `eaa9ceb91088c39b90d9b11b3817dc793e40005a`, main is 2 commits ahead and 0 behind.
- Those commits add/update the append-only continuity ledger, the 2026-11-23 live repository audit, WP-01 API security acceptance, the Gateway/Proxy route crosswalk, implementation status, requirements traceability and representative authorization tests.
- The 2026-11-23 audit documents remain explicitly tied to their stated baseline. Their historic counts and PR register must not be silently relabelled as current-main values.
- PR #149 and #150 remain OPEN/DRAFT with `mergeable=false` against an older base. PR #155 is OPEN/DRAFT, based on the exact current main SHA, and must not be merged until its current-head checks and review gates are complete.

## 3. Identity and account admission findings

### 3.1 Existing OIDC building blocks

Current main contains reusable OIDC modules:
- `tools/cloud_gateway/oidc_client.py`
- `tools/cloud_gateway/oidc_config.py`
- `tools/cloud_gateway/oidc_auth_service.py`
- `tools/cloud_gateway/oidc_session_store.py`
- `tools/cloud_gateway/oidc_wsgi.py`
- `tools/cloud_gateway/oidc_deployment.py`
- `tools/cloud_gateway/oidc_edge_signer.py`

These provide useful protocol/session/signing building blocks, but their presence does not establish a live all-account login path.

### 3.2 Current admission is privileged-group-only

Source evidence at the baseline:
- `tools/cloud_gateway/oidc_session_store.py` stores `role` with SQLite CHECK constraint `role IN ('owner','operator')`; `create_session` accepts only those roles.
- `tools/cloud_gateway/server.py::ProxyIdentityVerifier.verify` rejects every role except `owner` and `operator`.
- `docs/oidc-ingress.md` maps configured Owner and Operator groups and explicitly denies a verified user with no matching group.
- The OIDC edge signer only issues an assertion after the trusted auth endpoint returns verified subject and configured privileged groups.
- The current Gateway session payload exposes subject and role, but no principal UUID, tenant selection, membership version or application grant.

**Conclusion:** normal authenticated users are not admitted by the current DCP role boundary. Do not simply add `member` to one role allowlist: the downstream stores and resource routes are not tenant-scoped.

### 3.3 Deployment integration remains a separate gate

OIDC client/auth/session/WSGI components exist, but current documentation describes a trusted reverse-proxy/oauth2-proxy edge integration and deployment-specific secrets, groups, issuer, audience and callbacks. No evidence in this audit proves that a production identity provider is configured, that all-account group-less admission is active, or that the OIDC WSGI path is mounted into every supported host. Treat live login as UNKNOWN until a deployment-specific end-to-end test proves it.

### 3.4 Local Auth Proxy is a separate single-owner path

The current `tools/local_auth_proxy.py` is not the multi-account OIDC session service:
- It loads one local Owner credential record from `owner-auth.json` (or the configured credential path).
- Its in-memory session records are created for that configured Owner username; the signed Gateway assertion hardcodes role `owner`.
- The local session map is process memory, not a durable multi-principal session database.
- Its login/logout and Proxy allowlist protect the local Dashboard workflow, but do not create personal tenants, organization memberships or per-account application grants.
- The OIDC WSGI app and edge signer are separate components. `oidc_deployment.py` builds a WSGI application from deployment configuration; a host must explicitly mount it. The local password Proxy does not itself establish that production OIDC mounting has occurred.

**Disposition:** preserve the existing local Owner workflow as a compatibility/admin path while designing the separate all-account identity path. Do not convert the local Owner password into a shared account credential or let a member inherit local host access.

## 4. Resource ownership and isolation findings

| Resource family | Current storage / key observed | Current isolation status | Required UB work |
|---|---|---|---|
| Dashboard identity/session | Subject + role; session hash | No DCP principal/tenant context | Stable principal key from verified issuer + subject; tenant membership and revocation-aware context |
| Jobs | `jobs.id`; global unique `idem`; no `tenant_id` or `principal_id` | Gateway role gate only; list/get are not owner-filtered | Tenant/principal ownership, scoped query helpers and scoped idempotency |
| Job events/logs | `job_id` foreign reference only | Inherits unscoped job access | Every event/log read must first authorize the parent job in tenant scope |
| Artifacts | Artifact ID and job ID | Worker lease protects upload; browser download/list path lacks tenant ownership | Resolve artifact through an authorized tenant-scoped job; verify immutable metadata and download handle scope |
| Previews | Runtime ID + job ID | Preview routes have additional Owner gate, not tenant ownership | Scope preview start/list/status/content/stop through authorized parent job |
| Local projects/workspaces | Local registry/project/workspace identifiers | Owner-oriented local host registry | Keep local host owner boundary; introduce per-principal project grants only with explicit host capability model |
| Runner registry | Global worker ID and capabilities | Worker credential authenticates a worker; no tenant assignment in registry | Server-issued tenant/capability assignment and worker lease scope |
| Cloud runner/infrastructure | Global resource IDs and idempotency keys | Owner/operator/Owner gates; not tenant-scoped | Keep privileged infrastructure admin separate; do not expose to members by broad role relaxation |
| Terminal grants/templates | Grant/template identifiers and actor subject | Owner-only / disabled execution gates | Preserve Owner approval and sandbox gates; no automatic member elevation |
| Document Workflow | Project/grant/proposal identifiers and actor subject | Owner-only | Tenant-aware project grants only after independent project ownership design |

### 4.1 JobStore details

`tools/cloud_gateway/job_control.py::JobStore` currently creates:
- `jobs(id PRIMARY KEY, idem UNIQUE NOT NULL, ...)`
- `job_events(id, job_id, ...)`
- `job_logs(id, job_id, ...)`

Observed methods include global `create`, `get_by_idempotency_key`, `get`, `list_recent`, `claim`, `cancel`, `events` and `logs`. There is no principal or tenant parameter in the inspected API signatures. Idempotency is global rather than tenant/principal scoped.

### 4.2 RunnerStore and provider routing

- `tools/cloud_gateway/store.py::RunnerStore` uses a globally unique `idempotency_key` and runner ID; lifecycle audit rows are keyed by runner ID, not tenant.
- `tools/cloud_gateway/runner_registry.py` registers workers by global worker ID and capabilities; its registry schema has no tenant assignment.
- `tools/cloud_gateway/provider_router.py` routes by approved OS profile (Azure for supported Windows/Linux profiles and Orka for macOS) and readiness. It is not a tenant authorization layer.
- A worker credential must remain distinct from a human account session. A worker may not infer tenant authority from a job payload.

## 5. Gateway route impact

The current route families and role/CSRF boundaries are already inventoried in:
- `docs/DCP-WP01-API-SECURITY-ACCEPTANCE.md`
- `docs/DCP-WP01B-GATEWAY-PROXY-ROUTE-CROSSWALK.md`

UB-00 adds the following all-account interpretation to that route map:

| Route family | Current boundary observed | Multi-account requirement |
|---|---|---|
| `GET /api/jobs`, job detail, logs, events, artifacts | Owner/Operator role; global JobStore lookup/list | Member may read only own/shared tenant resources; parent job authorization before child data |
| `POST /api/jobs` | Owner/Operator + same-origin + CSRF; repository allowlist/immutable commit validation | Member may submit only explicitly granted application job types and repositories; tenant/principal from verified context, never body |
| Job cancel/resume/preview | Sensitive Owner gates | Keep elevated operations separate; member cancellation may be a distinct capability only after resource ownership and state policy are implemented |
| `/v1/runner/*` | Worker bearer credential and worker/lease checks | Server-side worker-to-tenant capability binding; reject cross-tenant claim/report/upload |
| `/api/artifacts/*` and preview descendants | Authenticated dashboard role and job/runtime IDs | Scope all actions through authorized parent job and tenant; no direct artifact UUID authority |
| Infrastructure/Cloud Runner | Owner/Operator or Owner-specific checks, gates and CSRF | Remain privileged; tenant admins cannot create paid resources or bypass global approval |
| Terminal/Document Workflow | Owner-only controls and approval | Retain Owner approval and platform isolation gates; do not expose via generic member role |

The Local Auth Proxy has its own explicit allowlist and CSRF/session checks. A Gateway change alone is insufficient: Proxy path allowlists, session serialization, UI visibility and Gateway authorization must be reviewed together. The Proxy must never become an authorization bypass.

## 6. UB-00 gap register

| Gap | Evidence | Risk | Required disposition |
|---|---|---|---|
| No normal-member admission | Role constraints and signer policy accept Owner/Operator only | New accounts cannot use DCP safely | Design explicit member admission after principal/tenant model exists |
| No tenant/principal ownership columns | Job and runner stores lack ownership keys | Cross-account data exposure if role gate is relaxed | Additive, restart-safe migration and scoped data-access layer |
| Global idempotency | Job and infrastructure keys are globally unique | Collision or outcome disclosure between accounts | Scope by tenant + principal + operation; payload fingerprint conflict |
| Child resources not independently scoped | Logs/events/artifacts/previews reference parent job IDs | IDOR through child-resource routes | Authorize parent in tenant scope before every child lookup |
| Worker identity has no tenant grant | Registry is global worker ID/capabilities | Worker may claim work outside account scope | Server-managed worker grants, lease claims and revocation |
| Owner-centric local resources | Local projects, Terminal and document grants use Owner flows | Unsafe blanket expansion | Separate local-owner capabilities from member app usage |
| Deployment-specific OIDC | Configuration and edge required; production wiring unproven | Login assumptions may be false | Deployment acceptance with real test identities and revocation |

## 7. Required UB-01/UB-02 design before code

1. Principal key: immutable local `principal_id` mapped to verified `iss + sub`; email is profile metadata only.
2. Personal tenant: provision exactly one personal tenant per principal on first successful admission, idempotently.
3. Organization tenants: explicit, revocable membership; no membership inferred from email domain.
4. Role/capability: default least-privilege `member`; tenant admin is tenant-local; DCP Owner/platform-admin remain separate global privileges.
5. Request context: derive principal, tenant, membership and application grant server-side from a validated session; body/query tenant values are selectors only.
6. Resource policy: every list/get/update/cancel/resume/log/event/artifact/preview route must use a shared authorization helper and tenant-scoped query.
7. Worker policy: workers authenticate with worker credentials and receive server-assigned tenant/capability grants; job payload cannot widen worker scope.
8. Migration: inspect and back up stores; add nullable ownership columns; classify records without authoritative ownership as `legacy_unassigned`; never guess an owner; keep them inaccessible to ordinary members until audited reconciliation.
9. Compatibility: preserve current Owner/Operator paths during migration; introduce Member access as a separate capability path with explicit tests.
10. Tests: positive same-tenant access plus negative cross-tenant tests for every resource/route, including IDOR, pagination, idempotency replay, worker claims, artifact downloads, previews and revocation.

## 8. Next work sequence

- **UB-00 (this checkpoint):** source and route/resource inventory — IN_PROGRESS. Remaining: full Local Auth Proxy/session flow trace, complete store schemas for every resource family, test function/fixture/skip mapping and reconciliation with all open PR dependencies.
- **UB-01:** principal/account/tenant data model and OIDC admission design. No implementation until UB-00 ownership and persistence inventory is closed.
- **UB-02:** shared authorization context and resource scoping; additive migration and cross-tenant tests.
- **UB-03:** worker tenant grants, scoped job leases and artifact/preview lifecycle.
- **UB-04+:** application adapters and provider routing after DCP contracts are stable.

## 9. Safety and non-claims

- No runtime source, database schema, credentials, role assignment, provider setting or production deployment was changed by this checkpoint.
- No cloud resource, paid service, OIDC application registration or secret was created.
- This document does not authorize merge, account role escalation, Terminal enablement, provider activation or deployment.
- Existing data must be preserved. Unknown ownership is not assigned to the first user or to the current repository owner.
- Hosted CI results are recorded only for the exact PR head; skipped/unknown checks are not PASS.


## 10. Relevant automated-test map (source inventory, not execution results)

The following test functions exist on the audited main baseline. Their presence does not prove the tests have passed on the current PR head, and none of these suites currently establishes tenant isolation.

| Test module | Relevant observed tests | What is covered | UB gap |
|---|---|---|---|
| `tests/test_cloud_gateway_oidc_session_store.py` | transaction browser binding/one-time use; expiry; session lookup/CSRF/rotation/logout; connection close; expired session; rejection of unverified role/invalid subject | OIDC transaction/session mechanics and role allowlist | Add member admission, principal mapping, tenant membership, membership revocation and session-to-tenant context tests |
| `tests/test_cloud_gateway_oidc_auth_service.py` | login callback + PKCE; browser-bound state; secure cookie/logout; session rotation | Provider-neutral OIDC callback and session lifecycle | Current service constructor requires Owner and Operator groups; no group-less member provisioning test |
| `tests/test_cloud_gateway_proxy_authorization.py` | Operator can read session but cannot create Runner; Operator cannot terminate Runner; unsupported HTTP methods are not dispatched | Sample Owner/Operator privilege boundaries | No normal Member identity or cross-tenant resource tests |
| `tests/test_cloud_gateway_job_control.py` | idempotent create/conflict; claims/lease fencing; cancellation; checkpoints; resume; concurrent workers; worker ownership | Durable job lifecycle and worker/lease invariants | No principal/tenant scoping, cross-account idempotency, or cross-tenant job/log/event tests |
| `tests/test_cloud_gateway_runner_registry.py` | register/heartbeat/drain/enable; capabilities; stale/offline worker; invalid capabilities; capability-aware claims | Global worker registration and capability matching | No worker-to-tenant grants, tenant-bound claims or revocation tests |
| `tests/test_cloud_gateway_artifacts.py` | immutable hash metadata; upload validation; truncated upload; invalid ID; tamper rejection | Artifact integrity and worker ownership/lease validation | No tenant-scoped artifact list/download or parent-job authorization test |
| `tests/test_local_auth_proxy.py` | full local login/Gateway/logout; CSRF/origin; unknown route denial; Owner-only Recon; protected Runner credential file | Single local Owner Proxy flow and security controls | No multiple-account sessions; optional Chromium/Firefox/WebKit tests are guarded by environment availability |

The browser tests in `test_local_auth_proxy.py` use `skipUnless` guards for Chromium, Firefox and WebKit prerequisites. A skipped browser test is not an acceptance pass. Target-host Windows PSEC acceptance remains separately blocked/unknown as recorded in the current implementation status.

## 11. Open-PR dependency reconciliation (live metadata snapshot)

| PR | Current branch/base relation | State | UB-00 disposition |
|---|---|---|---|
| #149 Windows PSEC trusted runtime | Base `eaa9ceb...`, 2 commits behind current main; `mergeable=false` | OPEN / DRAFT | Separate Terminal/host-acceptance work; do not use hosted probe as target-host PASS or merge into UB work |
| #150 2026-11-19 repository audit | Base `eaa9ceb...`, 2 commits behind; `mergeable=false` | OPEN / DRAFT | Historical audit candidate; current main already has newer 2026-11-23 audit docs, so do not copy its old counts as current |
| #151 Dashboard Code Navigator | Base `c17b2db...`, 1 commit behind current main; `mergeable=true` | OPEN / DRAFT | Independent Dashboard mapping change; no dependency for identity or tenant model |
| #152 trusted repository bootstrap | Base `eaa9ceb...`, 2 commits behind; `mergeable=false` | OPEN / DRAFT | Separate Runner credential/allowlist hardening; review and rebase dependency must be resolved by its workstream owner |
| #138 cross-fork PSEC comparison | Fork branch and feature-branch base; `mergeable=false` | OPEN | Do not merge wholesale; unrelated to Unified Backend foundation |
| #155 Unified Backend | Base is exact current main `5758987...`; `mergeable=true` at last metadata refresh | OPEN / DRAFT | Current architecture/audit work; exact-head CI must be refreshed after every branch commit |

This register is a point-in-time snapshot and must be refreshed before any merge or dependency decision. No PR was merged, closed or retargeted by this audit.

## 12. UB-00 completion checklist

- [x] Reconcile current main SHA against the 2026-11-23 audit baseline.
- [x] Trace Gateway identity role admission and OIDC session role constraints.
- [x] Trace the local Owner Auth Proxy and distinguish it from OIDC deployment components.
- [x] Inspect JobStore, RunnerStore, RunnerRegistry, ArtifactStore and ProviderRouter ownership keys.
- [x] Map current Gateway route families to the multi-account isolation requirements.
- [x] Identify relevant existing OIDC/job/runner/artifact tests and optional browser skips.
- [x] Refresh the open-PR dependency snapshot.
- [ ] Complete every persistent store schema and all Local Auth Proxy route/session branches.
- [ ] Complete all 117 test-path files' function/fixture/skip/workflow mapping; current table is targeted, not exhaustive.
- [ ] Reconcile application-level DCP integrations and service identity contracts.
- [ ] Independent review of the ownership matrix and migration classification.

**UB-00 remains IN_PROGRESS.** UB-01 implementation must not begin until the remaining unchecked items are closed or explicitly deferred with a documented reason and owner decision.


## 13. Application integration baseline (current source snapshots)

These are source-level integration observations, not claims that any application is already connected to DCP.

### 13.1 Research OS — existing per-user identity and owner-scoped jobs

**Repository:** `phakphum12345/Drive-letter`  
**Branch:** `main`  
**Inspected head:** `06989393619e56b074dcb73a8806749ec62fd84c`

- `GoogleIdentityBroker` verifies a Google subject and verified email before issuing a Research OS session. `auth_session.py` signs a short-lived session containing `user_id`, email, role and session ID; revocation markers are stored per user.
- `identity_context.py` derives Friend/profile scope from the verified session, not client-provided scope headers.
- `CloudLocalHTTP` derives the owner scope from the authenticated session's `user_id`; it does not accept the request body as authority for the principal.
- `CloudLocalStore` is already owner-scoped: jobs use primary key `(owner_id, job_id)` and unique `(owner_id, idempotency_key)`; agents/evidence/checkpoints are also scoped by owner ID.
- Cloud mode explicitly requires `RESEARCH_OS_DATABASE_URL` to point to PostgreSQL; ephemeral SQLite fallback is disabled in cloud mode. SQLite remains available for local development/tests.
- Research OS has its own provider interface and canonical Friend Resource Control boundary. Its installed Windows Local Mode selects Ollama (default model `llama3.2:3b`); Render Cloud Mode selects Gemini. The Friend runtime includes provider settings, readiness, usage/cost accounting and a per-owner ResourceControlPlane. The API's `RESEARCH_OS_AI_ROUTE` defaults to `friend`; the direct-provider path is explicitly disabled. DCP must not bypass Friend to call Ollama/Gemini directly or duplicate its AI budget/policy logic.
- The inspected API sets `FRIEND_OWNER_ID` default to `owner` and derives a per-user profile ID from the Research OS session. Friend routes default to `owner_only=True`, while only selected routes opt out. Therefore a DCP `member` must not be mapped to a Friend Owner identity; a tenant-aware Friend authorization/service-identity contract is needed before general Research OS accounts can use Owner-only Friend capabilities.
- DCP should orchestrate only the eligible compute/build/test jobs delegated by Research OS and preserve Research OS's provider/resource-control boundary, identity/session storage and research-domain records.

**Integration gap:** Research OS currently identifies Google users by a provider subject/user ID, but the inspected session context does not carry a verified OIDC issuer claim for a DCP `iss + sub` principal mapping. A future adapter must obtain/verify a DCP-audience service assertion or use a shared verified identity exchange; never trust a browser-supplied `user_id`, `owner_id` or role header.

### 13.2 Virtual Cloud Control Center — desktop client and GitHub Actions dispatch

**Repository:** `phakphum12345/VirtualCloud-ControlCenter`  
**Branch:** `feature/virtual-cloud-control-center`  
**Inspected head:** `0a3915bbe51fe703c504c2c75734cb464862b7f2`

- The README describes a Windows-first desktop Control Center that dispatches GitHub Actions workflows for Windows/macOS runners and separately synchronizes artifacts/logs/metadata to Google Drive.
- `virtual-cloud-runners.yml` uses manual `workflow_dispatch`, supports Windows/macOS targets, optional source repository/ref and an explicit no-op smoke-test input. The build hook is required unless the no-op flag is explicitly enabled.
- Google Drive OAuth credentials are held in the local application-data area; the desktop application also has an explicitly confirmed, narrowly scoped `MULTI_REPO_TOKEN` secret configuration action.
- No DCP API/job adapter was identified in the inspected README, runner workflow or controller entrypoint. The current desktop client therefore remains a separate dispatch client, not a DCP-integrated tenant-aware control client.

**Integration direction:** route eligible compute/build requests through DCP's authenticated Job API and provider capability policy; retain the Control Center UI, local Drive OAuth and checksum/receipt synchronization as separate client/storage responsibilities. Do not let a client-supplied repository/ref or GitHub token bypass DCP allowlists, owner approval or worker policy.

### 13.3 phakphum-calendar — Flutter client; cloud domain API remains unverified

**Repository:** `phakphum12345/phakphum-calendar`  
**Branch:** `main`  
**Inspected head:** `7ae6b3020c0cc331e2ab730591df44646b0ef530`

- Current README describes a Flutter app for roster import/review and guarded Google Calendar synchronization.
- `pubspec.yaml` declares Flutter/Dart dependencies including Google Sign-In and Google APIs.
- `GoogleAuthService` currently requests read-only scopes for Sheets, Calendar events and Drive metadata/files. It is a client-side Google identity/API workflow, not proof of a DCP service identity or a multi-tenant server API.
- At this baseline, root `composer.json` and `routes/api.php` are not present at the expected paths, and code search did not find Laravel route/controller/schema markers such as `Route::middleware`, `Schema::create`, `shift_transactions` or `artisan`. This is a bounded inspection, not proof that no backend exists in another repository or deployment.

**Architecture correction:** do not claim an existing Laravel Calendar API/database as verified. The selected Cloud operating mode remains a target decision, but a dedicated Calendar domain API, identity binding, tenant-aware storage, migration and deployment must first be located or designed. Shift rosters, swaps, approvals and Google Calendar synchronization must remain Calendar-domain responsibilities; DCP may provide shared identity/job execution contracts but must not become the shift transaction database.

### 13.4 Cross-application boundary decision

- DCP owns shared principal mapping, tenant membership, capability authorization, jobs, runner leases and execution evidence.
- Research OS retains its owner-scoped CloudLocal store and AI/provider domain.
- Virtual Cloud Control Center remains a desktop client; DCP becomes the job/runner authority after an explicit adapter is implemented.
- Calendar requires its own verified cloud domain API/storage before Cloud mode can be called operational.
- Do not consolidate these databases. Use versioned contracts, signed service assertions, correlation IDs and scoped service identities.


## 14. Additional persistent-store schema review

The following stores were inspected on the same DCP main baseline. Their current keys reinforce why a broad role change is unsafe.

| Store | Current key/ownership shape | Required future boundary |
|---|---|---|
| `InfrastructureStore` (`infrastructure.py`) | `infrastructure_resources.id` primary key; global unique `idempotency_key`; audit by resource ID | Keep platform provisioning owner-approved. If tenant-funded resources are ever supported, add explicit tenant budget/approval ownership before any member access |
| `InfrastructureGateStore` | Global `gate` primary key; audit records actor but no tenant | Platform-global gates remain Owner/platform-admin only; tenant admins cannot enable them |
| `TerminalGrantStore` | Grant ID primary key; subject/session/project/workspace/template/job/worker fields; unique job ID; no tenant key | Preserve Owner approval and OS isolation. Bind grant to authorized tenant/project only after parent ownership is implemented |
| `TerminalTemplateStore` | Template ID primary key; creator and audit actor; no tenant key | Keep imported template review platform-controlled unless a separate tenant template namespace is designed |
| `DocumentWorkflowStore` | Grant/proposal IDs; project ID; actor; globally unique idempotency key; no tenant key | Scope project grant, proposal, approval and idempotency to the authorized tenant/project; retain exact path-prefix grants |
| `LocalProjectRegistry` | Local JSON registry under per-user local application data; project IDs and enrolled roots, not a server tenant registry | Keep host paths local and owner-controlled; never let remote members submit arbitrary paths or inherit another local user's workspace |
| `AuthenticatedPreviewManager` | In-memory runtime-token/job maps; operations accept runtime ID + parent job ID | Resolve and authorize the parent job in tenant scope before preview start/status/content/stop; runtime token never leaves Gateway |

These resources fall into two categories and must not be conflated:

1. **Tenant-owned application resources:** jobs, their events/logs/checkpoints/artifacts/previews, and explicitly granted projects. These need tenant/principal scoping.
2. **Platform-global privileged controls:** infrastructure gates, provider provisioning, global templates and host-local enrollment. These should remain restricted to platform Owner/admin until a separate, reviewed delegated-administration model exists.

A tenant role must never become a shortcut to platform provisioning, local filesystem access, Terminal execution, or global provider configuration.


## 15. Complete test-path inventory and expanded identity/API test review

The recursive Git tree for audited `main` SHA `57589873583c706d4af9756709596fdba7c22de9` contains **116 files under `tests/`**:
- 112 Python test/support modules
- 3 PowerShell test scripts
- 1 JavaScript browser smoke test

This is a complete path inventory for the audited tree, not a claim that all 116 files were read line-by-line or executed during this audit. The targeted identity, job, worker, artifact, preview, infrastructure and document-workflow test modules reviewed in detail include the following additional evidence:

| Test module | Relevant tests / assertions | UB conclusion |
|---|---|---|
| `test_cloud_runner_user_api.py` | signed proxy identity; OIDC Owner group mapping; Viewer rejection; dashboard Job create/list/get/cancel role guards; worker-only identity; worker ownership/fencing; artifact upload/download | Current API has signed identity and role checks, but no personal tenant/member or cross-tenant assertions |
| `test_cloud_runner_openapi.py` | bearer-auth lifecycle; three platform contract; owner-only local project API; installation membership/idempotency/billing/teardown contract wording | OpenAPI contract is not a tenant ownership implementation |
| `test_cloud_runner_e2e_acceptance.py` | OIDC to budgeted create/status/terminate/cleanup; Orka independent budget; signed assertion replay rejection | Provider lifecycle security is tested; tenant ownership is not |
| `test_cloud_gateway_oidc_ingress_contract.py` | signer private; DCP identity headers overwritten; same-origin/CSRF forwarding | Trusted ingress boundary is tested; it does not provision a member tenant |
| `test_cloud_gateway_oidc_wsgi.py` | HTTPS login, browser binding, secure cookie, session identity/CSRF without tokens, same-origin logout, session rotation | Session mechanics tested; no tenant selection/membership context |
| `test_cloud_gateway_oidc_deployment.py` | durable session DB required; trusted proxy allowlist; distinct explicit Owner/Operator groups; origin/TTL validation | Deployment intentionally requires explicit privileged groups; group-less member admission is not present |
| `test_cloud_gateway_artifact_download.py` | Owner download bytes/hash; unauthenticated and Viewer denial; tamper rejection | Role/integrity gates exist; no parent-job tenant scoping test |
| `test_authenticated_preview.py` | one preview per job; job binding; no runtime capability leakage; Owner approval; server-side capability; traversal rejection | Preview capability protection exists; no cross-tenant parent-job authorization test |
| `test_cloud_gateway_infrastructure_api.py` | Owner create/list/start/stop/delete; Operator delete denial; gates default off; Owner confirmation/CSRF; unauthenticated denial; Terminal remains inert/Owner-reviewed | Platform infrastructure and Terminal controls must remain privileged, not exposed through general Member role |
| `test_cloud_gateway_infrastructure_gates.py` | gates off by default; exact confirmation; independent switches; persistent audit; actor validation | Platform-global gate semantics should remain Owner-only |
| `test_cloud_gateway_runner_terminal_grant.py` | job-bound grant; one-time consumption; wrong job/runner credential/lease rejection | Worker grant is job/worker-bound but not tenant-bound |
| `test_document_workflow_gateway.py` | Owner grant required; exact directory scope; revocation; exact digest approval; traversal rejection; idempotency payload conflict | Good path/digest safety; project grants and idempotency still need tenant/project scope |
| `test_local_auth_proxy_project_routes.py` | strict project/artifact/job read allowlist; session/CSRF on mutations; resume/cancel/infrastructure/Terminal route guards | Local Proxy is a separate Owner session boundary, not multi-account admission |

No reviewed test module demonstrates a full **two-principal / two-tenant negative matrix** for DCP jobs, child resources, artifacts, previews, runner claims and idempotency. This is the central test gap that UB-02 must close.

## 16. Exact-head CI interpretation for PR #155

At the latest observed PR snapshot:
- PR #155 head: `33a67e471361c419c2b9829f55672d080db8d7b3`
- Base: `57589873583c706d4af9756709596fdba7c22de9`
- Validate Control Plane workflow: **SUCCESS**
  - `validate`: SUCCESS
  - Windows dynamic-port launcher integration: SUCCESS
  - Windows runner acceptance matrix: SKIPPED
- Local-first Minimal Emulator: **SUCCESS**
  - Linux Minimal Emulator: SUCCESS
  - Windows 11 local Auth Proxy + Gateway end-to-end: SUCCESS
- Cross-platform Recovery Acceptance: **SUCCESS**
  - Ubuntu: SUCCESS
  - Windows: SUCCESS

The skipped Windows runner acceptance matrix is deliberately gated in `.github/workflows/validate-control-plane.yml`: it runs only on `workflow_dispatch` when input `run_self_hosted_windows_acceptance=true`; the default is false. It targets two specifically labelled self-hosted Windows runners. Therefore:
- The PR did pass Windows-hosted GitHub Actions jobs (Windows launcher integration, Windows Local Auth Proxy/Gateway E2E, and Windows recovery).
- It did **not** execute the separately gated self-hosted local-runner acceptance matrix.
- Do not report the whole PR as having no Windows coverage; equally, do not report the self-hosted acceptance as passed.

These CI results apply only to the exact PR head above. Any new commit invalidates this snapshot and requires fresh exact-head results.

## 17. Revised UB-00 exit criteria

- [x] Reconcile audited main baseline and current PR base/head.
- [x] Inventory all 116 test/support paths under `tests/`.
- [x] Inspect core OIDC/session, job, runner, artifact, preview, infrastructure, Terminal and Document Workflow test modules.
- [x] Record current exact-head Linux and Windows-hosted CI outcomes and explain the intentionally skipped self-hosted runner matrix.
- [x] Distinguish existing identity/role/worker security tests from missing tenant-isolation tests.
- [ ] Complete Local Auth Proxy route/session flow mapping, including every route allowlist and mutation boundary.
- [ ] Finish persistent-store schema inventory for all remaining stores and identify which are platform-global versus tenant-owned.
- [ ] Complete test fixture/skip/workflow mapping for remaining modules relevant to shared API contracts and application integration.
- [ ] Independently review the principal/tenant/resource ownership matrix and legacy record classification.
- [ ] Refresh open PR/dependency state before UB-00 closure.

**UB-00 remains IN_PROGRESS.** The 116-path inventory and expanded critical-suite review are complete, but the remaining route/store/dependency checks must be closed before UB-01 implementation. No runtime or database change is authorized by this audit.
