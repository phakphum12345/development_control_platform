# WP-01–WP-17 Atomic Acceptance Decomposition (2026-11-25)

**Repository:** `phakphum12345/development_control_platform`  
**Branch:** `docs/wp00-atomic-acceptance-map-20261125`  
**Baseline:** `57589873583c706d4af9756709596fdba7c22de9`  
**Purpose:** WP-00D follow-on. Convert the previously broad WP-01–WP-17 range into auditable acceptance records without inventing subsystem ownership or claiming unverified completion.

## 1. Status semantics

- **CONFIRMED-MAP** — an existing source-driven RQ crosswalk explicitly associates the work package with a requirement group.
- **TRACE-REQUIRED** — a package number exists in the master range, but the current checked-in crosswalk does not yet provide a sufficiently specific, independently verified source/test/workflow/acceptance mapping.
- **PASS** requires source review, automated tests on the exact candidate SHA, required CI, security review where applicable, and operational/target-host evidence where required.
- **PARTIAL** means some implementation or tests exist but one or more acceptance dimensions remain open.
- **BLOCKED** means a dependency, security gate, host proof, reviewer decision, or explicit authorization is outstanding.
- **NOT-STARTED** means no implementation/acceptance evidence was established in this audit.

A package must not be marked PASS solely because a file, class, route, test name, workflow, or historical document exists.

## 2. Atomic package register

| WP | Confirmed scope from current crosswalk | Required acceptance evidence | Initial state |
|---|---|---|---|
| WP-01 | Owner authentication / local proxy identity (RQ-002 association) | Identity/session lifecycle; credential storage; CSRF/origin/replay protections; role enforcement; negative authorization tests; supported Windows Dashboard → Proxy → Gateway E2E | TRACE-REQUIRED |
| WP-02 | Durable Jobs/leases/checkpoints and OIDC/trusted proxy security (RQ-004, RQ-015 associations) | Job state invariants; lease expiry/reclaim; idempotency; checkpoint replay; child-resource authorization; OIDC issuer/audience/signature/expiry/replay/key-rotation tests; restart and corruption recovery | PARTIAL / TRACE-REQUIRED |
| WP-03 | GitHub App catalog/import (RQ-003 association) | Installation/repository/ref authorization; pagination; least privilege; immutable source snapshot; failure/retry behavior; live authorized owner import through Dashboard | TRACE-REQUIRED |
| WP-04 | No unique WP-04 ownership/exit criteria confirmed by the current checked-in crosswalk | Trace exact source modules, routes, schemas, tests, workflows, and historical requirements before assigning scope; do not infer from package number | TRACE-REQUIRED |
| WP-05 | Runner enrollment/claim/heartbeat/cleanup (RQ-005 association) | Enrollment identity; claim authorization; lease fencing; heartbeat expiry; duplicate claim/idempotency; process-tree/workspace cleanup after shutdown and interruption | PARTIAL / TRACE-REQUIRED |
| WP-06 | Trusted repository bootstrap (PR #152) | PowerShell 5.1 replacement/recovery semantics; trusted parent ACL and reparse/race handling; transactional credential/settings writes; failure injection; target Windows evidence | BLOCKED pending PR #152 blockers |
| WP-07 | No unique WP-07 ownership/exit criteria confirmed by the current checked-in crosswalk | Source-driven decomposition required before implementation or status assignment | TRACE-REQUIRED |
| WP-08 | No unique WP-08 ownership/exit criteria confirmed by the current checked-in crosswalk | Source-driven decomposition required before implementation or status assignment | TRACE-REQUIRED |
| WP-09 | No unique WP-09 ownership/exit criteria confirmed by the current checked-in crosswalk | Source-driven decomposition required before implementation or status assignment | TRACE-REQUIRED |
| WP-10 | No unique WP-10 ownership/exit criteria confirmed by the current checked-in crosswalk | Source-driven decomposition required before implementation or status assignment | TRACE-REQUIRED |
| WP-11 | No unique WP-11 ownership/exit criteria confirmed by the current checked-in crosswalk | Source-driven decomposition required before implementation or status assignment | TRACE-REQUIRED |
| WP-12 | No unique WP-12 ownership/exit criteria confirmed by the current checked-in crosswalk | Source-driven decomposition required before implementation or status assignment | TRACE-REQUIRED |
| WP-13 | No unique WP-13 ownership/exit criteria confirmed by the current checked-in crosswalk | Source-driven decomposition required before implementation or status assignment | TRACE-REQUIRED |
| WP-14 | Infrastructure/provider/budget gates (RQ-014 association) | Provider adapter contract; budget and quota enforcement; owner approval; cleanup; mock-vs-live distinction; no paid/live provisioning without explicit authorization | PARTIAL / TRACE-REQUIRED |
| WP-15 | OIDC/trusted proxy security also appears in RQ-015; overlap with WP-02 must be resolved by source ownership | Single authority for issuer/key policy; ingress trust boundary; token validation; key rotation; replay resistance; deployment-specific acceptance | TRACE-REQUIRED (ownership overlap) |
| WP-16 | Dashboard view/navigation (RQ-016 association) | Route registry parity; view-to-handler-to-API trace; role-aware navigation; keyboard/screen-reader and cross-browser acceptance | PARTIAL / TRACE-REQUIRED |
| WP-17 | Document generation/durable writing (RQ-017 association) | Authenticated Dashboard-to-writer lifecycle; input validation; durable state; idempotency; interruption/recovery; artifact integrity; E2E evidence | PARTIAL / TRACE-REQUIRED |

**Important:** The table deliberately leaves WP-04 and WP-07–WP-13 unassigned. The current master inventory explicitly says WP-01–17 is a range and that atomic ownership was not yet documented. Naming plausible features for those numbers without inspecting their originating specifications would fabricate scope.

## 3. Cross-package requirements that must not be duplicated

1. **Identity authority:** WP-01 owns local Owner/Proxy session semantics; WP-02/WP-15 own OIDC trust and token-validation boundaries only after source ownership is reconciled. Do not create competing identity authorities.
2. **Job ownership:** WP-02 owns durable job state, lease fencing, checkpoint and child-event lifecycle. WP-05 owns Runner enrollment/claim/heartbeat. Runner credentials are not human sessions.
3. **Repository trust:** WP-03 owns authorized GitHub source selection/import. WP-06 owns trusted local bootstrap and persistence. A repository selection is not itself proof of trusted execution.
4. **Provider safety:** WP-14 must keep provider readiness, Owner approval, budget authorization, provisioning, and cleanup as distinct gates. Mock acceptance is not live cloud acceptance.
5. **Dashboard surface:** WP-16 owns navigation/view contract; feature packages own their API/service behavior. Navigation visibility is not authorization.
6. **Document workflow:** WP-17 owns durable writer lifecycle; shared artifact storage and job-control invariants remain with their respective owning packages.

## 4. Required per-WP trace record

Every atomic acceptance item added during WP-00B/00C must have:

- Stable ID: `DCP-WPxx-ACnnn`.
- Requirement ID(s), with exact source document and baseline SHA.
- Source path(s), symbol/route/handler and data/schema ownership.
- API contract: method/path, request/response schema, auth principal/role, status/error behavior.
- Dashboard view, DOM handler, client call and user-visible state (when applicable).
- Test path and exact test function; fixtures, markers, skip/xfail reason and platform constraints.
- Workflow/job/check name and whether it is required, optional or host-only.
- Positive, negative, boundary, concurrency, restart and recovery cases as relevant.
- Exact-head CI evidence and separate target-host evidence.
- Status, blocker, dependency, reviewer and closure commit.

No acceptance row may point only to a test file without a test function or to a workflow file without a job/check name.

## 5. WP-00B/C work remaining

- Enumerate every current source file and identify module entrypoints, exported service boundaries, persistence owners and imports.
- Enumerate Gateway and Local Auth Proxy routes including method, handler, middleware, role, request/response schema, status and error contract.
- Map every Dashboard view to DOM event handlers, API calls, service methods, auth states and visible success/failure states.
- Enumerate all test functions, fixtures, parametrizations, markers, skips/xfails and platform guards; record collection counts from actual test collection, not path counts.
- Map every workflow job and branch/event trigger to exact required status-check context and test/acceptance evidence.
- Reconcile all historical WP-01–WP-17 specifications and PR descriptions before assigning currently unowned package numbers.
- Resolve WP-02/WP-15 identity overlap and cross-package ownership before implementation changes.

## 6. Safety and release gates

- Do not enable Terminal templates until the relevant OS isolation package has passed target-host adversarial acceptance.
- Do not treat hosted Windows/Linux/macOS runners as the user's target host.
- Do not provision paid cloud resources or alter production settings without explicit authorization.
- Do not migrate or rewrite legacy data without restart-safe, additive, rollback-tested migration evidence.
- Do not merge a PR with failing, pending, or bypassed required checks.
- Do not mark a WP complete while any mandatory acceptance row is untested, skipped without an approved rationale, or lacks required target-host evidence.

## 7. Immediate execution order

1. Finish WP-00B/C source, API, Dashboard, test and workflow inventories.
2. Reconcile historical PR #150 unique audit content with current-main docs and exact current source.
3. Confirm WP-01–WP-17 ownership and requirements with source evidence; fill only verified acceptance rows.
4. Resolve WP-02/WP-15 overlap and WP-04/WP-07–WP-13 scope.
5. Continue implementation in dependency order, keeping WP-06 blocked until its Windows persistence and ACL findings are closed.
6. Run exact-head required CI, review, merge, then post-merge verification.
7. Keep WP-31 open until all package-level evidence and release gates are closed.

## 8. Audit statement

This document is a decomposition and traceability work product, not an implementation completion report. At creation, WP-00B/C remain partial, WP-00D remains in progress, and WP-31 remains not started. No package is upgraded to PASS by this document.


## 9. WP-01 source/test delta verified against current main (2026-11-25)

A targeted re-read of exact main SHA `57589873583c706d4af9756709596fdba7c22de9` confirms that the two source files referenced by the existing WP-01 crosswalk retain these blob identities:

- `tools/cloud_gateway/server.py`: `9a55bccf216cff1b934bebd643e68364305449aa` (1,894 lines).
- `tools/local_auth_proxy.py`: `2d8708216f85c28e70f358c0672152353c6b59bc` (971 lines).

The source still exposes Gateway `do_GET`, `do_POST`, `do_DELETE` and Local Auth Proxy `do_GET`, `do_POST`, `do_DELETE`, `do_OPTIONS`; Gateway helper anchors include `ProxyIdentityVerifier`, `runner_identity`, `proxy_identity`, `csrf_valid`, `same_origin` and bounded `body` parsing. This confirms the old source blob anchors remain applicable, but does not itself prove runtime behavior.

The current test files have these exact blob identities and test functions:

- `tests/test_cloud_gateway_proxy_authorization.py`: `10a54b6daf32d4ce4e7c593655c547171850b169`; includes `ProxyMutationAuthorizationTests.test_operator_can_read_session_but_cannot_create_runner`, `test_operator_cannot_terminate_runner`, and `test_unsupported_http_methods_are_not_dispatched`.
- `tests/test_local_auth_proxy_project_routes.py`: `2d1c1c2de3318e755c1a399e5f707e152cd4107b`; includes `test_options_and_unsupported_methods_have_explicit_boundary`, `test_rejects_encoded_path_separators_and_duplicate_query_keys`, exact project/read allowlist tests, artifact/authentication tests, CSRF-protected runner/Terminal/Infrastructure mutation tests, idempotency forwarding, job resume/cancel and authenticated-session tests.

**Traceability correction:** the older WP-01 acceptance document's rows WP01-API-009/010 describe unsupported-method behavior as a test gap. The current test source now contains explicit test anchors for unsupported methods at both the Gateway and Proxy test suites. Reclassify those rows as **IMPLEMENTED / TEST-ANCHORED**, not PASS, pending execution on the candidate SHA and inspection of the asserted status/header/no-side-effect behavior. Similarly, encoded separators and duplicate query keys now have an explicit Proxy test anchor; other query/path normalization cases remain open unless separately enumerated.

This delta closes only a source/test-anchor freshness discrepancy. It does not close WP-01 or WP-00B/C: test execution, full route-to-test mapping, fixtures/parameterization, workflow/job mapping, and the remaining route/schema/role matrix still require verification.
