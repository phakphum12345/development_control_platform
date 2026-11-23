# WP-01 — Gateway and Local Auth Proxy API Security Acceptance

**Repository:** `phakphum12345/development_control_platform`  
**Audit baseline:** `main` at `eaa9ceb91088c39b90d9b11b3817dc793e40005a`  
**Audit branch:** `docs/wp00-live-audit-20261123`  
**Status:** IN_PROGRESS — source and representative test trace only; no full acceptance claim  
**Scope:** WP-01 items that can be grounded in the current Gateway and Local Auth Proxy implementation. This document is a navigation and test plan; it does not change runtime behavior.

## 1. Acceptance state vocabulary

- **IMPLEMENTED / TESTED:** source behavior and a named automated test are both identified; this is not a claim that every CI job or host environment has passed.
- **IMPLEMENTED / TEST GAP:** source behavior is visible but a focused negative/positive test is not yet mapped.
- **PARTIAL:** only a portion of the required contract is evidenced.
- **UNKNOWN:** not established by inspected source or execution evidence.
- **BLOCKED:** acceptance depends on a missing capability or required environment.

## 2. Atomic acceptance register

| ID | Acceptance requirement | Source anchor (main baseline) | Existing test anchor | State / remaining evidence |
|---|---|---|---|---|
| WP01-API-001 | Gateway health endpoint returns bounded status only and does not expose credentials | `tools/cloud_gateway/server.py` `make_handler/do_GET`, `/healthz` (around L329–347) | Gateway health tests must be mapped from full test census | PARTIAL — verify exact payload and unauthenticated exposure is intentional |
| WP01-API-002 | Dashboard identity must be a valid signed Proxy assertion; invalid/missing identity denied | `server.py` `ProxyIdentityVerifier`, `proxy_identity`, `do_GET/POST/DELETE` | `tests/test_cloud_gateway_proxy_authorization.py`; `tests/test_local_auth_proxy.py` | IMPLEMENTED / TESTED for sampled authorization boundaries; exhaustive replay/expiry/nonce matrix open |
| WP01-API-003 | Gateway mutations require same-origin and valid CSRF where browser identity is used | `server.py` `same_origin`, `csrf_valid`, mutation handlers | `tests/test_cloud_gateway_proxy_authorization.py`; `tests/test_local_auth_proxy_project_routes.py` | IMPLEMENTED / TESTED for representative routes; route-by-route completeness open |
| WP01-API-004 | Gateway body parser rejects invalid length, oversized bodies, invalid UTF-8/JSON and non-object JSON | `server.py` `Handler.body(max_bytes=32768)` | Focused body-boundary test functions not yet individually mapped | IMPLEMENTED / TEST GAP |
| WP01-API-005 | Role boundaries are explicit for owner/operator and runner identities | `server.py` `do_GET/POST/DELETE`; role checks on recon, Terminal, Jobs, infrastructure, cloud runners | `tests/test_cloud_gateway_proxy_authorization.py` | IMPLEMENTED / TESTED for operator-vs-owner Cloud Runner mutation; full endpoint/role matrix open |
| WP01-API-006 | Dashboard Proxy exposes only allowlisted GET routes and bounded query forms | `tools/local_auth_proxy.py` `ALLOWED_GET`, `Handler.do_GET` (around L595–679) | `tests/test_local_auth_proxy_project_routes.py` tests for bounded reads and unapproved paths/query | IMPLEMENTED / TESTED for sampled route/query cases; exhaustive path encoding/duplicate query matrix open |
| WP01-API-007 | Proxy POST routes require same-origin, correct pre-auth or authenticated session, and CSRF | `local_auth_proxy.py` `do_POST` (around L681–873) | `tests/test_local_auth_proxy.py`; `tests/test_local_auth_proxy_project_routes.py` | IMPLEMENTED / TESTED for login/session/mutation cases; route-by-route payload and role parity open |
| WP01-API-008 | Proxy DELETE accepts only exact preview/infrastructure/cloud-runner patterns and requires session + CSRF | `local_auth_proxy.py` `do_DELETE` (around L874–910) | `tests/test_local_auth_proxy_project_routes.py` preview/infrastructure route tests | PARTIAL — cloud-runner and malformed-identifier/query boundary coverage needs explicit mapping |
| WP01-API-009 | Proxy OPTIONS is denied; unsupported HTTP verbs fail closed | `local_auth_proxy.py` `do_OPTIONS` (L911–912); no explicit do_PUT/do_PATCH handler observed | No explicit PUT/PATCH/OPTIONS negative-test anchor identified in inspected suites | IMPLEMENTED / TEST GAP — characterize BaseHTTPRequestHandler behavior with tests; do not assume 404/405 semantics |
| WP01-API-010 | Gateway unsupported HTTP verbs fail closed with documented response semantics | Gateway explicitly defines GET, POST, DELETE handlers in `make_handler`; no explicit PUT/PATCH/OPTIONS handler observed | No explicit unsupported-verb tests identified | IMPLEMENTED / TEST GAP — test actual status/connection behavior for PUT/PATCH/OPTIONS |
| WP01-API-011 | Idempotency keys are syntactically bounded and scope mutation replay/conflict safely | `server.py` Terminal Jobs, Jobs/Cloud Runner/Infrastructure create handlers; Proxy forwards selected keys | `tests/test_local_auth_proxy_project_routes.py::test_forwards_cloud_runner_create_idempotency_key`; Gateway/Job store idempotency tests require full mapping | PARTIAL — per-route minimum length, scope, retention, conflict and concurrent replay matrix open |
| WP01-API-012 | Sensitive responses are non-cacheable and errors do not disclose secrets or internal traces | Gateway `send_json`; Proxy `send_bytes`; exception handlers | Representative Proxy/Gateway tests; response-header/error tests not fully mapped | PARTIAL — assert headers and sanitize every exception path |
| WP01-API-013 | Proxy/Gateway route parity is intentional: every browser-facing mutation forwarded by Proxy is accepted by Gateway with compatible authorization | `local_auth_proxy.py` POST/DELETE allowlists; `server.py` GET/POST/DELETE handlers | `tests/test_local_auth_proxy_project_routes.py` | PARTIAL — exhaustive machine-readable route parity table not yet generated |
| WP01-API-014 | Query strings are rejected or parsed by strict per-route schemas; path decoding cannot bypass route allowlists | Proxy query checks and regex routes; Gateway uses `urlparse`, `parse_qs`, `unquote` | Project route tests cover representative unapproved path/query inputs | PARTIAL — duplicate keys, encoded slash/dot, blank values, parameter order and Unicode cases remain |
| WP01-API-015 | Authentication, authorization and request parsing failures return consistent documented status codes | Gateway/Proxy handler branches | Existing tests assert selected 401/403/404/409 cases | PARTIAL — publish full response contract and add negative matrix |
| WP01-API-016 | Runner service credentials are separate from Dashboard Proxy identity and bound to registered worker identity | `server.py` runner token validation, `runner_identity`, `/v1/runner/*` handlers | Runner registration/claim/heartbeat/lease tests; exact function map remains | PARTIAL — full worker token rotation/revocation/replay and cross-worker denial trace open |

## 3. Observed route families

### Gateway — source-level handler families

- **GET:** health; Recon; Document Workflow grants/target/proposal; Local Projects/roots; Terminal templates/events; Jobs/checkpoints/logs/events/previews; Runners; Infrastructure/gates/resources; Artifact download; Runner v1 job state; owner session; GitHub repositories/refs/commit/project; Cloud Runner status/list/detail.
- **POST:** Terminal job create, grant revoke/authorize/review/import/command preview; Infrastructure create/lifecycle/gates; Jobs create/resume/cancel/preview start; Runner enrollment/register/ping/claim/heartbeat/checkpoint/logs/artifacts/finish/Terminal grant; Runner control; Cloud Runner create; v1 runner create.
- **DELETE:** preview stop; Infrastructure resource delete; Cloud Runner terminate; v1 runner terminate.
- **Other verbs:** no explicit Gateway `do_PUT`, `do_PATCH` or `do_OPTIONS` implementation was found in the inspected handler.

### Local Auth Proxy — browser-facing handler families

- **GET:** health, auth session, bounded preview routes, explicit `ALLOWED_GET` routes, exact-pattern job/log/artifact/GitHub/infrastructure/Terminal/local-project reads and Recon prefix; authenticated session required for `/api/*`.
- **POST:** pre-auth login; authenticated logout; Jobs create/resume/cancel/preview; Infrastructure gates and lifecycle; Cloud Runner create; Terminal import/review/command preview; Runner drain/enable.
- **DELETE:** preview stop; exact UUID Infrastructure delete; Cloud Runner resource delete.
- **OPTIONS:** explicit 405.
- **Other verbs:** no explicit `do_PUT` or `do_PATCH` handler was found.

This is a source-family summary, not a claim that all individual URL patterns, body schemas or authorization predicates have been exhaustively enumerated.

## 4. Existing test anchors inspected

- `tests/test_cloud_gateway_proxy_authorization.py::ProxyMutationAuthorizationTests.test_operator_can_read_session_but_cannot_create_runner`
- `tests/test_cloud_gateway_proxy_authorization.py::ProxyMutationAuthorizationTests.test_operator_cannot_terminate_runner`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_allows_only_project_collection_root_and_uuid_reads`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_rejects_unapproved_project_api_paths`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_rejects_unbounded_or_unapproved_dashboard_read_routes`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_local_runner_controls_require_session_csrf_and_empty_payload`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_forwards_cloud_runner_create_idempotency_key`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_unknown_job_resume_requires_session_csrf_and_exact_route`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_job_cancellation_requires_session_csrf_and_exact_empty_request`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_terminal_studio_mutations_require_session_csrf_and_exact_routes`
- `tests/test_local_auth_proxy_project_routes.py::LocalProjectProxyRouteTests.test_infrastructure_mutations_require_session_csrf_and_exact_routes`

The list above is deliberately limited to test functions directly observed in the inspected source. It is not the full test suite.

## 5. WP-01 execution plan

1. Build a complete Gateway route matrix: method, literal/regex path, query schema, body schema/size, auth principal, role, same-origin, CSRF, idempotency, service call, response status.
2. Build the same matrix for Local Auth Proxy and compare forwarded routes against Gateway accepted routes.
3. Add negative tests for unsupported verbs, query duplicates/order/blank values, percent-encoded path separators and dot segments, malformed UUID/worker identifiers, content-length edge cases, invalid UTF-8/JSON and non-object bodies.
4. Add table-driven authorization tests for anonymous, expired/invalid/replayed proxy identity, owner, operator, runner credential, wrong worker, missing/invalid CSRF and wrong Origin.
5. Add idempotency tests for missing/invalid/duplicate/conflicting keys, concurrent duplicate requests, scope isolation and store restart behavior.
6. Assert security headers and ensure all unexpected exceptions return sanitized errors without logging credentials, cookies, request paths or user IDs.
7. Run targeted tests, full Python unittest discovery, browser tests, and exact-head PR workflows. Record skipped tests separately.
8. Close WP01 only after independent review confirms the full route matrix is complete and all required checks pass.

## 6. Explicit non-claims and safety

- Source presence and representative tests do not establish full API security acceptance.
- A successful hosted CI run is not target-user Windows acceptance.
- The self-hosted Windows acceptance job being skipped is not PASS.
- No route was changed in this WP-01 documentation pass.
- Do not enable Terminal templates, provision infrastructure, merge, deploy or release as part of this work.

## WP-01A — Source-derived HTTP dispatch inventory (2026-11-23)

This inventory is a static source review of the current `main` versions of:
- `tools/cloud_gateway/server.py` (blob `9a55bccf216cff1b934bebd643e68364305449aa`)
- `tools/local_auth_proxy.py` (blob `2d8708216f85c28e70f358c0672152353c6b59bc`)

It records explicit handler dispatch observed in source. It is not a runtime proof that every route is secure, reachable, or correctly authorized. The branch-specific acceptance status remains **IN PROGRESS**.

### HTTP method surface

| Component | Explicit handler methods | Source anchors | Static observation |
|---|---|---|---|
| Cloud Gateway | GET, POST, DELETE | `Handler.do_GET` line 329; `do_POST` line 869; `do_DELETE` line 1623 | No explicit PUT, PATCH, or OPTIONS handler found in this class |
| Local Auth Proxy | GET, POST, DELETE, OPTIONS | `Handler.do_GET` line 517; `do_POST` line 681; `do_DELETE` line 874; `do_OPTIONS` line 911 | OPTIONS is explicitly handled; unsupported verbs have no explicit handler in this class |

The absence of a custom method handler is not, by itself, proof of the externally observed status code. WP-01 tests must assert status, headers, and absence of side effects for unsupported verbs.

### Cloud Gateway GET dispatch families

Observed in `do_GET` (starting line 329):
- `/healthz` (line 344)
- `/api/recon/…` (line 331)
- Document Workflow grants/target and proposal matching (lines 352–366)
- Local Projects collection, roots, and descendants (lines 376–394)
- Terminal templates (line 426)
- Jobs collection, UUID job detail, logs, and preview collection (lines 442–476)
- Runners collection (line 538)
- Infrastructure gates and collection/descendants (lines 546–566)
- Artifact download suffix route (line 588)
- Runner protocol `/v1/runner/…` (line 618)
- General API dispatch includes auth session, GitHub repositories/refs, and Cloud Runner status/collection/descendants (lines 657–735)

### Cloud Gateway POST dispatch families

Observed in `do_POST` (starting line 869):
- Terminal jobs, authorization, templates import, and command preview (lines 871, 992, 1148, 1169)
- Document Workflow grants and proposals (lines 1017–1021)
- Infrastructure collection and gate mutation (lines 1086, 1209–1223)
- Jobs collection, preview creation, local-folder/repository job creation, and unknown-job resume (lines 1257–1388)
- Runner register/enroll, ping, claim, and worker protocol routes (lines 1407–1533)
- Cloud Runner/provisioning and related API dispatch (lines 1547–1613)

### Cloud Gateway DELETE dispatch families

Observed in `do_DELETE` (starting line 1623):
- Exact UUID job-preview stop route (line 1625)
- Infrastructure descendant deletion (line 1644)
- Cloud Runner descendant deletion (line 1667)

### Local Auth Proxy GET allowlist families

Observed in `do_GET` (starting line 517):
- Health and authenticated session endpoints (lines 520–523)
- Job preview listing (line 535)
- Explicit API read allowlist predicates for GitHub repository/refs, jobs collection/detail/logs, artifact downloads, terminal events, infrastructure resources, and Cloud Runner descendants (lines 595–655)
- Dashboard/static asset serving follows the API dispatch section (line 666)

### Local Auth Proxy POST dispatch families

Observed in `do_POST` (starting line 681):
- Login/logout (lines 689–715)
- Job creation, resume, cancellation, and preview start (lines 726–765)
- Cloud Runner mutations (line 807)
- Terminal template import and command preview (lines 821–822)
- Infrastructure mutation dispatch (line 842)

### Local Auth Proxy DELETE and OPTIONS

Observed in `do_DELETE` (starting line 874):
- Job preview stop and explicitly scoped infrastructure/Cloud Runner delete forwarding (lines 890–908)

Observed in `do_OPTIONS` (starting line 911):
- Explicit OPTIONS handler exists. Its response contract and CORS/header behavior still require dedicated positive and negative assertions.

### WP-01A remaining verification work

1. Convert each dispatch family above into a machine-readable route/method inventory with exact path matcher, identity role, CSRF requirement, body schema/size bound, idempotency behavior, and expected status.
2. Exercise every allowed Proxy GET route and reject near-miss paths, query variants, traversal/encoded separators, and unbounded identifiers.
3. Exercise every Proxy POST/DELETE route with missing, invalid, expired, and cross-session credentials; assert no Gateway side effect.
4. Assert OPTIONS preflight headers and unsupported PUT/PATCH behavior at both Proxy and Gateway boundaries.
5. Test Gateway direct access separately from Proxy-mediated access so Proxy controls are not mistaken for Gateway controls.
6. Tie every inventory row to at least one positive test and one relevant negative test before marking the corresponding WP-01 requirement accepted.

**Status: IN PROGRESS.** This source inventory does not close WP-01 and does not authorize merge, deployment, or production activation.
