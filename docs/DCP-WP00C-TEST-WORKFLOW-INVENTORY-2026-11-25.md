# WP-00C — Test Module, Function and Workflow Inventory (2026-11-25)

**Repository:** `phakphum12345/development_control_platform`  
**Baseline:** `875b7fd575b60cbfb3fea6d21343915ebf2a2633`  
**Branch:** `docs/wp00c-test-workflow-inventory-20261125`  
**Method:** recursive Git tree inventory + exact-blob source scan of every Python file under `tests/` + direct inspection of all GitHub Actions workflow YAML files.  
**Status:** PARTIAL — source definitions inventoried; actual collection/execution counts, complete fixture/setup semantics, skip reasons and every test-to-requirement edge remain open.

## 1. Test tree census

| Measure | Observed |
|---|---:|
| All paths under `tests/` | 116 |
| Python files | 112 |
| Python modules named `test_*.py` | 110 |
| Python support scripts not named `test_*.py` | 2 |
| PowerShell test scripts | 3 |
| Browser JavaScript support test | 1 (`browser_smoke.mjs`) |
| Syntactic `def test_*` definitions across all 112 Python files | 1,034 |
| Python class declarations in those files | 263 |
| `pytest.fixture` / `fixture` decorators detected | 0 |
| `unittest.skip*` / `pytest.mark.skip*` / `xfail` decorators detected | 27 |
| Runtime `skipTest()` / `pytest.skip()` calls detected | 26 |
| `pytest.mark.parametrize` decorators detected | 0 |

These are source-level lexical counts, not test-runner collection counts. The 1,034 definition count may include helper methods whose names start with `test_`; it must not be represented as 1,034 collected or passed tests. Decorator and runtime skip counts can overlap and are not additive. Fixture count refers to pytest fixture decorators only; unittest `setUp`/`tearDown` methods and custom helper fixtures require semantic classification. The actual Validate job's unittest discovery output must be captured separately to close the collection-count requirement.

## 2. Workflow inventory

Nine workflow files contain twelve actual jobs. Trigger declarations are not counted as jobs.

| Workflow | Job IDs | Test / acceptance relationship |
|---|---|---|
| `validate-control-plane.yml` | `validate`; `windows-launcher-integration`; `windows-runner-smoke-test` | `validate` runs full Python unittest discovery plus browser checks; Windows launcher integration runs PowerShell launcher/contract tests; runner smoke is optional host acceptance and may be skipped |
| `cross-platform-recovery.yml` | `recovery-tests` | Matrix recovery suites include Job Control, Cloud Runner User API, Local Runner pipeline/hardlink containment, Local Auth Proxy, Local Runner execution, Linux sandbox and Terminal executor; host-dependent portions differ by OS |
| `local-first-emulator.yml` | `linux-minimal-emulator`; `windows-11-launcher-emulator` | Linux and Windows local-first emulator checks; includes unittest discovery and gateway/launcher smoke validation |
| `package-release.yml` | `package` | Package/installer build and artifact validation; not a substitute for clean-machine install/upgrade/rollback acceptance |
| `windows-psec-host-acceptance.yml` | `windows-psec-host-acceptance` | Target-specific PSEC availability, real NTFS ACL and AppContainer effective-access probes; workflow success can represent an explicit BLOCKED probe, so inspect its evidence payload |
| `cloud-gateway-live-smoke.yml` | `live-gateway-readonly-smoke` | Manual opt-in, read-only live health/auth smoke; not a unit-test or provisioning acceptance |
| `macos-cloud-runner.yml` | `request-cloud-runner` | Manual opt-in provider request workflow; no live resource action without its separate explicit gates |
| `deploy-pages.yml` | `deploy` | Static Pages deployment; not backend or test-suite acceptance |
| `static.yml` | `notice` | Disabled duplicate Pages workflow notice; no product acceptance |

## 3. Selected test-to-workflow mapping

| Test family / modules | Primary workflow relationship | Evidence boundary |
|---|---|---|
| Gateway, Proxy, OIDC, Job Control, Document Workflow, GitHub App, provider policy, API contracts | Validate / `validate` full unittest discovery | Hosted suite result does not establish live provider or target-host acceptance |
| Auth Proxy, Job Control, Runner API, Local Runner pipeline, hardlink containment, execution, Linux sandbox, Terminal executor | Cross-platform Recovery / `recovery-tests` | Selected matrix subset only; not every test runs in every job |
| Dashboard launcher and dynamic-port scripts | Validate / `windows-launcher-integration` | Hosted Windows integration, not the user's workstation |
| Browser smoke and authenticated preview browser tests | Validate / `validate` browser steps | Browser-engine install/readiness can skip; capture each engine result |
| PSEC ACL handles / real NTFS / AppContainer effective access | Windows PSEC host acceptance | Target capability availability and evidence artifact must be read independently of workflow conclusion |
| Packaging | Package Release / `package` | Build success is not install/upgrade/uninstall rollback proof |
| Live Gateway preflight | Live Read-only Smoke | GET-only and manual opt-in; no mutation/provisioning proof |

## 4. Skip and fixture audit limitations

- The lexical scan found 27 skip-related decorators and 26 runtime skip calls across the Python files. It does not yet classify every condition, affected platform, skip rationale, or whether a skip is acceptable.
- No pytest fixture decorators were found. This does not mean there are no fixtures: many unittest suites define `setUp`, `tearDown`, class setup, temporary directories, fake HTTP servers, subprocess harnesses and shared helper factories.
- Some modules contain tests requiring Chromium, Firefox, WebKit, Git, symlink privileges, bubblewrap, Windows PSEC APIs, AppContainer, or real NTFS. These host dependencies must be separately classified.
- The 3 PowerShell scripts and browser JavaScript support file require step-level mapping; counting them as Python tests would be incorrect.
- Test definitions do not prove execution. Each relevant test must be tied to an exact workflow job/run and exact commit SHA.

## 5. Complete Python test-module path register

The 110 Python files matching `tests/test_*.py` at the stated baseline are:

- `tests/test_architecture_planner.py`
- `tests/test_authenticated_preview.py`
- `tests/test_browser_test.py`
- `tests/test_cloud_gateway.py`
- `tests/test_cloud_gateway_artifact_download.py`
- `tests/test_cloud_gateway_artifacts.py`
- `tests/test_cloud_gateway_azure_egress.py`
- `tests/test_cloud_gateway_azure_guest_profile.py`
- `tests/test_cloud_gateway_azure_identity.py`
- `tests/test_cloud_gateway_azure_network_policy.py`

- `tests/test_cloud_gateway_azure_provider_runtime.py`
- `tests/test_cloud_gateway_azure_runtime.py`
- `tests/test_cloud_gateway_azure_security.py`
- `tests/test_cloud_gateway_azure_vm.py`
- `tests/test_cloud_gateway_budget_lifecycle.py`
- `tests/test_cloud_gateway_dynamic_port.py`
- `tests/test_cloud_gateway_github_app.py`
- `tests/test_cloud_gateway_github_app_runtime.py`
- `tests/test_cloud_gateway_infrastructure.py`
- `tests/test_cloud_gateway_infrastructure_api.py`

- `tests/test_cloud_gateway_infrastructure_gates.py`
- `tests/test_cloud_gateway_job_control.py`
- `tests/test_cloud_gateway_key_vault.py`
- `tests/test_cloud_gateway_local_mode.py`
- `tests/test_cloud_gateway_local_projects.py`
- `tests/test_cloud_gateway_oidc_auth_service.py`
- `tests/test_cloud_gateway_oidc_client.py`
- `tests/test_cloud_gateway_oidc_config.py`
- `tests/test_cloud_gateway_oidc_deployment.py`
- `tests/test_cloud_gateway_oidc_edge_signer.py`

- `tests/test_cloud_gateway_oidc_ingress_contract.py`
- `tests/test_cloud_gateway_oidc_nginx_ingress.py`
- `tests/test_cloud_gateway_oidc_session_store.py`
- `tests/test_cloud_gateway_oidc_trusted_proxy.py`
- `tests/test_cloud_gateway_oidc_wsgi.py`
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
- `tests/test_local_runner_artifacts.py`
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
- `tests/test_public_github_catalog.py`
- `tests/test_recon_api.py`

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
- `tests/test_windows_psec.py`
- `tests/test_windows_psec_acl.py`
- `tests/test_windows_psec_acl_handles.py`
- `tests/test_windows_psec_acl_real_host.py`
- `tests/test_windows_psec_appcontainer_effective_access.py`
- `tests/test_windows_psec_host_acceptance.py`
- `tests/test_windows_psec_launcher.py`
- `tests/test_windows_psec_projection.py`
- `tests/test_windows_psec_spec.py`

The remaining two Python files under `tests/` are support scripts, not `test_*.py` modules:
- `tests/emit_runner_bootstrap_scripts.py`
- `tests/live_gateway_preflight.py`

Non-Python test assets:
- `tests/test_dashboard_dynamic_port.ps1`
- `tests/test_dashboard_launcher.ps1`
- `tests/test_local_runner_bootstrap.ps1`
- `tests/browser_smoke.mjs`

## 6. Required closure work

1. Capture actual unittest discovery counts and per-module results from exact Validate workflow run/job logs.
2. Enumerate every unittest `setUp`/`tearDown`, class setup/teardown, temporary fixture, fake service and subprocess harness; identify shared test utilities.
3. Resolve every skip decorator/runtime skip to its exact function, condition, platform and rationale; distinguish intentional host-only SKIPPED from accidental skipped coverage.
4. Map all 1,034 syntactic test definitions to actual collected test IDs and requirement IDs; classify helper methods that happen to start with `test_`.
5. Map every test ID to workflow/job/step and path-filter trigger; identify tests that are never run by CI.
6. Map the three PowerShell scripts and browser smoke asset to their exact workflow step and host matrix.
7. Record exact SHA, workflow run ID, job ID, conclusion and artifact evidence; do not infer PASS from workflow-level success if an internal probe is BLOCKED.
8. Keep target-host PSEC, OS-isolation, installer rollback and live cloud acceptance as separate gates.

## 7. Acceptance conclusion

WP-00C remains **PARTIAL**. The current source census establishes 116 test paths, 112 Python files, 110 Python test modules, 3 PowerShell scripts, 1 browser support asset, 1,034 syntactic `test_*` definitions and the nine-workflow/twelve-job map. It does not establish actual collected or passed test counts, complete fixture/skip semantics, requirement traceability or target-host acceptance.

No runtime code, test behavior, credentials, roles, provider configuration, cloud resource or deployment was changed by this inventory.


## 8. Actual CI collection evidence added after the source census

A completed Validate Control Plane run provides the first observed runner-collection count:

- Workflow: Validate Control Plane, run ID `45656155370`.
- Exact tested commit: `0fa336347e8d6b2561e7c81cfa6195a5e1307ae9` (the PR #157 docs-only merge candidate; Python/test source blobs are unchanged from the resulting mainline).
- Job: `validate`, job ID `139353263533`, conclusion `success`.
- Step: `python -m unittest discover -s tests -v`.
- Result: **Ran 1,054 tests in 89.995s; OK (skipped=34)**. Thus 1,020 were not skipped and the unittest command reported no failures.

### Skip breakdown observed in this exact run

| Reason | Count | Interpretation |
|---|---:|---|
| Real Windows `cmd.exe` batch-file launcher required | 25 | Host-specific tests skipped on the Linux Validate runner; Windows dynamic-port integration has a separate hosted job |
| Optional Python Playwright/browser prerequisites unavailable | 5 | One generic Playwright, Chromium, Firefox, WebKit and two local-browser acceptance tests |
| Real Windows NTFS handle-relative ACL acceptance opt-in | 1 | Target-host-only; not established by hosted Validate |
| Real Win32 ACL dedicated-host opt-in | 1 | Target-host-only |
| Real AppContainer effective-access acceptance opt-in | 1 | Target-host-only |
| **Total** | **34** | Counts from the emitted unittest skip lines; categories are mutually exclusive for this run |

The same Validate job subsequently ran four additional targeted browser tests, each reporting `Ran 1 test` and `OK`; those are separate invocations and are not added to the 1,054 discovery count. The general browser discovery step still recorded the five optional Playwright skips above.

The same workflow run's Windows dynamic-port launcher integration job (job ID `139353264190`) completed SUCCESS and passed the real `cmd.exe` shim, Runner job-to-artifact pipeline, hardlink containment, Local Folder snapshot-to-build, legacy launcher, bootstrap parsing, protected credential setup and dynamic Dashboard launcher steps. The optional Windows runner acceptance job was SKIPPED; it is not a target-host PSEC acceptance result.

**Interpretation:** this closes the gap between syntactic definitions and one actual collected-suite count for this exact workflow run. It does not prove every test was executed on every OS, and the 34 skips remain visible obligations or host-specific exclusions. Target-host NTFS/AppContainer/PSEC acceptance remains separate.
