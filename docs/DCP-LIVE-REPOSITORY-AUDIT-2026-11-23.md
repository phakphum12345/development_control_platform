# DCP Live Repository Audit — 2026-11-23

**Repository:** `phakphum12345/development_control_platform`  
**Audit branch:** `docs/wp00-live-audit-20261123`  
**Canonical branch:** `main`  
**Exact main baseline:** `eaa9ceb91088c39b90d9b11b3817dc793e40005a`  
**Protocol:** DCP-CEEP v1.0 — adopted  
**Audit state:** IN_PROGRESS — live metadata and selected PR/CI evidence refreshed; source-to-test-to-requirement trace and full acceptance audit remain open.

## 1. Baseline and repository metadata

| Item | Observed value | Evidence boundary |
|---|---:|---|
| Visibility | Public | GitHub repository metadata |
| Default branch | `main` | GitHub repository metadata |
| Exact main SHA | `eaa9ceb91088c39b90d9b11b3817dc793e40005a` | Latest commit returned by GitHub on 2026-11-23 audit |
| Linked account permissions | Admin / Maintain / Push | GitHub repository permissions response |
| Open pull requests | 5 | Live GitHub open-PR search |
| Open issues | 0 | Live GitHub open-issue search |
| Branches | 162 | Branch search paginated: 100 + 62; final cursor empty |
| Main combined status entries | 0 returned | No status entries were returned by the combined-status endpoint; this is not proof that every workflow is green |
| Open PR count after this audit PR was opened | 6 | The five-PR register below is the pre-creation source snapshot; PR #153 is this audit's delivery PR and is intentionally excluded from that baseline register |
| Branch protection | NOT AUDITED in this pass | Do not assume required checks are enforced by branch protection |

The audit baseline is the current main commit above, not the older `985a78d5fba459c8a0cbcf47e5d00a858c6e6228` baseline used by the 2026-11-19 audit documents on PR #150.

## 2. Live pull-request register

All four same-repository PRs below target `main` at base SHA `eaa9ceb91088c39b90d9b11b3817dc793e40005a`. Their current exact heads were fetched on 2026-11-23.

| PR | State | Head branch | Exact head SHA | Changed files | Current finding |
|---|---|---|---|---:|---|
| [#149](https://github.com/phakphum12345/development_control_platform/pull/149) | OPEN / DRAFT | `work/psec-base-runtime-trust-validation` | `d1dd866e7244b8e3fb87654adf631acbb50599b8` | 10 | CI workflows completed successfully; optional Windows runner acceptance SKIPPED; hosted PSEC probe reports internal BLOCKED |
| [#150](https://github.com/phakphum12345/development_control_platform/pull/150) | OPEN / DRAFT | `docs/wp00-full-repository-audit-20261119` | `aaa18c0674a1150d925fd8ee7ae22dccbc9d1e76` | 10 | Audit documentation candidate; its named baseline is older than current main and must not be presented as current-main inventory |
| [#151](https://github.com/phakphum12345/development_control_platform/pull/151) | OPEN / DRAFT | `fix/dashboard-code-navigator-cover-all-views-20261119` | `d17d6f99e32dab416c23f53339a14454da83b175` | 4 | Dashboard Code Navigator mapping candidate; CI workflows completed successfully; optional Windows runner acceptance SKIPPED |
| [#152](https://github.com/phakphum12345/development_control_platform/pull/152) | OPEN / DRAFT | `work/wp06-trusted-repository-bootstrap` | `b282acc9e7af7373261b64ae05cc748848652a7c` | 6 | Runner credential/allowlist hardening candidate; CI workflows completed successfully; security review and failure-injection audit remain |
| [#138](https://github.com/phakphum12345/development_control_platform/pull/138) | OPEN / NOT DRAFT | Fork `phakphumwiri-boop/development_control_platform` branch `main` | `23ab6fa5f0602040262e0b5d0c96da6aa00f41de` | 140 | Base is feature branch `work/wp18b1-windows-psec-filesystem-authorization`; mergeable=false; do not merge wholesale |

PR #140 is no longer open and its merge is represented by the current main baseline. No PR was merged or closed during this audit.

## 3. Exact-head workflow evidence

Workflow run metadata and job conclusions were fetched for the exact PR head SHAs in Section 2.

### PR #149 — Windows PSEC trusted runtime

Head: `d1dd866e7244b8e3fb87654adf631acbb50599b8`

| Workflow / job | Run ID | Result | Interpretation |
|---|---:|---|---|
| Validate Control Plane / validate | 44594228921 | PASS | Hosted validation job |
| Windows dynamic-port launcher integration | 44594228921 | PASS | Hosted Windows integration |
| Windows runner acceptance | 44594228921 | SKIPPED | Not target-host acceptance |
| Local-first Minimal Emulator / Linux | 44594228491 | PASS | Hosted Linux emulator |
| Local-first Minimal Emulator / Windows | 44594228491 | PASS | Hosted Windows Auth Proxy + Gateway E2E |
| Cross-platform Recovery / Ubuntu | 44594228460 | PASS | Hosted recovery tests |
| Cross-platform Recovery / Windows | 44594228460 | PASS | Hosted recovery tests |
| Windows PSEC API Availability Probe | 44594228695 | Workflow PASS; probe BLOCKED | Informational probe explicitly exits successfully for an expected blocked hosted image |

The PSEC probe log records `available=false`, state `BLOCKED`, missing `filesystem_deny`, `filesystem_enumerate`, and `network_ingress_policy`, with reason `processmodel.dll is unavailable from the System32 search path`. The workflow itself warns that this is not an acceptance PASS. Therefore PR #149 does not establish target Windows PSEC acceptance.

### PR #150 — WP-00 audit documentation

Head: `aaa18c0674a1150d925fd8ee7ae22dccbc9d1e76`

- Validate Control Plane: PASS (run 44590499134).
- Local-first Minimal Emulator: Linux PASS and Windows PASS (run 44590499095).
- Cross-platform Recovery: Ubuntu PASS and Windows PASS (run 44590499043).
- These results are exact-head workflow results only. They do not establish that the PR's audit inventory is current for the newer main baseline.

### PR #151 — Dashboard Code Navigator

Head: `d17d6f99e32dab416c23f53339a14454da83b175`

- Validate Control Plane: PASS (run 44585647307).
- Local-first Minimal Emulator: Linux PASS and Windows PASS (run 44585647238).
- Cross-platform Recovery: Ubuntu PASS and Windows PASS (run 44585647220).
- Package Development Control Platform: PASS (run 44585647193).
- Windows runner acceptance: SKIPPED (run 44585647307).
- PR diff reports mapping coverage for 23 Dashboard views; this is static mapping-integrity evidence, not proof that all 23 user journeys work end-to-end.

### PR #152 — Runner credential and allowlist hardening

Head: `b282acc9e7af7373261b64ae05cc748848652a7c`

- Validate Control Plane: PASS (run 44591565893).
- Local-first Minimal Emulator: Linux PASS and Windows PASS (run 44591566010).
- Cross-platform Recovery: Ubuntu PASS and Windows PASS (run 44591565963).
- Windows runner acceptance: SKIPPED (run 44591565893).
- The PR changes protected JSON persistence, credential/allowlist validation and bootstrap tests. Passing CI does not replace a focused review of atomic replacement semantics, parent-directory ACLs, partial-write recovery, and preservation of existing credentials/settings on every rejected or interrupted path.

## 4. Current-main documentation discrepancy

The current `main` branch contains the older operating documents and a continuity ledger captured on 2026-11-14. The files `docs/DCP-REPOSITORY-INVENTORY.md`, `docs/DCP-IMPLEMENTATION-STATUS.md`, `docs/DCP-REQUIREMENTS-TRACEABILITY.md`, and `docs/DCP-TEST-AND-ACCEPTANCE-MATRIX.md` from the 2026-11-19 audit set were not found on current main during this pass; they are additions in PR #150.

Consequences:

1. The 2026-11-19 inventory must remain identified as a historical/candidate baseline tied to its named SHA.
2. Do not copy its file counts or PR register forward as current-main facts without a fresh tree and source audit.
3. The 2026-11-14 continuity ledger is stale for current PR/main state and needs a dated append-only checkpoint.
4. The full WP-00 audit remains IN_PROGRESS until current-main source, route handlers, Dashboard actions, test functions, fixtures/skips, workflow jobs and requirements are traced on a single exact SHA.

## 5. Work-package status and safety gates

The previously recorded WP-00 through WP-31 inventory remains a planning reference, not a freshly revalidated completion register. Current evidence still requires the following gates to remain open:

- WP-00B / WP-00C / WP-00D: complete current-main source/API/Dashboard/workflow/test/documentation traceability.
- WP-18A–18E: platform-specific OS isolation, adversarial acceptance and process cleanup; hosted CI is not target-host certification.
- WP-19: actual supported Windows host and Dashboard → Auth Proxy → Gateway E2E.
- WP-20–WP-30: source-backed feature completion and operational acceptance by each workstream.
- WP-31: final exact-SHA regression, security, recovery, packaging and release audit.

Safety constraints:

- All seven built-in Terminal templates remain disabled until the relevant OS isolation backend is VERIFIED by actual-host acceptance.
- Windows PSEC is not LPAC. Do not claim AppContainer/LPAC or PSEC acceptance from unit tests or a hosted informational probe.
- Linux bubblewrap policy/CI does not substitute for target Linux host acceptance.
- Preserve UNKNOWN, SKIPPED, active, lease-expired and mismatched workspaces unless an independently verified cleanup contract authorizes cleanup.
- Cloud provisioning, VM creation, provider activation and deployment remain OFF absent a separate explicit authorization with scope and cost ceiling.
- No merge, deployment, release, template enablement or destructive cleanup was performed by this audit.

## 6. Audit limitations and next exact actions

This pass refreshed GitHub metadata, open PR/issue state, branch count, selected PR diffs, exact-head workflow runs/jobs and the PR #149 probe log. It did not execute the test suite locally, enumerate the recursive main tree, inspect every source file, inspect all review threads, or perform Windows/Linux target-host acceptance.

Next actions:

1. Complete WP-00A recursive tree inventory on current main SHA `eaa9ceb91088c39b90d9b11b3817dc793e40005a`.
2. Reconcile PR #150's 2026-11-19 audit documents against current main without rewriting historical evidence.
3. Complete source-backed WP-00B route/API/Dashboard/workflow mapping and WP-00C test/fixture/skip/job mapping.
4. Perform a focused security review of PR #152 before considering it ready for review.
5. Continue PR #149 target-host acceptance planning without treating the informational hosted probe as PASS.
6. Re-run exact-head checks after any changes; keep all PRs Draft/HOLD until review and acceptance gates are satisfied.

**Audit result:** IN_PROGRESS. This document records the observed state and evidence boundaries; it is not a release or security certification.


## 7. WP-00A recursive tree inventory — completed 2026-11-23

The Git Trees API was queried recursively at the exact current-main commit SHA `eaa9ceb91088c39b90d9b11b3817dc793e40005a`. GitHub returned `truncated=false`; all 340 blob paths were enumerated.

| Classification | Count | Counting rule |
|---|---:|---|
| All repository files | 340 | Blob entries in the recursive tree |
| Source files | 111 | `.py` and `.ps1` implementation files outside test paths and workflow definitions |
| Test files | 117 | Files under `tests/` plus the explicitly named test scripts discovered in the tree |
| GitHub Actions workflow files | 9 | Files directly under `.github/workflows/` |
| Documentation/checkpoint/README files | 73 | Files under `docs/`, `checkpoints/`, plus root `README.md` |

Top-level areas observed: `.github`, `.vscode`, `checkpoints`, `config`, `dashboard`, `deploy`, `docs`, `packaging`, `schemas`, `scripts`, `states`, `tests`, and `tools`, plus root launchers and dependency manifests.

This is a path inventory, not a semantic audit of every implementation file. The source count is deliberately narrow: it counts Python and PowerShell implementation files only, not HTML/JavaScript embedded in the Dashboard, schemas, YAML configuration, or workflow definitions. The test count includes test-named files in the test directory; it does not assert that each test is collected or executed by every workflow.

### Stale inventory fields found in current-main documents

- `docs/IMPLEMENTATION-STATUS.md` reports `docs/` = 58, while the current recursive tree contains 73 documentation/checkpoint/README files under the counting rule above. These are different scopes and the older figure is not a current full-repository document count.
- `docs/REQUIREMENTS-TRACEABILITY.md` labels its test-file inventory as an 86-file baseline; the current tree has 117 test files under the counting rule above. The existing requirement map is also explicitly first-pass and leaves atomic acceptance criteria open.
- The current-main implementation status records WP-00 source/API/Dashboard/requirements mapping as IN_PROGRESS and WP-31 as NOT STARTED. WP-18 platform acceptance and WP-19 Windows host E2E remain blocked/unknown as described in that document.

Do not silently replace these historical figures: update them only through a separately reviewed reconciliation that records the exact baseline and counting rule.

### PR #153 exact-head CI refresh

At PR head `4ab7bb02a517b4f93543a429c4540c33166cd814`:

| Workflow / job | Run ID | Observed result |
|---|---:|---|
| Local-first Minimal Emulator — Windows + Linux jobs | 45153995853 | PASS |
| Cross-platform Recovery — Ubuntu + Windows jobs | 45153995851 | PASS |
| Validate Control Plane — Windows dynamic-port integration | 45153995875 | PASS |
| Validate Control Plane — validate job | 45153995875 | IN_PROGRESS at last observation; WebKit preview-proxy step running |
| Validate Control Plane — Windows runner acceptance | 45153995875 | SKIPPED |

The validate workflow is not PASS until the validate job completes successfully. The skipped Windows runner acceptance remains a separate evidence gap. These results apply only to the exact PR head above and must be refreshed if the branch changes.

## 8. Updated WP-00 status

- WP-00A recursive repository path inventory: **PASS for path enumeration only** (exact main SHA, complete non-truncated tree response).
- WP-00B source/API/Dashboard route mapping: **IN_PROGRESS**.
- WP-00C test/fixture/skip/workflow-job mapping: **IN_PROGRESS**; inventory counts are complete, execution/collection mapping is not.
- WP-00D requirement-to-source-to-test-to-acceptance trace: **IN_PROGRESS**.
- Full repository audit and release acceptance: **NOT COMPLETE**.

Next actions: finish PR #153 exact-head CI; reconcile the stale documentation counts with an explicit counting convention; map concrete route handlers and Dashboard actions to source and tests; inspect fixtures/skips and review threads; then continue work-package acceptance without weakening any safety gates.


## 9. WP-00B source/API/Dashboard mapping — first pass

All observations below are from exact main SHA `eaa9ceb91088c39b90d9b11b3817dc793e40005a`.

### Source boundaries inspected

| Area | Main source | Observed responsibility | Current evidence limit |
|---|---|---|---|
| Gateway HTTP API | `tools/cloud_gateway/server.py` (1,894 lines) | HTTP method dispatch for health, auth/session, GitHub repository/refs/project inspection, Local Projects, Jobs, Runner, Cloud Runner, Infrastructure, Artifacts, Terminal, Document Workflow and Recon API families | Route-family inventory only; not a complete method/path/body/schema/role/CSRF table |
| Local Auth Proxy | `tools/local_auth_proxy.py` (971 lines) | Same-origin login/logout/session, CSRF/session enforcement, allowlisted Gateway forwarding, jobs/previews/artifacts, cloud runner and infrastructure actions | Forwarding and deny rules need a complete pairwise comparison with Gateway route contracts |
| Dashboard | `dashboard/index.html` (2,639 lines) | Single-page view markup, inline handlers, API calls, Code Navigator registry, local-only UI tools and runner/terminal controls | Static source inspection is not a full user-journey or accessibility acceptance |
| Main validation workflow | `.github/workflows/validate-control-plane.yml` (573 lines) | Python unittest discovery, embedded JavaScript syntax, dependency audit, Chromium/Firefox/WebKit preview tests, dashboard browser smoke, YAML/schema validation and Windows integration | Self-hosted Windows runner acceptance is gated behind manual workflow dispatch input and was SKIPPED on this PR |

### Gateway route families observed

- GET: health/session, GitHub repository catalog/refs/commit/project inspection, Local Projects/roots, Jobs/logs/previews, Runners, Cloud Runners/status, Infrastructure/gates, Terminal templates/events, Document Workflow grants/target, Artifacts download, Recon and runner-agent endpoints.
- POST: Jobs/create/resume/cancel/preview lifecycle, Terminal authorize/jobs/command preview/template import, Infrastructure create/actions/gates, Runner drain/enable, Cloud Runner create, Document Workflow grant/revoke/proposal/approve and runner-agent claim/ping endpoints.
- DELETE: Job preview stop, Infrastructure resource deletion and Cloud Runner deletion.
- The Proxy adds login/logout/session and serves Dashboard content; it applies an allowlist and route-specific matching before forwarding requests. Unknown API routes are explicitly denied.

This list intentionally describes families, not a complete API contract. Query-string handling, path parameters, request bodies, authorization roles, CSRF, idempotency, response schemas and all failure paths remain to be enumerated.

### Dashboard mapping

The current `CODE_NAV_MAPPINGS` registry contains **21** view mappings on main:

`contact`, `home`, `dev-tools`, `ui-routes`, `ui-simulator`, `route-colors`, `repo`, `pr`, `workspace`, `evidence`, `gates`, `checkpoint`, `audit`, `github-api`, `account`, `code-navigator`, `cloud-runners`, `infrastructure`, `repo-selector`, `user`, `terminal-studio`.

The test `tests/test_dashboard_contract.py::test_code_navigator_covers_all_dashboard_views` asserts exact set equality for these 21 IDs. This is mapping-integrity evidence, not 21 E2E user journeys. The current main test `test_all_tool_views_exist` checks a smaller set of core view IDs; its expected list is not the full mapping registry. The PR #151 historical diff claim of 23 mapped views must therefore not be copied to current main without reconciling the exact branch and view-set definition.

### Test/workflow links inspected

- Dashboard mapping and view contracts: `tests/test_dashboard_contract.py`.
- Local Auth Proxy authentication, CSRF, allowlist and browser-preview flows: `tests/test_local_auth_proxy.py`.
- Dashboard launcher lifecycle: `tests/test_dashboard_launcher_contract.py` and Windows PowerShell `tests/test_dashboard_dynamic_port.ps1`.
- Cloud Runner Dashboard contract: `tests/test_cloud_runner_dashboard_contract.py`; provider lifecycle E2E contract: `tests/test_cloud_runner_e2e_acceptance.py`.
- Windows PSEC host-acceptance harness contract: `tests/test_windows_psec_host_acceptance.py`; its non-Windows branch explicitly reports BLOCKED/skips native host acceptance.
- `validate-control-plane.yml` runs `python -m unittest discover -s tests -v`, targeted real-browser preview tests for Chromium/Firefox/WebKit, `node tests/browser_smoke.mjs`, YAML/JSON Schema validation, and a Windows dynamic-port/launcher integration job.
- The self-hosted Windows runner job is conditional on `workflow_dispatch` and `inputs.run_self_hosted_windows_acceptance == true`; a skipped job cannot be counted as host acceptance.

### Review register cross-check

PR #152 has one submitted COMMENTED review (review ID `PRR_kwDOVTLXVs8AAAABZs4Tsg`) and a corresponding general PR comment (comment ID `6019748786`), not an empty review history. The review explicitly requests follow-up on parent-directory DACL protection, two-file transaction/recovery behavior, atomic replacement proof and failure-injection tests. The inline review-thread endpoint returned an empty list; that does not negate the general review/comment. PR #152 remains Draft/HOLD.

## 10. Updated WP-00 progress

- WP-00A recursive tree inventory: **PASS for path enumeration only**.
- WP-00B source/API/Dashboard route mapping: **PARTIAL** — primary source boundaries, route families and all 21 Code Navigator mappings identified; complete route/security contract remains open.
- WP-00C test/fixture/skip/workflow-job mapping: **PARTIAL** — 117 test-path files counted and representative high-risk tests/workflow jobs inspected; complete test collection, fixture/data, skip and requirement crosswalk remains open.
- WP-00D requirement-to-source-to-test-to-acceptance trace: **IN_PROGRESS** — existing traceability document is explicitly first-pass and incomplete.
- Full repository audit and release acceptance: **NOT COMPLETE**.

Next actions: finish exact-head CI for the updated PR; build a method/path/auth/CSRF/idempotency API matrix; reconcile Dashboard registry against actual rendered views and E2E journeys; enumerate test collection/skip markers and fixture dependencies; audit all PR review comments and open work packages; preserve all unresolved host and security gates.


## 11. WP-00B API contract security pass — additional source evidence

The following is a focused source-level contract map, not a claim that every API has been exhaustively documented.

### Local Auth Proxy read boundary

At main baseline, `tools/local_auth_proxy.py` defines an explicit `ALLOWED_GET` tuple for selected read endpoints. Additional GET routes are accepted only through route-specific predicates, including:

- `/api/jobs`, job detail, logs and artifact/preview reads with bounded query parsing.
- `/api/github/repositories` and repository refs/project inspection.
- `/api/local-projects/{uuid}`.
- `/api/terminal/events/{...}` and infrastructure resource/gate reads.
- `/api/recon/...` is separately allowed by the current predicate.
- Artifact download and authenticated preview proxy routes are separately handled.

The Proxy rejects unrecognized API paths with 404 rather than forwarding arbitrary `/api/*` paths. Query strings are parsed and bounded for selected endpoints (for example job list limits and log cursor/limit). This allowlist is an important security boundary; every Gateway route addition should have an intentional Proxy policy decision and negative test.

### Mutating route families and controls observed in Gateway

| Mutation family | Route shape observed | Controls visible in source |
|---|---|---|
| Terminal job create | `POST /api/terminal/jobs` | Owner role, signed identity, CSRF, required Idempotency-Key, session-scoped idempotency and conflict handling |
| Terminal authorize/grant/template import/command preview | `POST /api/terminal/authorize`, grant/revoke, `/api/terminal/templates/import`, `/api/terminal/commands/preview` | Signed identity, CSRF; owner for authorization/import/grant operations; owner/operator for command preview |
| Document Workflow | `POST /api/document-workflow/grants`, proposals, revoke/approve | Owner role and CSRF; proposal call carries idempotency key |
| Infrastructure | `POST /api/infrastructure[/...]`, gate toggle | Owner/operator for selected actions, CSRF; create operation passes idempotency key |
| Jobs | `POST /api/jobs`, `/{id}/resume`, `/{id}/cancel`, `/{id}/previews` | Owner/operator base; CSRF; owner-only Local Folder job, UNKNOWN resume, cancellation and preview creation |
| Runner control | `POST /api/runners/{worker}/...` and `/v1/runner/*` | Signed dashboard identity plus owner/CSRF for management; separate runner identity for agent protocol |
| Destructive operations | `DELETE /api/jobs/{job}/previews/{runtime}`, `/api/infrastructure/{resource}`, `/api/cloud-runners/{id}` | Owner role and CSRF; preview deletion also requires same-origin |

### Proxy-side mutation boundary

The Proxy requires same-origin for POST, requires a pre-authentication CSRF session for login, authenticated session + CSRF for logout and job mutations, and forwards only explicitly matched job routes. This means the Proxy's GET allowlist and POST/DELETE route matchers should be tested against both allowed and denied route variants, including query-string variants and malformed IDs.

### Remaining API audit gaps

- No generated exhaustive method × path × query × body-schema × role × CSRF × idempotency matrix exists yet.
- Route-family matching was inspected in Gateway and Proxy, but complete branch-by-branch comparison is not finished.
- Need tests proving every mutating Gateway route is reachable only through an intentionally allowed Proxy path (or intentionally unavailable) and that malformed path/query variants fail closed.
- Need inspect all `do_PUT`/`do_PATCH` handling and confirm whether any API methods exist beyond GET/POST/DELETE.
- Need map API response schemas and error/status semantics to dashboard callers.

## 12. WP-00C test, fixture and skip evidence — current scope

- The recursive tree search found no directory/file paths named `fixtures`, `fixture`, `testdata`, `golden` or `samples` under the explicit path-name convention. This does **not** prove that tests have no fixture data: test data may be inline, generated in temporary directories, or stored under other names.
- Representative test suites inspected include Dashboard contract, Local Auth Proxy, Cloud Runner Dashboard contract, Cloud Runner E2E acceptance, Windows PSEC host acceptance, local Runner pipeline and launcher contracts.
- `validate-control-plane.yml` runs Python `unittest discover -s tests -v`, explicit real Chromium/Firefox/WebKit preview-proxy tests, Node dashboard browser smoke, YAML/JSON Schema validation, and dedicated Windows integration steps.
- The self-hosted Windows runner job is explicitly conditional on `workflow_dispatch` plus `inputs.run_self_hosted_windows_acceptance == true`; ordinary PR runs skip it.
- The Windows PSEC host-acceptance test suite contains a non-Windows blocked/skip branch; hosted Windows GitHub runners and self-hosted target-host acceptance must not be conflated.
- A full automated census of all 117 test-path files for skip decorators, test discovery, fixtures, and CI selection has **not** been completed. The earlier 117 count is a path inventory, not a count of collected test cases or passed tests.

## 13. PR #153 CI refresh — latest observed state

For exact head `2757d441c716f231b682691035a8b28fd05516f9`, at the latest poll:

| Workflow/job | Run / Job | Result |
|---|---:|---|
| Validate Control Plane — Windows dynamic-port launcher integration | Run 45154961048 / Job 137625506399 | **PASS** |
| Validate Control Plane — main validate job | Run 45154961048 / Job 137625507039 | **IN PROGRESS**, executing dashboard/Python contracts |
| Validate Control Plane — self-hosted Windows runner acceptance | Run 45154961048 / Job 137625509738 | **SKIPPED** |
| Cross-platform Recovery — Windows | Run 45154961165 / Job 137625502400 | **IN PROGRESS**, Local Runner interruption/recovery pipeline |
| Cross-platform Recovery — Ubuntu | Run 45154961165 / Job 137625503077 | **IN PROGRESS**, installing bubblewrap |
| Local-first Minimal Emulator — Linux | Run 45154961121 / Job 137625584155 | **QUEUED** |
| Local-first Minimal Emulator — Windows | Run 45154961121 / Job 137625584483 | **QUEUED** |

No conclusion is assigned to workflows with active or queued jobs. The exact-head validation workflow is not green while the validate job remains in progress and self-hosted acceptance is skipped.

## 14. Updated WP-00 status

- WP-00A recursive repository path inventory: **PASS for path enumeration only**.
- WP-00B source/API/Dashboard mapping: **PARTIAL** — source boundaries, 21 Dashboard mappings, Proxy GET allowlist and representative mutating-route controls mapped; exhaustive method/path/security contract remains open.
- WP-00C test/fixture/skip/workflow mapping: **PARTIAL** — 117 test paths counted and representative suites/workflow steps inspected; all-file skip/fixture/collection crosswalk remains open.
- WP-00D requirement-to-source-to-test-to-acceptance trace: **IN PROGRESS**.
- Full repository audit and release acceptance: **NOT COMPLETE**.

Next: finish exact-head CI; complete GET/POST/DELETE and unsupported-method matrix; inspect Proxy/Gateway route parity with negative tests; complete skip and collected-test census in manageable batches; then reconcile each requirement and work-package acceptance criterion against actual source, test, workflow and host evidence.
