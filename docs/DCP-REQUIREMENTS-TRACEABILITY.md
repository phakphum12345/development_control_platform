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
