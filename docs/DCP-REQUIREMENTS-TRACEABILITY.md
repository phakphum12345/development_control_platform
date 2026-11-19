# DCP Requirements Traceability — 2026-11-19

**Baseline:** `main@`985a78d5fba459c8a0cbcf47e5d00a858c6e6228``  
**State:** PARTIAL — source/test/workflow family mapping is established; complete per-symbol, per-handler, per-test-function mapping is still IN_PROGRESS.

## Traceability rules

- A requirement is not PASS because a source file or test file exists.
- A passing workflow is valid only for the exact head SHA that ran.
- Host acceptance must identify the OS, host type, test command, evidence artifact and exact commit.
- Missing, skipped, blocked, stale or inaccessible evidence is UNKNOWN/BLOCKED, never PASS.
- Existing repository IDs (CORE/IMP/BUILD/RUN/TERM/TEST/SEC/ART/OPS/AI/INF) remain canonical. The Master Coding Directive's workstream labels are mapped below as WS labels to avoid renumbering existing WPs.

## Requirement-to-source/test/workflow map

| Requirement group | Directive workstream | Main source | Test evidence files | Relevant workflows | Current state |
|---|---|---|---|---|---|
| CORE-01 Gateway / local API | WS-01 | `tools/cloud_gateway/server.py`, `service.py`, `store.py` | `tests/test_cloud_gateway.py`, `tests/test_cloud_gateway_dynamic_port.py`, `tests/test_sqlite_security.py` | Validate Control Plane; Local-first Minimal Emulator | PARTIAL |
| CORE-02 Job Control / scheduling | WS-05 | `tools/cloud_gateway/job_control.py`, `scheduler.py`, `store.py` | `tests/test_cloud_gateway_job_control.py`, `tests/test_cloud_gateway_scheduler_integration.py`, `tests/test_cloud_runner_user_api.py` | Cross-platform Recovery; Local-first Minimal Emulator | PARTIAL |
| CORE-03 Workspace / Runner | WS-06, WS-16 | `tools/local_runner_agent/workspace.py`, `pipeline.py`, `execution.py`, `tools/runner_agent/agent.py` | `tests/test_local_runner_workspace.py`, `tests/test_local_runner_pipeline_e2e.py`, `tests/test_runner_agent.py` | Cross-platform Recovery; Validate Control Plane | PARTIAL |
| IMP-01 GitHub App intake | WS-03 | `tools/cloud_gateway/github_app.py`, `github_app_runtime.py`, `public_github.py` | `tests/test_cloud_gateway_github_app.py`, `tests/test_cloud_gateway.py` | Validate Control Plane; Local-first Minimal Emulator | PARTIAL |
| IMP-02 Local Folder intake | WS-04 | `tools/local_runner_agent/local_project.py`, `checkout.py`, `file_safety.py` | `tests/test_local_project_registry.py`, `tests/test_local_project_snapshot.py`, `tests/test_local_runner_checkout.py`, `tests/test_local_auth_proxy_project_routes.py` | Cross-platform Recovery; Validate Control Plane | PARTIAL |
| IMP-03 Project intelligence | WS-08 | `tools/project_intelligence.py`, `tools/dcp_project_intelligence.py`, `tools/architecture_planner.py` | `tests/test_project_intelligence.py`, `tests/test_architecture_planner.py` | Validate Control Plane | PARTIAL |
| BUILD-01/02 Build adapters | WS-08 | `tools/local_runner_agent/web_build.py`, `pipeline.py` | `tests/test_local_web_build.py`, `tests/test_local_runner_pipeline_e2e.py` | Validate Control Plane; Cross-platform Recovery | PARTIAL |
| RUN-01/02 Runtime and Preview | WS-09 | `tools/local_runner_agent/runtime.py`, `tools/cloud_gateway/preview.py`, `tools/local_auth_proxy.py` | `tests/test_local_runtime.py`, `tests/test_authenticated_preview.py`, `tests/test_local_auth_proxy.py` | Validate Control Plane | PARTIAL |
| TERM-01–05 Terminal | WS-10 | `tools/cloud_gateway/terminal_catalog.py`, `terminal_grants.py`, `terminal_execution_contract.py`, `tools/local_runner_agent/terminal_executor.py` | `tests/test_terminal_command_pack_schema.py`, `tests/test_terminal_execution_contract.py`, `tests/test_terminal_grants.py`, `tests/test_terminal_executor.py` | Validate Control Plane; Cross-platform Recovery | BLOCKED for process execution |
| OSI-Linux | WS-11 | `tools/local_runner_agent/linux_sandbox.py`, `terminal_isolation.py` | `tests/test_linux_sandbox.py`, `tests/test_terminal_isolation.py` | Cross-platform Recovery | BLOCKED for production execution pending host acceptance |
| OSI-Windows / PSEC | WS-12 | No Windows PSEC launcher in main; PR #140/#149 branches contain candidate code | `tests/test_windows_psec*.py` exist on PR branches, not main | Windows PSEC API Availability Probe; Windows host acceptance | BLOCKED |
| OSI-macOS | WS-11 | Design and cloud runner adapter documentation; no signed native isolation helper evidenced | No complete host acceptance test evidenced | macOS Cloud Runner (manual provisioning path) | BLOCKED |
| ART-01 Artifact integrity | WS-13 | `tools/cloud_gateway/artifacts.py`, `tools/local_runner_agent/artifacts.py` | `tests/test_cloud_gateway_artifacts.py`, `tests/test_cloud_gateway_artifact_download.py`, `tests/test_local_runner_pipeline_e2e.py` | Validate Control Plane; Cross-platform Recovery | EXISTING / PARTIAL |
| TEST-01/02 Browser | WS-14 | `tools/local_runner_agent/browser_test.py`, Dashboard browser scripts | `tests/test_browser_test.py`, `tests/test_local_auth_proxy.py`, `tests/browser_smoke.mjs` | Validate Control Plane | PARTIAL |
| UI Dashboard | WS-15 | `dashboard/index.html`, `dashboard/recon-back-box/index.html` | `tests/test_dashboard_contract.py`, `tests/test_dashboard_document_lifecycle_contract.py` | Validate Control Plane; Local-first Minimal Emulator | PARTIAL |
| DATA-01 SQLite / environment | WS-17 | `tools/cloud_gateway/sqlite_security.py`, `store.py` | `tests/test_sqlite_security.py`, `tests/test_dev_environment.py` | Validate Control Plane; Cross-platform Recovery | PARTIAL |
| OPS-01–03 diagnostics / recovery | WS-18, WS-21 | `tools/cloud_gateway/preflight.py`, `local_mode.py`, `runner_cleanup.py`, `tools/dev_environment.py` | `tests/test_runner_preflight.py`, `tests/test_cloud_gateway_runner_cleanup.py`, `tests/test_local_runner_readiness.py` | Cross-platform Recovery; Local-first Minimal Emulator | PARTIAL |
| CLOUD / INF provider lifecycle | WS-07 | `tools/cloud_gateway/provider_router.py`, Azure/Orka modules, `tools/cloud_runner/backend.py` | `tests/test_cloud_gateway_azure_*.py`, `tests/test_cloud_gateway_orka.py`, `tests/test_cloud_runner_e2e_acceptance.py` | macOS Cloud Runner; Cloud Gateway Live Read-only Smoke | DEFERRED / PARTIAL; no live provision acceptance |
| AI-01 assisted development | WS-19 | `tools/project_intelligence.py`, `tools/architecture_planner.py` | `tests/test_project_intelligence.py`, `tests/test_architecture_planner.py` | Validate Control Plane | PARTIAL; approval/apply loop incomplete |
| DOC-01 document generation | WS-20 | `tools/document_workflow/gateway.py`, `writer.py` | `tests/test_document_workflow_gateway.py`, `tests/test_document_workflow_writer.py` | Validate Control Plane | PARTIAL |
| MCP-01 bounded local adapter | WS-20 | `tools/mcp_engine/engine.py`, `server.py` | `tests/test_native_mcp_engine.py`, `tests/test_native_mcp_server.py` | Validate Control Plane | EXISTING (read-only slice) |
| PKG-01 install/package | WS-21 | `packaging/package-release.ps1`, `packaging/windows/DCP.iss` | `tests/test_release_packaging.py`, PowerShell launcher tests | Package Development Control Platform | PARTIAL |
| SEC-01 supply-chain scanning | WS-22 | Workflow credential-pattern scan and security policy | Coverage requires full workflow/dependency scan audit | Validate Control Plane; package/release | VERIFY / PARTIAL |

## Requirement coverage gaps

1. The table maps requirement families to representative source/tests, not every function, call site, UI event, or test method.
2. The Dashboard's 334 observed DOM IDs are not 334 views; each actual view needs explicit route, handler, API, service, auth, tests and error-state mapping.
3. The Gateway and Auth Proxy use custom HTTP handler dispatch; route inventory must be extracted from dispatch logic, not only Flask-style decorators.
4. Some Windows PSEC tests and source exist only on PR branches and must not be attributed to main.
5. Workflow names alone are not evidence; test results must be tied to exact run IDs and commit SHAs.
6. Closed historical PRs/issues and all 158 branches require ancestry/value classification before pruning or reusing any branch.

## Next traceability increment

- Build a complete method/path/role/CSRF table from Gateway and Auth Proxy dispatch branches.
- Build Dashboard view/action/API/service mappings from every event handler.
- Enumerate test functions, skips, fixtures and test-to-workflow relationships across all 91 test files.
- Reconcile each backlog ID against current mainline source and the exact PR where work is proposed.


## 2026-11-19 — Gateway/Auth Proxy and Dashboard dispatch pass

### Dashboard navigation trace

Source: `dashboard/index.html` at `main@985a78d5fba459c8a0cbcf47e5d00a858c6e6228`.

There are 23 distinct navigation tabs:
`home`, `account`, `project-import`, `terminal-studio`, `code-navigator`, `cloud-runners`, `infrastructure`, `dev-tools`, `ui-routes`, `ui-simulator`, `route-colors`, `github-api`, `repo-selector`, `repo`, `pr`, `user`, `workspace`, `evidence`, `gates`, `checkpoint`, `document-generator`, `audit`, `contact`.

The declared `CODE_NAV_MAPPINGS` contains 21 entries. It is a partial mapping rather than complete coverage of all 23 tabs. The Dashboard also has 334 DOM element IDs; this number must not be mistaken for the view count.

### HTTP dispatch / authorization trace

Gateway source: `tools/cloud_gateway/server.py`  
Auth Proxy source: `tools/local_auth_proxy.py`

| Method / family | Gateway authorization observed | Additional enforcement |
|---|---|---|
| GET `/healthz` | Public | Health-only response |
| GET `/api/auth/session` | Validated proxy identity | Returns identity role and session CSRF token |
| GET GitHub repository catalog/refs/commit inspection | Validated proxy identity | Repository access delegated to GitHub App service/authorizer |
| GET Local Projects and roots | Owner | Owner-only project registry |
| GET Document Workflow grants/target/proposals | Owner | Project/path scope checked by workflow service |
| GET Terminal templates/events | Owner/operator | Event query is bounded |
| GET Jobs, logs, previews | Owner/operator | Owner-only restrictions for selected preview operations |
| GET Runners, Infrastructure, Artifacts, Cloud Runner resources | Owner/operator / validated dashboard session | Exact per-item rules require a further schema-level pass |
| POST Terminal jobs/authorize/grant revoke | Owner | Same-origin + CSRF |
| POST Document Workflow grant/revoke/proposal/approve | Owner | Same-origin + CSRF and explicit write approval |
| POST Terminal import/review | Owner | Same-origin + CSRF; imported packs remain inert |
| POST Terminal command preview | Owner/operator | Same-origin + CSRF; preview does not imply process launch |
| POST Infrastructure actions | Owner/operator | Same-origin + CSRF; gate mutation is Owner-only |
| POST Jobs create/resume/cancel/preview start | Owner/operator baseline | Same-origin + CSRF; Local Folder and selected lifecycle actions have additional Owner-only checks |
| POST Runner drain/enable | Owner | Same-origin + CSRF |
| POST `/v1/runner/*` | Runner credential identity | Separate Runner authentication/lease contract |
| DELETE preview/infrastructure/Cloud Runner resources | Owner | Same-origin + CSRF |

Auth Proxy GET is an allowlisted read surface; POST and DELETE mutations enforce same-origin and session CSRF before forwarding. The Auth Proxy's browser session is Owner-scoped in this implementation; it does not establish multi-user operator role support by itself.

### Remaining detail gaps

- Extract every literal and regex route, HTTP status, request body schema, response schema, query parameter and error branch.
- Verify each Gateway method against Auth Proxy forwarding allowlists; flag direct Gateway-only paths and paths unintentionally inaccessible from Dashboard.
- Map every one of the 23 tabs to its event listeners, called functions, API method/path, server handler, role/CSRF check and test.
- Reconcile README and Code Navigator's 21-entry registry with the 23 actual navigation tabs.
- Count and map individual test functions, fixtures, skips and test workflow jobs; path inventory alone is not test coverage.


## 2026-11-19 — Exact HTTP path-family refinement

The following path shapes were confirmed from the Gateway and Auth Proxy dispatch source. UUID means the bounded 36-character UUID pattern in the handler; Git commit SHA means 40 hexadecimal characters.

### Gateway GET

- `/healthz`
- `/api/auth/session`
- `/api/github/repositories`
- `/api/github/repositories/{owner}/{repo}/refs?kind=branches|tags`
- `/api/github/repositories/{owner}/{repo}/commits/{sha40}`
- `/api/github/repositories/{owner}/{repo}/projects/{sha40}`
- `/api/local-projects`, `/roots`, `/{uuid}`
- `/api/document-workflow/grants?project_id=...`, `/target?project_id=...&path=...`, `/proposals/{uuid}`
- `/api/terminal/templates`, `/templates/{custom-id}/events`
- `/api/jobs`, `/{uuid}`, `/{uuid}/logs`, `/{uuid}/artifacts`, `/{uuid}/events`, `/{uuid}/previews`, `/{uuid}/previews/{runtime-uuid}`, optional `/content/{relative-path}`
- `/api/runners`
- `/api/infrastructure/gates`, `/api/infrastructure`, `/api/infrastructure/{uuid}` and resource events
- `/api/artifacts/{uuid}/download`
- `/api/cloud-runners/status`, `/api/cloud-runners`, `/api/cloud-runners/{runner-id}`

### Gateway POST

- `/api/terminal/jobs`, `/api/terminal/grants/{uuid}/revoke`, `/api/terminal/authorize`
- `/api/document-workflow/grants`, `/api/document-workflow/grants/{uuid}/revoke`, `/api/document-workflow/proposals`, `/api/document-workflow/proposals/{uuid}/approve`
- `/api/infrastructure/gates/cloud_provisioning`, `/vm_creation`
- `/api/terminal/templates/{custom-id}/review`, `/api/terminal/templates/import`, `/api/terminal/commands/preview`
- `/api/infrastructure`, `/api/infrastructure/{uuid}/start|stop|restart`
- `/api/jobs`, `/api/jobs/{uuid}/resume`, `/cancel`, `/api/jobs/{uuid}/previews`
- `/api/runners/{worker-id}/drain|enable`
- Runner credential routes: `/v1/runner/register`, `/enroll`, `/ping`, `/claim`, `/{job-uuid}/terminal-grant`, `/artifacts`, `/heartbeat`, `/checkpoint`, `/logs`, `/finish`

### Gateway DELETE

- `/api/jobs/{job-uuid}/previews/{preview-uuid}`
- `/api/infrastructure/{resource-uuid}`
- `/api/cloud-runners/{runner-id}`

### Auth Proxy forwarding constraints

- GET uses explicit allowlists and regex patterns. GitHub refs query accepts exactly `kind=branches` or `kind=tags`; infrastructure catalog accepts `view=catalog`; job list accepts bounded `limit` (1–200); logs accept bounded `after_id` and `limit` (limit ≤500 and signed 64-bit cursor bound). Unsupported query strings are rejected.
- Preview reads use authenticated session/preview cookie and bounded response sizes; artifact download is a separate allowlisted path.
- POST requires same-origin and an authenticated session plus CSRF. Login has a pre-authentication CSRF challenge; logout requires authenticated CSRF. Job cancellation accepts an empty JSON object only. Infrastructure lifecycle and Runner drain/enable also require empty objects.
- DELETE requires same-origin and session-bound CSRF before forwarding.
- Both HTTP handlers implement GET, POST and DELETE dispatch; no PUT/PATCH handler was found in these two modules.

This is a source-derived route-shape inventory. It does not yet document every request/response JSON schema, every HTTP status/error branch, or the full Auth Proxy `ALLOWED_GET` constant and Gateway service call graph. Those remain open WP-00B work.


## 2026-11-19 — Dashboard Code Navigator mapping coverage

- 23 distinct Dashboard navigation tabs were extracted from `data-tab`.
- `CODE_NAV_MAPPINGS` contains 21 declared records.
- The two unmapped tabs are `project-import` and `document-generator`.
- The 21 declared records contain 48 test references; all referenced test file paths exist on current main.
- These declared links do not prove that the referenced tests were executed on the current PR head or that every handler/API edge is correct.
- WP-00B follow-up: map the two missing tabs and verify each mapping's handler, API path, auth/CSRF behavior, backend service and test assertion.


---

## 2026-11-20 — WP-00B Gateway/Auth Proxy dispatch contract pass

**Exact source baseline:** `main@985a78d5fba459c8a0cbcf47e5d00a858c6e6228`  
**Source blobs:** `tools/cloud_gateway/server.py@583eb48f4d37281e2485fc3331a893996c75f2ef`; `tools/local_auth_proxy.py@22e2a27ce9bcd630c17d665215322fd4ffcdca8b`.

This pass traces the actual `do_GET`, `do_POST`, and `do_DELETE` dispatch blocks. The route families below are source-derived; they are not a substitute for OpenAPI schema validation or a live deployment test.

### Gateway GET route / authorization / response contract

| Route family | Gateway identity / role gate | Success shape observed | Important non-success branches |
|---|---|---|---|
| `GET /healthz` | Public | `{status, provisioning_enabled}` | No identity check |
| `GET /api/auth/session` | Validated proxy identity | `{authenticated, csrfToken, user:{displayName,role}}` | 401 without proxy identity |
| `GET /api/github/repositories` | Validated proxy identity | `{repositories:[...]}` | 401; 503 when GitHub App catalog is unavailable |
| `GET /api/github/repositories/{owner}/{repo}/refs?kind=branches\|tags` | Validated proxy identity; repository access revalidated by service | `{repository,kind,refs}` | 400 invalid repo/kind/SHA; 403 inaccessible repository; 404 unknown path; 503 provider inspection failure |
| `GET /api/github/repositories/{owner}/{repo}/commits/{sha40}` | Validated proxy identity; service authorization | `{repository,...commit}` | 400 invalid SHA/repo; 403 inaccessible; 503 verification unavailable |
| `GET /api/github/repositories/{owner}/{repo}/projects/{sha40}` | Validated proxy identity; service authorization | Project inspection object | 400 invalid SHA/repo; 403 inaccessible; 503 inspection unavailable |
| `GET /api/local-projects`, `/roots`, `/{uuid}` | Owner only | `{projects:[...]}`, `{roots:[...]}`, or one public project | 401 unauthenticated; 403 non-owner; 404 invalid/missing project; 503 registry unavailable/read failed |
| `GET /api/document-workflow/grants?project_id=...`, `/target?project_id=...&path=...`, `/proposals/{uuid}` | Owner only | `{grants:[...]}`, `{target:...}`, or `{proposal:...}` | 401/403; 503 unconfigured/read failure; domain-specific `DocumentWorkflowError.status_code` |
| `GET /api/terminal/templates`, `/templates/{custom-id}/events` | Owner or operator | `{templates:[...],execution_enabled:boolean}` or `{events:[...]}` | 401; 403 role; 503 template store unavailable |
| `GET /api/jobs`, `/{uuid}`, `/{uuid}/logs`, `/{uuid}/artifacts`, `/{uuid}/events` | Owner or operator | `{jobs:[...]}`, public job, `{logs:[...]}`, `{artifacts:[...]}`, `{events:[...]}` | 401/403; 400 invalid ID/pagination; 404 missing job/artifact; 503 store unavailable |
| `GET /api/jobs/{uuid}/previews`, `/{uuid}/previews/{runtime_uuid}[/content/{relative_path}]` | Owner only (additional to owner/operator job gate) | `{previews:[...]}`, preview status, or `{content_type,body_base64}` | 401/403; 404 missing job/runtime/worker; 503 preview dependencies unavailable |
| `GET /api/runners` | Owner or operator | `{runners:[...]}` | 401 for missing/invalid dashboard identity; 503 registry unavailable |
| `GET /api/infrastructure/gates`, `/api/infrastructure[?view=catalog]`, `/{uuid}[/events]` | Owner or operator | `{gates:...}`, catalog, `{resources:[...]}`, resource or `{events:[...]}` | 401/403; 400 invalid UUID; 404 missing resource; 409 lifecycle conflict; 503 manager unavailable/failure |
| `GET /api/artifacts/{id}/download` | Owner or operator | Binary attachment; SHA-256 ETag; private/no-store and nosniff headers | 401; 404 missing/invalid artifact; 503 store unavailable |
| `GET /api/cloud-runners/status`, `/api/cloud-runners`, `/{runner_id}` | Validated dashboard identity (role-specific rules remain in provider/service layer) | Control status, `{runners:[...]}`, or one runner | 401; 400 invalid runner ID; 404 missing; 503 provider status unavailable |

### Gateway POST route / authorization / request contract

| Route family | Gateway authorization | Request / safety contract observed | Success / failure behavior |
|---|---|---|---|
| `POST /api/terminal/authorize` | Owner + same-origin + CSRF | Typed grant request; template and project/workspace scope validated by grant service | 201 `{grant}`; 401/403; 400/409 domain validation; 503 fail-closed |
| `POST /api/terminal/jobs` | Owner + same-origin + CSRF | Requires valid `Idempotency-Key`; binds template, project/workspace and authorization grant; execution-disabled catalog returns 409 | 202 new / 200 idempotent replay; 400/403/409/503 |
| `POST /api/terminal/grants/{uuid}/revoke` | Owner + same-origin + CSRF | Grant ID in path; revocation is state-checked | 200 `{revoked:true}`; 409 already consumed/revoked/missing; 400/503 |
| `POST /api/document-workflow/grants` | Owner + same-origin + CSRF | Explicit project ID, allowed paths and confirmation; grant store validates scope | 201 `{grant}`; 400 invalid fields; 503 unavailable |
| `POST /api/document-workflow/grants/{uuid}/revoke` | Owner + same-origin + CSRF | Exact grant reference and confirmation | 200 on revoke; 400/404/409/503 according to workflow error |
| `POST /api/document-workflow/proposals` | Owner + same-origin + CSRF | Proposal binds project, scoped path, base digest, content digest and idempotency | 201 proposal; invalid/stale scope rejected |
| `POST /api/document-workflow/proposals/{uuid}/approve` | Owner + same-origin + CSRF | Separate explicit confirmation bound to exact proposal/content digest; server read-back verification | 200 verified result; stale/conflicting proposal rejected |
| `POST /api/terminal/templates/import`, `/review`, `/api/terminal/commands/preview` | Owner + same-origin + CSRF | JSON object, bounded body; imported packs remain inert pending review; preview is not process launch | Domain-specific 200/201; 400/403/409/503 |
| `POST /api/infrastructure/gates/{cloud_provisioning\|vm_creation}` | Owner/operator session; gate mutation is Owner-only; same-origin + CSRF | Explicit gate state payload validated by backend | Backend-confirmed gate state; 400/403/409 |
| `POST /api/infrastructure` | Owner/operator + same-origin + CSRF; create gate and provider checks remain independent | Resource request plus idempotency key | 202/201 or domain-specific denial; provider remains disabled by default |
| `POST /api/infrastructure/{uuid}/{start\|stop\|restart}` | Owner/operator + same-origin + CSRF | Empty JSON object only | 200 or 400/403/404/409 |
| `POST /api/jobs` | Owner/operator + same-origin + CSRF | Idempotency key; GitHub source binds verified commit; Local Folder is Owner-only and binds registered project ID + SHA-256 snapshot + supported target | 202 new / 200 replay; 400/403/404/409/503 |
| `POST /api/jobs/{uuid}/resume` | Owner only + same-origin + CSRF | Owner confirmation required for UNKNOWN job after worker stop/workspace cleanup | 200 public job; 400/403/404/409 |
| `POST /api/jobs/{uuid}/cancel` | Owner only + same-origin + CSRF | Empty JSON object only | 200 public job; 400/403/404/409 |
| `POST /api/jobs/{uuid}/previews` | Owner only + same-origin + CSRF | Job must succeed; static preview has bounded supported fields; Next.js requires explicit `confirm_code_execution=true` and matching build path | 201 preview; 400/403/409/503 |
| `POST /api/runners/{worker-id}/{drain\|enable}` | Owner only + same-origin + CSRF | Empty JSON object only | 200 or 400/403/404 |
| `POST /v1/runner/*` | Runner credential identity, separate from dashboard session | Register/enroll, ping, claim, heartbeat/checkpoint/log/artifact/finish and terminal grant paths are lease-bound; payload validation occurs per route | 200 on accepted operations; 400/401/403/404/409/503 depending on credential, lease and registry state |

### Gateway DELETE

| Route | Authorization | Contract |
|---|---|---|
| `DELETE /api/jobs/{job_uuid}/previews/{preview_uuid}` | Owner + same-origin + session CSRF | Stops the scoped preview and revokes its preview cookie |
| `DELETE /api/infrastructure/{resource_uuid}` | Owner + same-origin + session CSRF | Resource removal is delegated to Infrastructure Manager; missing/conflicting resource is not treated as success |
| `DELETE /api/cloud-runners/{runner_id}` | Owner + same-origin + session CSRF | Provider lifecycle request; provider and provisioning gates remain enforced |

### Auth Proxy boundary and query validation

- Auth Proxy owns the browser cookie session and CSRF/Origin checks; it does not trust browser-supplied role claims. Gateway repeats identity and role authorization for the actual operation.
- GET is an explicit allowlist/regex forwarding surface. Unsupported paths or query strings return 404 rather than being forwarded generically.
- Allowed query shapes include GitHub refs exactly `kind=branches` or `kind=tags`; Infrastructure catalog exactly `view=catalog`; job list `limit=1..200`; logs with `after_id <= 9223372036854775807` and `limit <= 500`.
- Preview content uses a separate authenticated preview cookie and bounded response size. Artifact download is separately validated for attachment disposition, SHA-256 ETag and bounded response.
- POST and DELETE require exact same-origin, session-bound CSRF and reject query strings. Login uses a pre-authentication CSRF session, validates username/password types and limits failed attempts to five per IP in a 15-minute window. Job cancel, infrastructure lifecycle and runner drain/enable accept an empty object only.
- Both handlers implement GET, POST, DELETE and OPTIONS; OPTIONS returns 405. No PUT/PATCH handler is present in these modules.

### Remaining WP-00B gaps after this pass

1. Full request/response JSON schema and field constraints for every route (including Runner credential routes).
2. Exact Auth Proxy `ALLOWED_GET` constant and one-to-one comparison with every Gateway GET route, including routes intentionally inaccessible from Dashboard.
3. Full Gateway handler-to-service method call graph and exception/status mapping for all branches.
4. Dashboard event listener → frontend function → API call → Gateway branch → service method mapping for every control.
5. Automated extraction or regression test that detects route inventory drift.

The above is a route/auth/status-family pass, not a claim that every API schema is complete.

## 2026-11-20 — WP-00B Dashboard 23-view candidate reconciliation

- Main baseline has 23 distinct `data-tab` navigation IDs and 21 Code Navigator records.
- PR #151 head `87b2c4dd48c6ad21fdeb8fa9cd79173f4409de92` adds the missing `project-import` and `document-generator` mappings; its candidate mapping count is 23.
- Project Import mapping declares 18 DOM IDs and its session/catalog/refs/commit-inspection/local-project handlers. It is read-only and binds GitHub source to a verified commit SHA or Local Folder to a snapshot SHA-256.
- Document Generator mapping declares 25 DOM IDs and its browser generation/download plus optional Owner-scoped Document Workflow grant/proposal/approval handlers. A browser download is not a repository write; a local write requires separate scoped grant, exact proposal digest confirmation and read-back verification.
- PR #151 adds navigation-vs-mapping and declared test-reference validation. Its head CI is not accepted as PASS while the shared Windows dynamic-port bootstrap job fails.
- The 23-view mapping is candidate-verified on PR #151 only; main remains at 21 mappings until an Owner-approved merge.


## 2026-11-20 — WP-00B strict request schemas and Auth Proxy allowlist

### Auth Proxy literal GET allowlist

The mainline `ALLOWED_GET` constant is exactly:
- `/api/cloud-runners/status`
- `/api/cloud-runners`
- `/api/local-projects`
- `/api/local-projects/roots`
- `/api/github/repositories`
- `/api/infrastructure/gates`
- `/api/runners`
- `/api/terminal/templates`
- `/api/infrastructure`

Additional GET paths are admitted only by explicit regex/condition branches:
- GitHub repository refs, commits and project inspection with bounded owner/repo segments and 40-hex commit SHA.
- Local Project UUID detail.
- Job UUID detail, artifacts, events and bounded logs.
- Custom Terminal template event IDs.
- Infrastructure UUID detail/events.
- Cloud Runner UUID-like detail path.
- Artifact download UUID path.
- Job preview list/status/content paths, with separate preview-cookie handling.

The Auth Proxy checks the parsed query string separately. Unsupported query combinations are rejected with 404 before Gateway forwarding. The Gateway remains the authorization authority; the proxy's allowlist is only a forwarding boundary.

### Exact body-key constraints confirmed in Gateway source

| Route | Exact JSON keys / constraints | Authorization and result |
|---|---|---|
| `POST /api/document-workflow/grants` | Exactly `project_id`, `allowed_paths`, `confirmation` | Owner + Origin + CSRF; 201 `{grant}` |
| `POST /api/document-workflow/grants/{uuid}/revoke` | Exactly `confirmation` | Owner + Origin + CSRF; 200 `{grant}` |
| `POST /api/document-workflow/proposals` | Exactly `project_id`, `relative_path`, `content`, `expected_sha256` | Owner + Origin + CSRF; 201 `{proposal}` |
| `POST /api/document-workflow/proposals/{uuid}/approve` | Exactly `content_sha256`, `confirmation` | Owner + Origin + CSRF; 200 `{write}`; service verifies exact digest and read-back |
| `POST /api/terminal/templates/{custom-id}/review` | Exactly `decision`, `confirmation`, `source_sha256` | Owner + Origin + CSRF; 200 `{template}`; 404/409/400 domain branches |
| `POST /api/infrastructure/gates/{gate}` | `enabled` and `confirmation` are consumed by the gate store; unknown-key rejection is not established at the HTTP handler | Owner + Origin + CSRF; 200 `{gate}`; readiness and confirmation rechecked by store |
| `POST /api/terminal/commands/preview` | Validated by `validate_preview_payload`; only `template_id` and `parameters` are accepted by its contract test | Owner/operator + Origin + CSRF; 200 `{preview,execution_enabled}`; preview never launches a process |
| `POST /api/jobs` Local Folder | Exactly `source_type`, `project_id`, `snapshot_sha256`, `target`; project ID UUID and snapshot lowercase 64-hex SHA-256 | Owner only + Origin + CSRF; 202 new / 200 idempotent replay |
| `POST /api/jobs/{uuid}/resume` | Exactly `confirmation` with literal `RESUME UNKNOWN JOB AFTER WORKER STOPPED AND WORKSPACE CLEANED` | Owner only + Origin + CSRF; 200 public job |
| `POST /api/jobs/{uuid}/cancel` | Empty JSON object only | Owner only + Origin + CSRF; 200 public job |
| `POST /api/jobs/{uuid}/previews` | Static: only `runtime_kind` and optional `output_relative`; Next.js: exactly `runtime_kind` and `confirm_code_execution=true` | Owner only + Origin + CSRF; job must have succeeded; 201 preview |
| `POST /api/runners/{worker-id}/{drain\|enable}` | Empty JSON object only | Owner only + Origin + CSRF |
| Runner credential `POST /v1/runner/{route}` | Route-specific payload; includes host OS/capabilities, lease seconds, checkpoint sequence/checkpoint, log message/stream, finish outcome/result/error code, artifact content length and Terminal authorization ID | Runner credential + registered worker/job lease; 401/409/403/400/413/415/503 branches |

**Important schema limitation:** The infrastructure gate handler reads `enabled` and `confirmation` but does not enforce an exact key set at the HTTP layer. The gate store must be inspected and tests must prove unknown fields cannot influence behavior. This remains a specific WP-00B schema-validation item, not an assumed PASS.

### Test links for these route contracts

- Local Auth Proxy forwarding allowlist and mutation boundaries: `tests/test_local_auth_proxy_project_routes.py` (19 test methods, including allow/deny GET paths, bounded query, artifact digest headers, Owner CSRF mutations, idempotency forwarding and exact empty-body enforcement).
- Document Workflow exact-scope and digest contract: `tests/test_document_workflow_gateway.py` (11 methods).
- Terminal catalog and typed preview: `tests/test_cloud_gateway_terminal_catalog.py` (7 methods).
- Infrastructure and gate authorization: `tests/test_cloud_gateway_infrastructure_api.py` (16 methods).
- These files are executed by `validate-control-plane.yml` full unittest discovery. The Auth Proxy main module is also explicitly run in `cross-platform-recovery.yml`; the project-routes module is not separately named in that recovery workflow.

### Remaining WP-00B schema work

- Inspect `validate_preview_payload`, infrastructure gate store schema and every runner credential handler to capture nested types, bounds, unknown-key policy and error statuses.
- Enumerate all request/response object fields for non-GET endpoints.
- Add automated contract tests for route allowlist parity and exact request field sets where source currently accepts unknown keys.
