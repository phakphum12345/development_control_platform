# DCP Requirements Traceability

**Repository:** `phakphum12345/development_control_platform`  
**Protocol:** DCP-CEEP v1.0 — Adopted  
**Baseline:** `main` at `62d72bddd028399d0b96cd9c2f6e3b16a704b758`  
**Status:** IN_PROGRESS — first-pass source/test mapping; atomic acceptance criteria remain open

## 1. Traceability rules

- Source presence is implementation evidence, not acceptance evidence.
- A test file is not a pass result. Record exact CI run, job, commit SHA and test output.
- GitHub-hosted CI does not prove a user's local Windows/Linux/macOS host.
- SKIPPED, UNKNOWN, missing, stale or different-SHA evidence is never PASS.
- Every new WP must map to source, tests, workflow, docs, owner gate and acceptance evidence.

## 2. Requirement-to-source/test map

| Requirement | Source boundary | Test evidence in repository | Remaining acceptance |
|---|---|---|---|
| RQ-001 Gateway health/API safety | `tools/cloud_gateway/server.py`, `service.py` | `test_cloud_gateway.py`, `test_cloud_runner_openapi.py` | Full method/path/auth matrix and deployed API acceptance |
| RQ-002 Owner authentication and proxy identity | `tools/local_auth_proxy.py`, `server.py` | `test_local_auth_proxy.py`, `test_local_auth_proxy_project_routes.py`, `test_cloud_gateway_proxy_authorization.py` | Real Windows host Dashboard → Proxy → Gateway acceptance |
| RQ-003 GitHub App repository catalog and import | `github_app.py`, `github_app_runtime.py`, `service.py`, Local Project Registry | `test_cloud_gateway_github_app.py`, `test_cloud_gateway_local_projects.py`, `test_local_project_registry.py`, `test_local_project_snapshot.py` | Live authorized owner flow and full Dashboard import |
| RQ-004 Durable Jobs, leases and checkpoints | `job_control.py`, `store.py`, `scheduler.py` | `test_cloud_gateway_job_control.py`, `test_cloud_gateway_scheduler_integration.py`, `test_cloud_runner_user_api.py` | Independent Runner interruption and host recovery |
| RQ-005 Runner enrollment, claim, heartbeat and cleanup | `runner_registry.py`, `runner_bootstrap.py`, `runner_cleanup.py`, Local Runner client/service | `test_cloud_gateway_runner_registry.py`, `test_cloud_gateway_runner_cleanup.py`, `test_runner_agent.py`, `test_runner_agent_gateway_e2e.py`, `test_local_runner_service.py` | Actual process-tree and workspace cleanup after service interruption |
| RQ-006 Artifact integrity and provenance | `tools/cloud_gateway/artifacts.py`, Local Runner artifact uploader, Proxy download | `test_cloud_gateway_artifacts.py`, `test_cloud_gateway_artifact_download.py`, `test_local_runner_pipeline_e2e.py` | Dashboard end-to-end SHA-256 provenance and download read-back |
| RQ-007 Local Folder trust and immutable snapshots | `local_project.py`, `checkout.py`, `workspace.py` | `test_local_project_cli.py`, `test_local_project_registry.py`, `test_local_project_snapshot.py`, `test_local_runner_checkout.py`, `test_local_runner_workspace.py` | Broader dependency-managed target matrix and real host acceptance |
| RQ-008 Build and framework adapters | `web_build.py`, `execution.py`, `pipeline.py` | `test_local_web_build.py`, `test_local_runner_execution.py`, `test_local_runner_pipeline_e2e.py` | Additional frameworks, dependency install policy, runtime and HMR/WebSocket support |
| RQ-009 Runtime and authenticated preview | `runtime.py`, Gateway `preview.py`, Proxy preview routes | `test_local_runtime.py`, `test_authenticated_preview.py`, `test_local_auth_proxy.py` | Full imported-project preview and runtime process acceptance |
| RQ-010 Browser testing and accessibility | `browser_test.py`, Dashboard HTML/JS | `test_browser_test.py`, `test_local_browser_testing.py`, `browser_smoke.mjs`, `test_dashboard_contract.py` | Trace artifacts, visual regression baselines, full WCAG/axe |
| RQ-011 Terminal typed commands and app grants | Terminal catalog/grants/authorization/executor | `test_terminal_command_pack_schema.py`, `test_terminal_execution_contract.py`, `test_terminal_grants.py`, `test_terminal_executor.py`, `test_cloud_gateway_runner_terminal_grant.py`, `test_cloud_gateway_terminal_catalog.py`, `test_cloud_gateway_terminal_templates.py` | End-to-end authorization and execution after verified OS sandbox acceptance |
| RQ-012 Linux OS isolation | `terminal_isolation.py`; PR #116 adds `linux_sandbox.py` builder | `test_terminal_isolation.py`; PR #116 adds `test_linux_sandbox.py` | Integrate into executor; run real bubblewrap acceptance and adversarial host tests |
| RQ-013 Windows/macOS OS isolation | Native platform helper contracts in `terminal_isolation.py` | `test_terminal_isolation.py` | Windows AppContainer/LPAC and signed macOS helper implementation/acceptance |
| RQ-014 Infrastructure/provider lifecycle and budget gates | `infrastructure.py`, `infrastructure_gates.py`, `azure_*.py`, `orka*.py`, `budget_guard.py` | `test_cloud_gateway_infrastructure.py`, `test_cloud_gateway_infrastructure_api.py`, `test_cloud_gateway_infrastructure_gates.py`, Azure/Orka/budget suites | Explicit live provider acceptance; no implicit paid resources |
| RQ-015 OIDC and trusted proxy security | `oidc_assertion.py`, `oidc_edge_signer.py`, `server.py`, `local_auth_proxy.py` | `test_cloud_gateway_oidc_edge_signer.py`, `test_cloud_gateway_oidc_ingress_contract.py`, `test_cloud_gateway_proxy_authorization.py` | Deployment-specific identity, replay, ingress and key-rotation acceptance |
| RQ-016 Dashboard view/route/navigation contracts | `dashboard/index.html`, PWA shell and local route registry | `test_dashboard_contract.py`, `test_dashboard_launcher_contract.py`, `test_dashboard_document_lifecycle_contract.py`, browser smoke | Keyboard/screen-reader and cross-browser visual acceptance |
| RQ-017 Document generation and durable local writing | `tools/document_workflow/`, Dashboard Document Generator | `test_document_workflow_gateway.py`, `test_document_workflow_writer.py`, `test_dashboard_document_lifecycle_contract.py` | Authenticated Dashboard-to-writer end-to-end and interruption recovery |
| RQ-018 MCP read-only engine | `tools/mcp_engine/` | `test_native_mcp_engine.py`, `test_native_mcp_server.py` | Capability lifecycle and future plugin contract; no browser arbitrary shell |
| RQ-019 Project intelligence and architecture planning | `project_intelligence.py`, `dcp_project_intelligence.py`, `architecture_planner.py` | `test_project_intelligence.py`, `test_architecture_planner.py` | Bounded AI Analyze/Propose/Apply/Verify with owner approval and evidence |
| RQ-020 Developer environment and workspace tools | `dev_environment.py`, `local_runner_manager.py`, Dashboard developer/code navigator views | `test_dev_environment.py`, `test_local_runner_manager.py`, `test_dashboard_contract.py` | Complete editable Developer Workspace and Visual Workflow Builder |
| RQ-021 Local image lab | `tools/local_image_lab/` | `test_local_image_lab.py` | End-to-end UI, storage, safety and recovery acceptance |
| RQ-022 SQLite and data integrity | `sqlite_security.py`, durable stores | `test_sqlite_security.py`, `test_cloud_gateway_job_control.py`, `test_cloud_gateway.py` | Backup/restore and corruption/recovery drills |
| RQ-023 Local runner readiness and launchers | `tools/local_runner_agent/`, setup scripts | `test_local_runner_readiness.py`, `test_local_runner_launcher_contract.py`, PowerShell launcher tests | Actual supported Windows host startup, stop, restart and interruption tests |
| RQ-024 Full DCP self-test, upgrade and rollback | Environment doctor, preflight and control-plane self-check foundations | `test_runner_preflight.py`, `test_local_runner_readiness.py`, `test_dashboard_contract.py` | Signed versioned upgrade, rollback and disaster recovery acceptance |

## 3. Test-file inventory (86 baseline files)

### Cloud Gateway (33)
- `test_cloud_gateway.py`
- `test_cloud_gateway_artifact_download.py`
- `test_cloud_gateway_artifacts.py`
- `test_cloud_gateway_azure_egress.py`
- `test_cloud_gateway_azure_guest_profile.py`
- `test_cloud_gateway_azure_provider_runtime.py`
- `test_cloud_gateway_azure_security.py`
- `test_cloud_gateway_azure_vm.py`
- `test_cloud_gateway_budget_lifecycle.py`
- `test_cloud_gateway_dynamic_port.py`
- `test_cloud_gateway_github_app.py`
- `test_cloud_gateway_infrastructure.py`
- `test_cloud_gateway_infrastructure_api.py`
- `test_cloud_gateway_infrastructure_gates.py`
- `test_cloud_gateway_job_control.py`
- `test_cloud_gateway_local_mode.py`
- `test_cloud_gateway_local_projects.py`
- `test_cloud_gateway_oidc_edge_signer.py`
- `test_cloud_gateway_oidc_ingress_contract.py`
- `test_cloud_gateway_orka.py`
- `test_cloud_gateway_orka_bootstrap.py`
- `test_cloud_gateway_preflight.py`
- `test_cloud_gateway_provider_budget.py`
- `test_cloud_gateway_provider_router.py`
- `test_cloud_gateway_proxy_authorization.py`
- `test_cloud_gateway_runner_bootstrap.py`
- `test_cloud_gateway_runner_cleanup.py`
- `test_cloud_gateway_runner_registry.py`
- `test_cloud_gateway_runner_terminal_grant.py`
- `test_cloud_gateway_runtime.py`
- `test_cloud_gateway_scheduler_integration.py`
- `test_cloud_gateway_terminal_catalog.py`
- `test_cloud_gateway_terminal_templates.py`

### Runner and Cloud Runner (9)
- `test_cloud_runner_backend.py`
- `test_cloud_runner_dashboard_contract.py`
- `test_cloud_runner_e2e_acceptance.py`
- `test_cloud_runner_openapi.py`
- `test_cloud_runner_user_api.py`
- `test_cloud_runner_workflow_client.py`
- `test_runner_agent.py`
- `test_runner_agent_gateway_e2e.py`
- `test_runner_preflight.py`

### Local Runner and Local Projects (14)
- `test_local_project_cli.py`
- `test_local_project_registry.py`
- `test_local_project_snapshot.py`
- `test_local_runner_agent.py`
- `test_local_runner_bootstrap.ps1`
- `test_local_runner_checkout.py`
- `test_local_runner_cli.py`
- `test_local_runner_execution.py`
- `test_local_runner_launcher_contract.py`
- `test_local_runner_manager.py`
- `test_local_runner_pipeline_e2e.py`
- `test_local_runner_readiness.py`
- `test_local_runner_service.py`
- `test_local_runner_workspace.py`

### Terminal (5)
- `test_terminal_command_pack_schema.py`
- `test_terminal_execution_contract.py`
- `test_terminal_executor.py`
- `test_terminal_grants.py`
- `test_terminal_isolation.py`

### Dashboard (5)
- `test_dashboard_contract.py`
- `test_dashboard_document_lifecycle_contract.py`
- `test_dashboard_dynamic_port.ps1`
- `test_dashboard_launcher.ps1`
- `test_dashboard_launcher_contract.py`

### Authentication (2)
- `test_local_auth_proxy.py`
- `test_local_auth_proxy_project_routes.py`

### Local tooling/runtime and browser (4)
- `test_local_browser_testing.py`
- `test_local_image_lab.py`
- `test_local_runtime.py`
- `test_local_web_build.py`

### Project intelligence/architecture (2)
- `test_architecture_planner.py`
- `test_project_intelligence.py`

### MCP (2)
- `test_native_mcp_engine.py`
- `test_native_mcp_server.py`

### Other supporting tests and scripts (10)
- `browser_smoke.mjs`
- `emit_runner_bootstrap_scripts.py`
- `live_gateway_preflight.py`
- `test_authenticated_preview.py`
- `test_browser_test.py`
- `test_dev_environment.py`
- `test_document_workflow_gateway.py`
- `test_document_workflow_writer.py`
- `test_live_gateway_preflight.py`
- `test_sqlite_security.py`

**Count note:** the groups above total 86 files. The inventory includes test scripts and PowerShell checks, not only Python unittest modules. PR #116 adds a new Linux sandbox test file on its feature branch; it is not part of the baseline count until merged.

## 4. Workflow-to-requirement map

| Workflow | Primary requirements | What it cannot prove |
|---|---|---|
| `cross-platform-recovery.yml` | RQ-004, 005, 007, 011, 012, 023 | User-host acceptance; Windows AppContainer or Linux sandbox unless the explicit host test runs |
| `local-first-emulator.yml` | RQ-001, 004, 014 | Live cloud provider readiness or user environment |
| `validate-control-plane.yml` | RQ-016, 020, 023 | Complete manual accessibility or production security acceptance |
| `cloud-gateway-live-smoke.yml` | RQ-001, 002, 014, 015 | No live evidence unless explicitly configured and executed |
| `macos-cloud-runner.yml` | RQ-005, 014 | macOS App Sandbox isolation for Terminal |
| `static.yml` | RQ-016, static deployment assets | Backend/API/authenticated workflow acceptance |
| `deploy-pages.yml` | Static UI delivery | Does not prove backend deployment or authorize production deployment |

## 5. Unresolved traceability gaps

1. Per-file function/class/entrypoint inventory for all 78 tool files.
2. Complete HTTP method + path + request schema + auth/role + CSRF matrix for Gateway and Local Auth Proxy.
3. Dashboard view → DOM handlers → API call → backend service → test mapping for all 21 views.
4. Every test function mapped to requirement ID and exact workflow/job.
5. Requirements source and acceptance criteria for non-code goals (AI lifecycle, plugins, visual workflow, backup/restore, upgrades).
6. Actual Windows and Linux host acceptance evidence.
7. Current exact-head CI for PR #116 and all subsequent changes.

Do not mark this document COMPLETE until every unresolved gap is closed or explicitly deferred with an owner decision and reason.
