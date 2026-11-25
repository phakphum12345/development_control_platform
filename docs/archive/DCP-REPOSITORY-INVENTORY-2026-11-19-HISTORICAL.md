# DCP Repository Inventory — 2026-11-19

**Repository:** `phakphum12345/development_control_platform`  
**Default branch:** `main`  
**Exact baseline SHA:** `985a78d5fba459c8a0cbcf47e5d00a858c6e6228`  
**Audit date:** 2026-11-19 (Asia/Bangkok)  
**Protocol:** DCP-CEEP v1.0 — adopted  
**Audit state:** IN_PROGRESS — path inventory and selected architecture inspection completed; full symbol/handler/test-function trace remains open.

## 1. Baseline facts

| Item | Observed value | Evidence boundary |
|---|---:|---|
| Git tree entries | 309 | Recursive Git tree for exact main SHA above |
| Files (blobs) | 283 | Recursive Git tree; path inventory |
| `tools/` files | 81 | Path inventory |
| `tests/` files | 91 | Includes Python, PowerShell and browser scripts |
| `docs/` files | 63 | Path inventory |
| GitHub Actions workflows | 8 | Workflow files listed below |
| JSON/OpenAPI schemas | 3 | `schemas/` |
| Branches | 158 | GitHub branch search paginated: 100 + 58; final cursor empty |
| Open pull requests | 3 | GitHub REST open PR list |
| Open issues | 0 | GitHub REST open issue list |
| Closed issues | 0 | GitHub REST closed issue list returned no issue records |
| Main branch protection | Not enabled/reported | GitHub branch API returned `protected=false`; do not assume required checks are enforced by branch protection |
| Repository visibility | Public | GitHub repository metadata |

The counts are a new baseline and supersede older inventory counts tied to `62d72bddd028399d0b96cd9c2f6e3b16a704b758` or earlier commits. Historical audit documents remain historical evidence and are not rewritten.

## 2. Open pull request register

| PR | State | Head | Base | Current audit finding |
|---|---|---|---|---|
| [#140](https://github.com/phakphum12345/development_control_platform/pull/140) | OPEN / DRAFT | `8bf0b74859c3749070eafbd7906d9c7df6d0822b` | `main` at `985a78d5fba459c8a0cbcf47e5d00a858c6e6228` | Windows PSEC filesystem authorization; workflows completed successfully, but hosted PSEC probe reports BLOCKED and optional self-hosted Windows acceptance is SKIPPED |
| [#149](https://github.com/phakphum12345/development_control_platform/pull/149) | OPEN / DRAFT | `44ec9f4b95601071b172a9b541387399591745b7` | `work/wp18b1-windows-psec-filesystem-authorization`; PR's recorded base SHA is stale (`59961b3cc96bb619126ae7d4b193410bd83ada5d`) | Trusted Python base runtime; overlaps #140 launcher/tests; branch comparison against current #140 head reports 71 ahead / 7 behind and 9 changed files; history is divergent, so do not merge blindly |
| [#138](https://github.com/phakphum12345/development_control_platform/pull/138) | OPEN | Fork head `main` | `work/wp18b1-windows-psec-filesystem-authorization` | Cross-fork PR with reversed-looking main-to-feature direction; body records 501 ahead / 472 behind and mergeable=false at reconciliation; treat as comparison/reference, never merge wholesale |

No review threads or submitted reviews were returned for PR #140 or #149 in this audit. This does not replace a fresh review immediately before any future merge.

## 3. Workflow inventory

- `.github/workflows/cloud-gateway-live-smoke.yml`
- `.github/workflows/cross-platform-recovery.yml`
- `.github/workflows/deploy-pages.yml`
- `.github/workflows/local-first-emulator.yml`
- `.github/workflows/macos-cloud-runner.yml`
- `.github/workflows/package-release.yml`
- `.github/workflows/static.yml`
- `.github/workflows/validate-control-plane.yml`

## 4. Source tree inventory

### Tools

Total: 81 files.

### tools/ (8)

- `tools/architecture_planner.py`
- `tools/dcp_project_intelligence.py`
- `tools/dev_environment.py`
- `tools/local_auth_proxy.py`
- `tools/local_runner_manager.py`
- `tools/project_intelligence.py`
- `tools/reset_owner_password.py`
- `tools/universal_runner_factory.py`

### tools/cloud_gateway (38)

- `tools/cloud_gateway/__init__.py`
- `tools/cloud_gateway/artifacts.py`
- `tools/cloud_gateway/azure_budget.py`
- `tools/cloud_gateway/azure_egress.py`
- `tools/cloud_gateway/azure_guest_profile.py`
- `tools/cloud_gateway/azure_identity.py`
- `tools/cloud_gateway/azure_provider_runtime.py`
- `tools/cloud_gateway/azure_vm.py`
- `tools/cloud_gateway/budget_guard.py`
- `tools/cloud_gateway/github_app.py`
- `tools/cloud_gateway/github_app_runtime.py`
- `tools/cloud_gateway/github_runner_online.py`
- `tools/cloud_gateway/infrastructure.py`
- `tools/cloud_gateway/infrastructure_gates.py`
- `tools/cloud_gateway/job_control.py`
- `tools/cloud_gateway/key_vault.py`
- `tools/cloud_gateway/local_mode.py`
- `tools/cloud_gateway/oidc_assertion.py`
- `tools/cloud_gateway/oidc_edge_signer.py`
- `tools/cloud_gateway/orka.py`
- `tools/cloud_gateway/orka_bootstrap.py`
- `tools/cloud_gateway/policy.py`
- `tools/cloud_gateway/preflight.py`
- `tools/cloud_gateway/preview.py`
- `tools/cloud_gateway/provider_router.py`
- `tools/cloud_gateway/runner_bootstrap.py`
- `tools/cloud_gateway/runner_cleanup.py`
- `tools/cloud_gateway/runner_registry.py`
- `tools/cloud_gateway/scheduler.py`
- `tools/cloud_gateway/server.py`
- `tools/cloud_gateway/service.py`
- `tools/cloud_gateway/sqlite_security.py`
- `tools/cloud_gateway/store.py`
- `tools/cloud_gateway/terminal_authorization.py`
- `tools/cloud_gateway/terminal_catalog.py`
- `tools/cloud_gateway/terminal_execution_contract.py`
- `tools/cloud_gateway/terminal_grants.py`
- `tools/cloud_gateway/terminal_templates.py`

### tools/cloud_runner (3)

- `tools/cloud_runner/__init__.py`
- `tools/cloud_runner/__main__.py`
- `tools/cloud_runner/backend.py`

### tools/document_workflow (3)

- `tools/document_workflow/__init__.py`
- `tools/document_workflow/gateway.py`
- `tools/document_workflow/writer.py`

### tools/local_image_lab (2)

- `tools/local_image_lab/__init__.py`
- `tools/local_image_lab/backend.py`

### tools/local_runner_agent (17)

- `tools/local_runner_agent/__init__.py`
- `tools/local_runner_agent/__main__.py`
- `tools/local_runner_agent/artifacts.py`
- `tools/local_runner_agent/browser_test.py`
- `tools/local_runner_agent/checkout.py`
- `tools/local_runner_agent/client.py`
- `tools/local_runner_agent/execution.py`
- `tools/local_runner_agent/file_safety.py`
- `tools/local_runner_agent/linux_sandbox.py`
- `tools/local_runner_agent/local_project.py`
- `tools/local_runner_agent/pipeline.py`
- `tools/local_runner_agent/runtime.py`
- `tools/local_runner_agent/service.py`
- `tools/local_runner_agent/terminal_executor.py`
- `tools/local_runner_agent/terminal_isolation.py`
- `tools/local_runner_agent/web_build.py`
- `tools/local_runner_agent/workspace.py`

### tools/mcp_engine (3)

- `tools/mcp_engine/__init__.py`
- `tools/mcp_engine/engine.py`
- `tools/mcp_engine/server.py`

### tools/runner_agent (3)

- `tools/runner_agent/README.md`
- `tools/runner_agent/agent.py`
- `tools/runner_agent/preflight.py`

### tools/runner_backend (4)

- `tools/runner_backend/__init__.py`
- `tools/runner_backend/cloud_api.py`
- `tools/runner_backend/manager.py`
- `tools/runner_backend/provider.py`

### Tests

Total: 91 files. This is a path-level inventory; the number of individual test methods and their exact requirement mapping is not yet certified.

- `tests/browser_smoke.mjs`
- `tests/emit_runner_bootstrap_scripts.py`
- `tests/live_gateway_preflight.py`
- `tests/test_architecture_planner.py`
- `tests/test_authenticated_preview.py`
- `tests/test_browser_test.py`
- `tests/test_cloud_gateway.py`
- `tests/test_cloud_gateway_artifact_download.py`
- `tests/test_cloud_gateway_artifacts.py`
- `tests/test_cloud_gateway_azure_egress.py`
- `tests/test_cloud_gateway_azure_guest_profile.py`
- `tests/test_cloud_gateway_azure_provider_runtime.py`
- `tests/test_cloud_gateway_azure_security.py`
- `tests/test_cloud_gateway_azure_vm.py`
- `tests/test_cloud_gateway_budget_lifecycle.py`
- `tests/test_cloud_gateway_dynamic_port.py`
- `tests/test_cloud_gateway_github_app.py`
- `tests/test_cloud_gateway_infrastructure.py`
- `tests/test_cloud_gateway_infrastructure_api.py`
- `tests/test_cloud_gateway_infrastructure_gates.py`
- `tests/test_cloud_gateway_job_control.py`
- `tests/test_cloud_gateway_local_mode.py`
- `tests/test_cloud_gateway_local_projects.py`
- `tests/test_cloud_gateway_oidc_edge_signer.py`
- `tests/test_cloud_gateway_oidc_ingress_contract.py`
- `tests/test_cloud_gateway_orka.py`
- `tests/test_cloud_gateway_orka_bootstrap.py`
- `tests/test_cloud_gateway_preflight.py`
- `tests/test_cloud_gateway_provider_budget.py`
- `tests/test_cloud_gateway_provider_router.py`
- `tests/test_cloud_gateway_proxy_authorization.py`
- `tests/test_cloud_gateway_runner_bootstrap.py`
- `tests/test_cloud_gateway_runner_cleanup.py`
- `tests/test_cloud_gateway_runner_registry.py`
- `tests/test_cloud_gateway_runner_terminal_grant.py`
- `tests/test_cloud_gateway_runtime.py`
- `tests/test_cloud_gateway_scheduler_integration.py`
- `tests/test_cloud_gateway_terminal_catalog.py`
- `tests/test_cloud_gateway_terminal_templates.py`
- `tests/test_cloud_runner_backend.py`
- `tests/test_cloud_runner_dashboard_contract.py`
- `tests/test_cloud_runner_e2e_acceptance.py`
- `tests/test_cloud_runner_openapi.py`
- `tests/test_cloud_runner_user_api.py`
- `tests/test_cloud_runner_workflow_client.py`
- `tests/test_dashboard_contract.py`
- `tests/test_dashboard_document_lifecycle_contract.py`
- `tests/test_dashboard_dynamic_port.ps1`
- `tests/test_dashboard_launcher.ps1`
- `tests/test_dashboard_launcher_contract.py`
- `tests/test_dev_environment.py`
- `tests/test_document_workflow_gateway.py`
- `tests/test_document_workflow_writer.py`
- `tests/test_linux_sandbox.py`
- `tests/test_live_gateway_preflight.py`
- `tests/test_local_auth_proxy.py`
- `tests/test_local_auth_proxy_project_routes.py`
- `tests/test_local_browser_testing.py`
- `tests/test_local_image_lab.py`
- `tests/test_local_project_cli.py`
- `tests/test_local_project_registry.py`
- `tests/test_local_project_snapshot.py`
- `tests/test_local_runner_agent.py`
- `tests/test_local_runner_bootstrap.ps1`
- `tests/test_local_runner_checkout.py`
- `tests/test_local_runner_cli.py`
- `tests/test_local_runner_execution.py`
- `tests/test_local_runner_hardlink_containment.py`
- `tests/test_local_runner_launcher_contract.py`
- `tests/test_local_runner_legacy_launcher_contract.py`
- `tests/test_local_runner_manager.py`
- `tests/test_local_runner_pipeline_e2e.py`
- `tests/test_local_runner_readiness.py`
- `tests/test_local_runner_service.py`
- `tests/test_local_runner_workspace.py`
- `tests/test_local_runtime.py`
- `tests/test_local_web_build.py`
- `tests/test_native_mcp_engine.py`
- `tests/test_native_mcp_server.py`
- `tests/test_project_intelligence.py`
- `tests/test_release_packaging.py`
- `tests/test_reset_owner_password.py`
- `tests/test_runner_agent.py`
- `tests/test_runner_agent_gateway_e2e.py`
- `tests/test_runner_preflight.py`
- `tests/test_sqlite_security.py`
- `tests/test_terminal_command_pack_schema.py`
- `tests/test_terminal_execution_contract.py`
- `tests/test_terminal_executor.py`
- `tests/test_terminal_grants.py`
- `tests/test_terminal_isolation.py`

### Documentation

Total: 63 files.

- `docs/DCP-ACCEPTANCE-TEST-PLAN.md`
- `docs/DCP-ARCHITECTURE.md`
- `docs/DCP-AUTHENTICATED-PREVIEW.md`
- `docs/DCP-CEEP-COMMAND-REFERENCE.md`
- `docs/DCP-CEEP-PROTOCOL.md`
- `docs/DCP-CEEP-UNIVERSAL-v2.0.md`
- `docs/DCP-CEEP-V2-MIGRATION.md`
- `docs/DCP-COMMAND-LIBRARY.md`
- `docs/DCP-IMPLEMENTATION-ROADMAP.md`
- `docs/DCP-LOCAL-FOLDER-BUILD.md`
- `docs/DCP-MASTER-FEATURE-BACKLOG.md`
- `docs/DCP-MASTER-PROJECT-PLAN.md`
- `docs/DCP-PLAYWRIGHT-TESTING.md`
- `docs/DCP-REMAINING-WORK-INVENTORY.md`
- `docs/DCP-REPOSITORY-AUDIT-2026-11-11.md`
- `docs/DCP-REPOSITORY-AUDIT-2026-11-12.md`
- `docs/DCP-SECURITY-AND-SAFETY-POLICY.md`
- `docs/DCP-TERMINAL-API.md`
- `docs/DCP-TERMINAL-EXECUTION-ARCHITECTURE.md`
- `docs/DCP-TERMINAL-OS-ISOLATION.md`
- `docs/DCP-TERMINAL-RUNNER-SETUP.md`
- `docs/DCP-TERMINAL-SECURITY.md`
- `docs/DCP-TERMINAL-STUDIO.md`
- `docs/IMPLEMENTATION-STATUS.md`
- `docs/INDEX.md`
- `docs/REQUIREMENTS-TRACEABILITY.md`
- `docs/authentication-deployment.md`
- `docs/azure-identity-keyvault-budget.md`
- `docs/azure-production-deployment.md`
- `docs/azure-runner-bootstrap.md`
- `docs/azure-vm-provisioner.md`
- `docs/cloud-gateway-core.md`
- `docs/cloud-runner-architecture.md`
- `docs/cloud-runner-completion-audit-2026-11-12.md`
- `docs/cloud-runner-control-plane.md`
- `docs/cloud-runner-lifecycle-cleanup.md`
- `docs/cloud-runner-user-api.md`
- `docs/dcp-own-infrastructure-roadmap.md`
- `docs/dcp-own-platform-architecture.md`
- `docs/document-generator-operations.md`
- `docs/gateway-deployment-preflight.md`
- `docs/github-app-runner-bootstrap.md`
- `docs/infrastructure-manager.md`
- `docs/live-cloud-gateway-acceptance.md`
- `docs/local-auth-proxy-dashboard-routes.md`
- `docs/local-first-mode.md`
- `docs/local-image-lab.md`
- `docs/local-job-control-plane.md`
- `docs/local-owner-password-reset.md`
- `docs/local-runner-manager.md`
- `docs/macos-cloud-runner-control-plane.md`
- `docs/native-mcp-engine-test-plan.md`
- `docs/native-mcp-engine.md`
- `docs/oidc-ingress.md`
- `docs/orka-adapter.md`
- `docs/runner-scheduler.md`
- `docs/security-readiness-audit-2026-11-08.md`
- `docs/selective-code-monitor-editor.md`
- `docs/self-learning-runner-platform.md`
- `docs/templates/DCP-CEEP-PROJECT-PROFILE.md`
- `docs/web-build-engine.md`
- `docs/windows-11-one-click.md`
- `docs/windows-11-self-hosted.md`

## 5. Architecture-critical files inspected in this pass

| Area | Files | Inspection result |
|---|---|---|
| Gateway | `tools/cloud_gateway/server.py`, `service.py`, `store.py`, `job_control.py` (tree and selected source) | HTTP server and service/control-plane surface exist; full method/path/role matrix remains open |
| Local Auth Proxy | `tools/local_auth_proxy.py` | Same-origin local authentication proxy exists; complete route-to-handler-to-Gateway trace remains open |
| Local Runner | `tools/local_runner_agent/pipeline.py`, `workspace.py`, `execution.py`, `runtime.py` | Snapshot/build/runtime/workspace pipeline exists in constrained slices; real host acceptance remains separate |
| Terminal security | `tools/local_runner_agent/terminal_isolation.py`, `terminal_executor.py`, `linux_sandbox.py` | Fail-closed isolation assessment exists; no platform is promoted to production VERIFIED by this inventory |
| Artifacts | `tools/cloud_gateway/artifacts.py`, Runner artifact modules | SHA-256 upload/download integrity implementation and tests exist; full user-journey provenance remains partial |
| Dashboard | `dashboard/index.html` (2,639 lines at baseline) | Static Dashboard contains multiple functional views and handlers; 334 element IDs were observed, not 334 views; complete view/action/API mapping remains open |
| Schemas | `schemas/cloud-runner-gateway.openapi.yaml`, `project-state.schema.json`, `terminal-command-pack.schema.json` | Three schema assets present; contract-to-handler completeness still requires validation |
| Packaging | `packaging/package-release.ps1`, `packaging/windows/DCP.iss` | Windows package workflow and installer definition exist; install/upgrade/rollback acceptance remains incomplete |

## 6. Repository protocol and history

- `docs/DCP-CEEP-PROTOCOL.md` identifies CEEP v1.0 as adopted.
- CEEP v2.0 remains a proposal and is not adopted.
- `checkpoints/DCP-CEEP-CONTINUITY.md` is the mandatory resume ledger.
- Older inventory/status/traceability documents use the 2026-11-14 baseline SHA and are stale for current counts.
- `docs/DCP-REPOSITORY-AUDIT-2026-11-11.md` and `...2026-11-12.md` are historical, SHA-scoped audits and must remain unchanged.

## 7. Limits of this audit

Completed in this pass:
- Captured exact recursive tree and all file paths.
- Paginated branch search to completion (158 branches).
- Inspected all open PR metadata and current #140/#149 branch relationships.
- Inspected all current workflow definitions at a structural level.
- Inspected selected architecture, security, continuity and backlog sources.
- Inspected current PR workflow job results and the PSEC probe log.

Still IN_PROGRESS:
- Read every source file in full and map public symbols/callers.
- Enumerate every Gateway and Auth Proxy HTTP method/path and its auth/role/CSRF rules.
- Map every Dashboard view, event handler, API call, backend function and test.
- Enumerate test functions, fixtures, skips and workflow/job coverage for all 91 test files.
- Reconcile every roadmap/backlog claim with current source and exact-head CI.
- Inspect relevant closed PRs and all historical branch ancestry before deciding which branch work is still valuable.

No source-code behavior was changed by this audit document set. No local test suite, deployment, cloud provisioning, VM creation or release was run.


## 8. Refined Dashboard and HTTP dispatch inventory

A second source pass inspected Gateway/Auth Proxy dispatch branches and the Dashboard navigation source:

- Dashboard has **23 distinct `data-tab` values**: `home`, `account`, `project-import`, `terminal-studio`, `code-navigator`, `cloud-runners`, `infrastructure`, `dev-tools`, `ui-routes`, `ui-simulator`, `route-colors`, `github-api`, `repo-selector`, `repo`, `pr`, `user`, `workspace`, `evidence`, `gates`, `checkpoint`, `document-generator`, `audit`, `contact`.
- The in-page `CODE_NAV_MAPPINGS` contains 21 explicit mappings, so it does not currently map every one of the 23 navigation tabs. The historical inventory's older 21-view count is superseded by this source-derived count.
- `dashboard/index.html` has 334 observed element IDs; these are DOM IDs, not view count.
- Gateway and Auth Proxy use `BaseHTTPRequestHandler` dispatch, not Flask-style decorators. Route extraction must inspect `do_GET`, `do_POST`, and `do_DELETE`.

### Gateway dispatch families (source: `tools/cloud_gateway/server.py`)

| Method | Path family | Observed authorization boundary |
|---|---|---|
| GET | `/healthz` | Public health response |
| GET | `/api/auth/session` | Requires validated proxy identity; returns session role and CSRF token |
| GET | `/api/github/repositories`, repository refs/commit inspection | Requires validated proxy identity; repository access is delegated to the configured GitHub App service/authorizer |
| GET | `/api/local-projects`, `/roots`, `/{project_id}` | Owner only |
| GET | `/api/document-workflow/grants`, `/target`, proposal lookup | Owner only |
| GET | `/api/terminal/templates`, terminal events | Owner/operator |
| GET | `/api/jobs`, `/{job_id}`, logs and preview metadata | Owner/operator; selected preview controls require Owner |
| GET | `/api/runners`, `/api/infrastructure/gates`, `/api/infrastructure[/...]` | Owner/operator |
| GET | `/api/artifacts/{artifact_id}/download` | Owner/operator |
| GET | `/api/cloud-runners/status`, collection and item | Validated dashboard identity; verify exact item policy in full endpoint matrix |
| POST | `/api/terminal/jobs`, `/api/terminal/authorize`, grant revoke | Owner + same-origin + CSRF |
| POST | `/api/document-workflow/grants`, grant revoke, proposals and approve | Owner + same-origin + CSRF |
| POST | `/api/terminal/templates/import`, template review | Owner + same-origin + CSRF |
| POST | `/api/terminal/commands/preview` | Owner/operator + same-origin + CSRF |
| POST | `/api/infrastructure`, gate changes and actions | Owner/operator for general actions; Owner for gate mutation; same-origin + CSRF |
| POST | `/api/jobs`, `/{job_id}/resume`, `/{job_id}/cancel`, preview start | Owner/operator + same-origin + CSRF; Local Folder creation, resume and cancellation have additional Owner checks |
| POST | `/api/runners/{worker_id}/drain|enable` | Owner + same-origin + CSRF |
| POST | `/v1/runner/register`, `enroll`, `ping`, `claim` and job lease routes | Runner credential identity, not browser Owner session |
| DELETE | `/api/jobs/{job_id}/previews/{preview_id}` | Owner + same-origin + CSRF |
| DELETE | `/api/infrastructure/{resource_id}` | Owner + same-origin + CSRF |
| DELETE | `/api/cloud-runners/{runner_id}` | Owner + same-origin + CSRF |

Source line anchors at this baseline: Gateway `do_GET` begins near line 327, `do_POST` near 815 and `do_DELETE` near 1569; Auth Proxy `do_GET` near 517, `do_POST` near 676 and `do_DELETE` near 869. This is a route-family map, not yet the final exhaustive path/query/body schema.

### Auth Proxy dispatch families (source: `tools/local_auth_proxy.py`)

- GET: `/healthz`, `/api/auth/session`, allowlisted read-only API paths for GitHub catalog/refs, Jobs/logs, artifacts, terminal events, infrastructure resources, Local Projects and Cloud Runner resources, plus static Dashboard assets.
- POST: `/api/auth/login`, `/api/auth/logout`, Jobs create/resume/cancel, preview start, infrastructure/gate actions, Cloud Runner requests, Terminal template import/review/command preview and Runner drain/enable.
- DELETE: preview stop, infrastructure resource delete and Cloud Runner delete.
- Proxy mutation paths enforce same-origin and session-bound CSRF before forwarding. Exact role requirements and all forwarded body/header fields still need a dedicated per-route contract table.

This second pass supersedes the earlier README-derived 21-view estimate with the current source-derived 23 navigation tabs.


## 9. HTTP path-family coverage update

The 2026-11-19 source pass now records concrete Gateway GET/POST/DELETE route shapes, Runner credential endpoints, Auth Proxy read allowlists, bounded query rules and same-origin/CSRF checks in `DCP-REQUIREMENTS-TRACEABILITY.md`. Gateway and Auth Proxy each expose GET/POST/DELETE handler dispatch; no PUT/PATCH handler was found. Exact request/response schemas, all error statuses, and the full Proxy allowlist equivalence table remain IN_PROGRESS.


### Dashboard Code Navigator coverage check
- Current navigation: 23 distinct `data-tab` values.
- Declared `CODE_NAV_MAPPINGS`: 21 entries.
- Unmapped navigation tabs: `project-import` and `document-generator`.
- The 21 mapping records declare 48 test references; every referenced test file path exists on current main.
- The 48 references are declared associations, not evidence that all 48 test functions ran on this audit branch.


---

## Historical-baseline notice — 2026-11-25

This archived document preserves the detailed WP-00 work product originally authored against main SHA `985a78d5fba459c8a0cbcf47e5d00a858c6e6228`. Its counts, PR heads, check results and implementation statements are historical and must not be treated as current-main facts. The refreshed current baseline is main SHA `57589873583c706d4af9756709596fdba7c22de9`; see [DCP Live Repository Audit 2026-11-25](../DCP-LIVE-REPOSITORY-AUDIT-2026-11-25.md). Preserve this file for its source-level route, test, workflow and architecture detail; reconcile each claim before reusing it.
