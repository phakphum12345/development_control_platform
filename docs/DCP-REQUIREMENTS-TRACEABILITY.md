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
| IMP-01 GitHub App intake | WS-03 | `tools/cloud_gateway/github_app.py`, `github_app_runtime.py`, `public_github.py` | `tests/test_cloud_gateway_github_app.py`, `tests/test_public_github_catalog.py` | Validate Control Plane; Local-first Minimal Emulator | PARTIAL |
| IMP-02 Local Folder intake | WS-04 | `tools/local_runner_agent/local_project.py`, `checkout.py`, `file_safety.py` | `tests/test_local_project_registry.py`, `tests/test_local_project_snapshot.py`, `tests/test_local_runner_checkout.py`, `tests/test_local_auth_proxy_project_routes.py` | Cross-platform Recovery; Validate Control Plane | PARTIAL |
| IMP-03 Project intelligence | WS-08 | `tools/project_intelligence.py`, `tools/dcp_project_intelligence.py`, `tools/architecture_planner.py` | `tests/test_project_intelligence.py`, `tests/test_architecture_planner.py` | Validate Control Plane | PARTIAL |
| BUILD-01/02 Build adapters | WS-08 | `tools/local_runner_agent/web_build.py`, `pipeline.py` | `tests/test_local_web_build.py`, `tests/test_local_runner_pipeline_e2e.py` | Validate Control Plane; Cross-platform Recovery | PARTIAL |
| RUN-01/02 Runtime and Preview | WS-09 | `tools/local_runner_agent/runtime.py`, `tools/cloud_gateway/preview.py`, `tools/local_auth_proxy.py` | `tests/test_local_runtime.py`, `tests/test_authenticated_preview.py`, `tests/test_local_auth_proxy.py` | Validate Control Plane | PARTIAL |
| TERM-01–05 Terminal | WS-10 | `tools/cloud_gateway/terminal_catalog.py`, `terminal_grants.py`, `terminal_execution_contract.py`, `tools/local_runner_agent/terminal_executor.py` | `tests/test_terminal_command_pack_schema.py`, `tests/test_terminal_execution_contract.py`, `tests/test_terminal_grants.py`, `tests/test_terminal_executor.py` | Validate Control Plane; Cross-platform Recovery | BLOCKED for process execution |
| OSI-Linux | WS-11 | `tools/local_runner_agent/linux_sandbox.py`, `terminal_isolation.py` | `tests/test_linux_sandbox.py`, `tests/test_terminal_isolation.py` | Cross-platform Recovery | BLOCKED for production execution pending host acceptance |
| OSI-Windows / PSEC | WS-12 | No Windows PSEC launcher in main; PR #140/#149 branches contain candidate code | `tests/test_windows_psec*.py` exist on PR branches, not main | Windows PSEC API Availability Probe; Windows host acceptance | BLOCKED |
| OSI-macOS | WS-11 | Design and cloud runner adapter documentation; no signed native isolation helper evidenced | No complete host acceptance test evidenced | macOS Cloud Runner (manual provisioning path) | BLOCKED |
| ART-01 Artifact integrity | WS-13 | `tools/cloud_gateway/artifacts.py`, `tools/local_runner_agent/artifacts.py` | `tests/test_cloud_gateway_artifacts.py`, `tests/test_cloud_gateway_artifact_download.py`, `tests/test_local_runner_artifacts.py` | Validate Control Plane; Cross-platform Recovery | EXISTING / PARTIAL |
| TEST-01/02 Browser | WS-14 | `tools/local_runner_agent/browser_test.py`, Dashboard browser scripts | `tests/test_browser_test.py`, `tests/test_local_auth_proxy.py`, `tests/browser_smoke.mjs` | Validate Control Plane | PARTIAL |
| UI Dashboard | WS-15 | `dashboard/index.html`, `dashboard/recon-back-box/index.html` | `tests/test_dashboard_contract.py`, `tests/test_dashboard_document_lifecycle_contract.py`, `tests/test_recon_api.py` | Validate Control Plane; Local-first Minimal Emulator | PARTIAL |
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
