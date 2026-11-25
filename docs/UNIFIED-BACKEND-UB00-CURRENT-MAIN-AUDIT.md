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
