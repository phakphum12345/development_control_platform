# Unified Backend — All-Account Access and Multi-Tenant Architecture

**Repository:** `phakphum12345/development_control_platform`  
**Branch:** `feat/unified-backend-multi-account-foundation`  
**Baseline:** `main` at `57589873583c706d4af9756709596fdba7c22de9` (2026-11-23)  
**Protocol:** DCP-CEEP v1.0 — adopted  
**Status:** DESIGN / IN_PROGRESS — no runtime behavior is changed by this document.

## 1. Decision and scope

The user has authorized continuous work with **all accounts**. The system must support every eligible authenticated account, not only the original local Owner or members of preconfigured Owner/Operator OIDC groups.

This means:

- An active, verified account can sign in and use the features granted to that account.
- A normal account receives a least-privilege `member` role (or an explicitly assigned application role); it does not need to be an Owner or Operator.
- Administrative and infrastructure capabilities remain restricted to explicitly assigned privileged roles.
- Account eligibility, tenant membership, role assignment, resource ownership and provider policy are checked server-side on every request.
- No account may read, modify, cancel, export or infer another account's private jobs, logs, artifacts, projects, sessions or application records without an explicit authorized sharing/membership rule.

“All accounts” is **not** a request to grant every account administrator privileges, bypass authentication, or expose all tenants to each other.

## 2. Canonical architecture

`phakphum12345/development_control_platform` is the canonical shared **Control Plane and Runner Infrastructure**. It owns identity integration, tenant authorization, policy, job orchestration, runner registration/leases, provider routing and control-plane audit evidence.

It does not replace the application domain APIs or consolidate all application databases.

| System | Role | Selected operating mode | Data ownership |
|---|---|---|---|
| Development Control Platform (DCP) | Shared Control Plane, identity boundary, job/runner orchestration | Local-first control plane; provider-neutral | DCP accounts, memberships, jobs, runners, control-plane audit |
| Research OS (`phakphum12345/Drive-letter`) | Research application and AI orchestration | Hybrid: Local Ollama primary, Cloud Gemini fallback | Research OS domain store and research artifacts |
| Virtual Cloud Control Center (`phakphum12345/VirtualCloud-ControlCenter`) | Cloud control client | Cloud | Its application settings and user workspace; DCP controls runner/job lifecycle |
| phakphum-calendar (`phakphum12345/phakphum-calendar`) | Flutter roster/calendar client; cloud domain API not yet verified | Cloud (target) | Calendar domain API/database must be located or designed; DCP must not own shift transactions |
| Apple/macOS worker | Optional execution provider for eligible macOS workloads | Optional / capability-gated | Job-scoped workspace and artifacts governed by DCP |

The application systems use DCP through versioned, authenticated APIs and narrowly scoped service identities. DCP must not read or write another application's domain database directly. Current-source audit note: Research OS already has per-user owner-scoped CloudLocal storage; Virtual Cloud Control Center is currently a desktop/GitHub Actions client without a DCP adapter identified; phakphum-calendar's Cloud domain API/database is not yet verified. See `docs/UNIFIED-BACKEND-UB00-CURRENT-MAIN-AUDIT.md`.

## 3. Identity and account model

### 3.1 Stable identity

- Use the verified OIDC `iss` + `sub` pair as the external principal key. Email and display name are mutable profile attributes, never ownership keys.
- Store a local immutable `principal_id` mapped to that external identity.
- Require verified issuer, audience, signature, expiry, issue time, state, nonce, PKCE and exact redirect URI at the OIDC boundary.
- Check account active/disabled state and session revocation before issuing the DCP request assertion.
- Do not accept browser-supplied identity, tenant, role or owner identifiers as authority.

### 3.2 Personal and organization tenants

Every principal receives a personal tenant/workspace after first successful account activation. Organization tenants are additional workspaces and require an explicit membership record.

Conceptual entities:

- `principals(principal_id, issuer, subject, status, created_at, updated_at)`
- `tenants(tenant_id, tenant_type, display_name, status, created_at)`, where tenant_type is `personal` or `organization`
- `tenant_memberships(tenant_id, principal_id, role, status, granted_by, created_at, revoked_at)`
- `sessions(session_id_hash, principal_id, expires_at, revoked_at, ...)`
- `application_grants(tenant_id, principal_id, application_id, capabilities, status, ...)`

These are logical entities, not a mandate to introduce a new database product. Select storage only after examining current DCP persistence, backup and transaction boundaries.

A principal may belong to multiple tenants. Every tenant-scoped API request must resolve the selected tenant from a validated server-side session/context and verify active membership. A tenant ID supplied in a URL or body is only a selector; it is never proof of membership.

### 3.3 Role and capability model

Initial least-privilege role vocabulary:

| Role | Intended capabilities |
|---|---|
| `member` | Use own personal tenant and application features explicitly granted to them; create/read/manage own resources |
| `viewer` | Read resources explicitly shared with them; no mutations |
| `operator` | Operate only the tenant/application resources granted by policy; no global ownership |
| `tenant_admin` | Manage membership and tenant settings for their tenant; cannot change global DCP security or billing controls |
| `owner` | DCP deployment owner and explicitly approved global operations |
| `platform_admin` | Optional break-glass/platform administration; separate, audited and not granted by default |

Do not infer `owner` or `platform_admin` from ordinary login. Do not use the current global `owner/operator` group mapping as the only admission gate for normal accounts. Verified users without a privileged group should be provisioned as `member`, subject to account-status and tenant-provisioning policy.

Privileged role assignment must be server-side, auditable, revocable and protected against self-escalation. Organization administrators cannot grant themselves DCP-global privileges.

## 4. Resource isolation contract

Every private DCP resource must be scoped to a tenant and, where relevant, an owning principal:

- Jobs, idempotency records, checkpoints, events, logs, results and cancellation/resume operations.
- Artifacts, previews, preview runtimes and download handles.
- Local project registrations, workspaces, Terminal grants and templates.
- Runner enrollment, worker-to-tenant capability grants and provider execution assignments.
- Infrastructure resources, budgets and provisioning approvals.
- Application grants, service identities, integration tokens and audit events.

Required authorization predicate:

1. Authenticate the principal and active session.
2. Resolve the requested tenant context.
3. Verify active tenant membership and required capability.
4. Load the resource by ID **and** tenant scope (and owner scope when private).
5. Apply resource/action policy.
6. Write an audit event with principal, tenant, application, action, resource, decision and correlation ID; never record secrets.

A missing or mismatched tenant/resource must return a non-enumerating not-found/denial response. Never fetch by resource UUID alone and then rely on the UI to hide unauthorized rows.

### 4.1 Job and idempotency ownership

- Add explicit `tenant_id` and `principal_id` ownership to jobs and related rows.
- Scope idempotency by tenant + principal (and operation/API namespace), not only by a caller-provided key.
- Replaying a key with a different normalized payload returns conflict without exposing the original job.
- Job list, get, events, logs, artifacts, previews, cancel and resume must use the same authorization helper.
- Worker credentials authenticate workers, not human users. A worker may claim only jobs within its server-assigned tenant/capability policy; request payloads cannot widen that scope.
- Preserve the existing lease fencing, checkpoint, retry and cleanup behavior.

### 4.2 Existing data migration

Do not add a non-null tenant column with a guessed default and do not silently assign historical records to the first new user.

Migration must be additive and restart-safe:
1. Back up and inspect existing DCP stores and schemas.
2. Add nullable ownership columns/indexes in a migration that preserves all old rows.
3. Classify legacy rows as `legacy_unassigned` or map them only where authoritative owner evidence exists.
4. Keep unassigned legacy records inaccessible to ordinary members; allow a separately audited Owner-only reconciliation process.
5. Backfill in bounded, idempotent batches with before/after counts and integrity checks.
6. Make tenant ownership mandatory for newly created resources only after all write paths and worker paths are covered.
7. Remove compatibility paths only in a later reviewed migration after evidence proves no legacy consumer remains.

Never delete or rewrite old data to make a migration pass.

## 5. API and service boundaries

Introduce shared, versioned DCP contracts for:

- OIDC principal/session introspection and tenant context.
- Personal tenant provisioning and organization membership.
- Application identity and scoped service-to-service grants.
- Job submission/status/events/logs/artifact references.
- Provider capability discovery, readiness and server-side route selection.
- Audit and evidence correlation.

The browser must never receive DCP internal bearer tokens, HMAC signing secrets, provider credentials, OIDC refresh tokens or worker tokens. Keep the same-origin trusted ingress and CSRF/Origin/replay controls.

Each application integrates through its own adapter:
- Research OS adapter delegates only eligible compute/build/test jobs to DCP. Research OS Friend remains the authority for AI provider selection, Ollama/Gemini readiness, usage/cost and AI policy; DCP must not bypass or duplicate that boundary.
- Virtual Cloud Control Center adapter uses DCP control APIs; it does not duplicate runner authority.
- Calendar adapter may delegate shared identity/job capabilities only after a dedicated cloud domain API and tenant-aware storage are verified or implemented; shifts, swaps, approvals and Google Calendar state remain Calendar-domain responsibilities.
- Provider adapters expose capabilities/readiness and receive only scoped job claims.

## 6. Provider selection and fallback

Provider routing is server-side policy, not a user-supplied arbitrary URL or credential.

- Research OS: Local Ollama first. If local runtime is unavailable or the configured capacity policy is exceeded, surface the defined fallback decision and route to Gemini only when cloud fallback is enabled and the account/application grant permits it.
- Virtual Cloud Control Center: Cloud control plane through DCP. Actual runner execution remains blocked unless provider readiness, budget, owner approval, repository allowlist, cleanup and live acceptance gates pass.
- Calendar: Cloud is the selected target mode, not a verified current deployment; implement/locate a dedicated Calendar domain API first and do not route shift writes through arbitrary compute workers.
- Apple/macOS: optional provider only on an eligible Apple-hosted worker with verified credentials, policy and acceptance. A macOS VM on non-Apple Windows hardware is not a production Apple backend.
- Missing, stale, failed or unknown provider readiness/budget remains blocked. No implicit paid resource creation or cloud activation.

## 7. Current-main findings that drive the work

Inspected source at `57589873583c706d4af9756709596fdba7c22de9`:

1. `tools/cloud_gateway/server.py::ProxyIdentityVerifier.verify` accepts only `owner` and `operator`.
2. `docs/oidc-ingress.md` maps only explicit owner/operator groups; a verified user with no matching group is denied.
3. `tools/cloud_gateway/oidc_session_store.py` constrains session roles to `owner` and `operator`.
4. `tools/local_auth_proxy.py` is a local Owner setup/session model, not a multi-account OIDC tenant service.
5. `tools/cloud_gateway/server.py` Jobs GET paths currently permit owner/operator and call `JobStore.list_recent/get/logs/events` without principal/tenant filtering.
6. `tools/cloud_gateway/job_control.py::JobStore` stores global jobs and globally unique idempotency keys; its schema has no tenant or principal ownership fields.
7. Terminal operations and some administrative routes are explicitly owner-only. These controls must not be relaxed globally; ordinary member capabilities should be added through separate policy paths.
8. DCP includes reusable OIDC client/session/WSGI building blocks, but `docs/oidc-ingress.md` says the WSGI adapter is not mounted by the current local password proxy or a production host. There is no evidence of a configured production OIDC provider or live all-account login.
9. The latest main commit adds HTTP method and Proxy path-canonicalization contract tests; it does not implement multi-account access.

The older 2026-11-23 audit document is a historical inventory at its own baseline. Its stale PR register and baseline SHA must not override the exact main SHA recorded above.

## 8. Work-package plan

| WP | Scope | Required outputs | Gate |
|---|---|---|---|
| UB-00 | Current-main baseline and source/API/test trace | Exact SHA inventory, open PR reconciliation, complete identity/resource route matrix | No implementation until source conflicts are resolved |
| UB-01 | Principal, account and tenant identity | Additive schema/migrations, member admission, personal tenant provisioning, membership/role service | OIDC and account lifecycle tests pass |
| UB-02 | Authorization middleware and resource scoping | Shared policy helper; tenant-scoped list/get/mutate for all DCP resources | Cross-tenant negative tests pass on every route |
| UB-03 | Multi-account jobs and runner authorization | JobStore ownership, tenant/principal idempotency, worker tenant/capability claims, artifact/log isolation | Concurrency, replay, lease and cross-account E2E pass |
| UB-04 | Application integrations | Research OS, Virtual Cloud Control Center and Calendar API adapters/contracts | Contract tests; domain stores remain separate |
| UB-05 | Provider routing | Local Ollama/Gemini policy, Azure/Orka capability routing, optional Apple worker contract | Unknown/unready providers fail closed |
| UB-06 | Production identity and operations | OIDC deployment, key rotation, revocation, backup/restore, monitoring and account lifecycle | Explicit deployment configuration and operational acceptance |
| UB-07 | Full regression and release audit | Exact-SHA CI, migration rollback, multi-tenant security test matrix, docs/evidence | No FAIL/UNKNOWN critical gate; separate merge approval |

## 9. Required acceptance matrix

- First-time verified normal user can sign in and receives exactly one personal tenant.
- Returning user retains the same principal and personal tenant when email/display name changes.
- A user without owner/operator groups is admitted as `member` when account policy permits.
- Disabled, unverified, expired, revoked and wrong-issuer/audience users are denied.
- A user in two tenants can switch only to tenants where active membership exists.
- Tenant A cannot list, read, update, cancel, resume, download or infer Tenant B resources by UUID, query, event, log, preview or artifact endpoint.
- Same idempotency key across different principals/tenants cannot reveal or collide with another account's resource.
- Tenant admin can manage only their tenant; cannot grant global owner/platform-admin.
- Worker A cannot claim or report against jobs outside its assigned tenant/capability scope.
- Revoked membership/session blocks subsequent requests, including already-open browser tabs.
- Legacy unassigned records remain preserved and unavailable to normal members until reconciled.
- Application adapters reject missing tenant context and invalid service grants.
- All mutation paths retain exact Origin, CSRF, idempotency and audit requirements.
- No test requires paid cloud resources; cloud provider activation remains disabled until separately approved.

## 10. Execution and safety rules

- Follow DCP-CEEP v1.0: READ → ANALYZE → MODIFY → TEST → AUDIT → PR → exact-head CI → review → merge gate → post-merge verification.
- Work on dedicated feature branches; keep `main` unchanged.
- Keep changes small and separable. Do not mix multi-account identity with cloud provisioning activation, Terminal sandbox enablement or unrelated WP-18 work.
- Preserve all existing data, APIs and local ports unless a reviewed compatibility plan explicitly changes them.
- No cloud resources, billable services, OIDC tenant registrations, production secrets or deployments are created by this work.
- PRs may be opened as Draft for inspection and CI. Merge, production deployment and role escalation remain separate explicit gates.
- If tests are skipped or unavailable, record SKIPPED/UNKNOWN rather than PASS.

## 11. Current checkpoint

- Branch created from `main`: `feat/unified-backend-multi-account-foundation`.
- Design document is the first deliverable on this branch.
- No application source, schema, account, role, credential, provider or production configuration has been changed.
- No deployment or cloud resource has been created.
- Draft PR #155 is open. UB-00 current-main source audit is recorded in `docs/UNIFIED-BACKEND-UB00-CURRENT-MAIN-AUDIT.md` at source baseline `57589873583c706d4af9756709596fdba7c22de9`. Next: complete Local Auth Proxy/session and remaining store/test trace, reconcile open PR dependencies, then freeze UB-00 before any UB-01 runtime/schema changes.
