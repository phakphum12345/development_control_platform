# DCP Test and Acceptance Matrix — 2026-11-19

**Main baseline:** `985a78d5fba459c8a0cbcf47e5d00a858c6e6228`  
**Evidence source:** GitHub workflow definitions, exact-head workflow run metadata and selected job logs.  
**Current audit state:** PARTIAL — workflow topology and PR #140/#149 outcomes inspected; no tests were executed locally by this audit.

## 1. Workflow-to-acceptance matrix

| Workflow | Trigger / runner | Main test scope | What it proves | What it does not prove |
|---|---|---|---|---|
| `validate-control-plane.yml` | PR/push main/manual; Ubuntu; optional self-hosted Windows matrix | Python unittest discovery, Dashboard JS syntax, Chromium real-app smoke, authenticated Preview Proxy Chromium/Firefox/WebKit, browser smoke, schema/registry validation, optional Windows Runner acceptance | Broad contract/regression and selected browser/API behavior on hosted runners | Real user's local machine, complete app compatibility, full WCAG/visual regression, Windows acceptance when optional job skipped |
| `local-first-emulator.yml` | PR/push main/manual; Ubuntu + Windows hosted | Local doctor, full Python unittest discovery, Gateway health/auth/safe defaults, Windows PowerShell parsing and Auth Proxy → Gateway login/logout/session flow | Local-first emulator and hosted Windows integration | Self-hosted user host, production OIDC, OS sandbox |
| `cross-platform-recovery.yml` | PR/push path-filter/manual; Ubuntu + Windows hosted | JobStore recovery, Runner API, pipeline interruption, hardlink containment, Auth Proxy, Flutter executor policy, Linux bubblewrap policy | Selected cross-platform recovery and policy tests | All failure modes, production sandbox acceptance on every supported host, macOS |
| `package-release.yml` | Dashboard/package PR, manual, release; Windows hosted | Inno Setup install, PWA/portable ZIP/installer build and upload | Packaging pipeline build | Clean-machine install/upgrade/rollback/uninstall and code-signing acceptance |
| `cloud-gateway-live-smoke.yml` | Manual only; explicit input defaults false; Ubuntu | GET-only live health/auth preflight | Read-only live endpoint behavior when explicitly enabled | Provisioning, VM creation, runner-online, live job or teardown |
| `macos-cloud-runner.yml` | Manual only; opt-in boolean defaults false plus repository variables and secrets | Provider request dispatch for allowlisted repository/commit/OS | Guarded request path when every gate is deliberately enabled | Actual macOS runner readiness/job/cleanup unless a separate live acceptance is captured |
| `deploy-pages.yml` | Main dashboard push/manual; Ubuntu | Static Dashboard Pages deployment | Pages artifact/deployment action | Authenticated local Gateway availability or production backend deployment |
| `static.yml` | Manual only | Informational notice | Duplicate Pages workflow is disabled | No product acceptance |

## 2. PR exact-head evidence observed

### PR #140 — head `8bf0b74859c3749070eafbd7906d9c7df6d0822b`

| Workflow / job | Result | Interpretation |
|---|---|---|
| Validate Control Plane / `validate` | PASS | Hosted test and validation job passed |
| Windows dynamic-port launcher integration | PASS | Hosted Windows integration passed |
| Optional Windows runner acceptance | SKIPPED | Not a target-host acceptance result |
| Windows PSEC API Availability Probe workflow | Workflow PASS; internal evidence BLOCKED | Probe JSON says `available=false`, `state=BLOCKED`; `processmodel.dll` unavailable from System32 search path |
| Package Development Control Platform | PASS | Windows package build completed |
| Cross-platform Recovery / Windows + Ubuntu | PASS | Both hosted matrix jobs passed |
| Local-first Minimal Emulator / Linux + Windows | PASS | Both hosted emulator jobs passed |

### PR #149 — head `44ec9f4b95601071b172a9b541387399591745b7`

| Workflow / job | Result | Interpretation |
|---|---|---|
| Validate Control Plane / `validate` | PASS | Hosted test and validation job passed |
| Windows dynamic-port launcher integration | PASS | Hosted Windows integration passed |
| Optional Windows runner acceptance | SKIPPED | Not target-host acceptance |
| Windows PSEC API Availability Probe workflow | Workflow PASS; internal evidence BLOCKED | Probe JSON says `available=false`, `state=BLOCKED`; `processmodel.dll` unavailable |
| Cross-platform Recovery / Windows + Ubuntu | PASS | Both hosted matrix jobs passed |
| Local-first Minimal Emulator / Linux + Windows | PASS | Both hosted emulator jobs passed |

**Important:** A workflow may be green because its probe classifies the hosted image as an expected BLOCKED environment and uploads evidence. The workflow conclusion is not proof that the PSEC capability passed.

## 3. Required host acceptance not yet satisfied

- Windows: PSEC API availability on a supported target, trusted base runtime and stdlib, real AppContainer/LPAC effective access, filesystem deny/enumeration behavior, network denial, process-tree containment, cleanup, scratch profile and no host-profile escape.
- Linux: integrated bubblewrap launcher, mount and namespace verification, seccomp network denial, process cleanup and adversarial host tests.
- macOS: signed helper, entitlements, filesystem/network boundary and actual-host acceptance.
- Windows installation: clean machine install, upgrade, rollback, interrupted install recovery and uninstall preservation.
- Cloud: only with explicit approval; runner create → online → controlled job → offline → deregistration → VM/NIC absence → orphan reconciliation and actual spend evidence.

## 4. Evidence record requirements

Every future acceptance record must include:
- Repository, branch, full commit SHA.
- Workflow URL, run ID, job ID and job conclusion.
- Host OS/build/architecture and runner identity.
- Exact command and environment contract (never secret values).
- Start/end timestamp and exit code.
- Artifact path/URL and SHA-256.
- Cleanup result.
- PASS/FAIL/BLOCKED/SKIPPED/UNKNOWN classification.
- Explicit scope limits.

## 5. Re-run policy

- Re-run required workflows after any source or workflow change.
- Verify the exact current PR head SHA, not a parent or prior run.
- Treat path-filtered workflows that did not trigger as UNKNOWN until manually or otherwise validly executed.
- Keep optional self-hosted jobs SKIPPED unless a registered supported host actually runs them.
- Never use unsandboxed browser fallback or relax security policy merely to make CI green.


---

## 6. 2026-11-20 — Exact-head PR #150 / #151 recheck

### PR #150

- Head SHA: `b4769a69115cefa39a8ac5770b65e5379917142d`.
- Validate Control Plane: `validate` PASS.
- Local-first Minimal Emulator: Linux Minimal Emulator PASS; Windows 11 Auth Proxy + Gateway E2E PASS.
- Cross-platform Recovery: Ubuntu PASS; Windows PASS.
- Windows dynamic-port launcher integration: **FAIL** (job `135733550078`).
- Optional Windows runner acceptance: **SKIPPED** (job `135733552694`).
- Exact failure line: `tests/test_local_runner_bootstrap.ps1:28` invokes `Setup-DCP-Local-Runner.ps1 -WorkerId ... -TrustedRepository ...`; PowerShell reports that the `TrustedRepository` parameter is not defined on main.
- Classification: PR #150 CI = FAIL; Windows host acceptance = SKIPPED. The docs-only change did not alter the failing bootstrap contract.

### PR #151

- Head SHA: `87b2c4dd48c6ad21fdeb8fa9cd79173f4409de92`.
- Validate Control Plane: PASS; package: PASS; Linux Minimal Emulator: PASS; Windows Auth Proxy + Gateway E2E: PASS; Ubuntu and Windows Recovery: PASS.
- Windows dynamic-port launcher integration: **FAIL** (job `135720966046`).
- Optional Windows runner acceptance: **SKIPPED** (job `135720969555`).
- Classification: PR #151 CI = FAIL; Code Navigator contract mapping = candidate implementation only.

### PR #151 Code Navigator test trace

At the PR #151 head:
- 23 navigation IDs are present in Dashboard source.
- 23 `CODE_NAV_MAPPINGS` records are present, including `project-import` and `document-generator`.
- New contract checks include exact navigation/mapping equality and validation that each declared test path and function/class symbol resolves.
- The changed test file includes `DashboardControlCenterV2Tests.test_code_navigator_covers_all_dashboard_views` and `test_code_navigator_mapping_test_references_resolve`.
- This validates static mapping integrity; it does not execute the referenced tests or prove backend behavior.

## 7. 2026-11-20 — Selected test-function and workflow trace (WP-00C increment)

This increment enumerates test methods and fixtures from eight security/control-plane test files on exact main baseline. It is a partial register, not the full 88 Python test-file inventory.

| Test file | Test methods | Fixture / setup | Skip conditions | Workflow/job relationship |
|---|---:|---|---|---|
| `tests/test_cloud_gateway_job_control.py` | 23 | `JobStoreTests.setUp/tearDown` | None found | Validate Control Plane / full unittest discovery; Cross-platform Recovery (recovery-focused subset) |
| `tests/test_cloud_gateway_proxy_authorization.py` | 2 | `ProxyMutationAuthorizationTests.setUp/tearDown` | None found | Validate Control Plane / full unittest discovery |
| `tests/test_cloud_gateway_dynamic_port.py` | 4 | None | None found | Validate Control Plane / full unittest discovery; Windows dynamic-port integration exercises launcher rather than this module alone |
| `tests/test_cloud_gateway_local_projects.py` | 22 | `LocalProjectGatewayAPITests.setUp/tearDown` | None found | Validate Control Plane / full unittest discovery |
| `tests/test_document_workflow_gateway.py` | 11 | `DocumentWorkflowStoreTests.setUp/tearDown` | None found | Validate Control Plane / full unittest discovery |
| `tests/test_terminal_grants.py` | 11 | `TerminalGrantStoreTests.setUp/tearDown` | None found | Validate Control Plane / full unittest discovery |
| `tests/test_terminal_executor.py` | 20 | `TerminalScriptExecutorTests.setUp/tearDown` | Git unavailable; Git <2.36; symlinks unavailable on host | Validate Control Plane / full unittest discovery; Cross-platform Recovery / policy and process-related subsets |
| `tests/test_sqlite_security.py` | 4 | None | POSIX-only file mode assertions skipped on Windows | Validate Control Plane / full unittest discovery; Windows ACL behavior requires separate tests |
 
### Selected method-level coverage

- Job control: idempotency, invalid/conflicting payloads, immutable Local Folder snapshot identity, trusted-project gate, terminal grant binding, lease expiry/requeue/fencing, bounded retries, checkpoint monotonicity/idempotency/lease binding, UNKNOWN-job owner reconciliation, concurrent claims and cancellation.
- Proxy authorization: operator read access is distinct from Owner-only runner creation/termination.
- Local project Gateway API: Owner-only Local Folder metadata, public GitHub catalog operator access, local path disclosure prevention, source refresh/fingerprint and terminal grant/job authorization.
- Document Workflow: default-disabled scope, explicit grant confirmation, exact byte/digest approval, stale base, path traversal, revoked grant and idempotency.
- Terminal grants/executor: one-time consumption, job/runner binding, expiry/revocation, canonical digest, disabled execution without verified isolation, fixed argv, timeout/output/cancel termination, symlink rejection and streaming secret redaction.
- SQLite security: owner-only DB permissions and symlink rejection.

### Remaining WP-00C gaps

- Enumerate all test functions/classes, fixtures and skip decorators in the remaining test files (88 `test_*` paths exist in the main recursive tree; this is not the total number of tests).
- Include non-`test_*` test assets such as `tests/browser_smoke.mjs`, generated bootstrap scripts and PowerShell acceptance scripts.
- Map each test function to the exact workflow step/job and path-filter conditions.
- Record exact-head test execution results separately from test definitions.


## 8. 2026-11-20 — Additional WP-00C API/security test-function mapping

| Test file | Methods | Fixture / skip notes | Workflow/job mapping |
|---|---:|---|---|
| `tests/test_local_auth_proxy_project_routes.py` | 19 | `LocalProjectProxyRouteTests.setUp/tearDown`; no skip markers found | Validate Control Plane / full unittest discovery |
| `tests/test_cloud_gateway_terminal_catalog.py` | 7 | No skip markers found | Validate Control Plane / full unittest discovery |
| `tests/test_cloud_gateway_infrastructure_api.py` | 16 | No skip markers found | Validate Control Plane / full unittest discovery |
| `tests/test_local_auth_proxy.py` | 22 | Includes browser-engine readiness/skip behavior; credential, session, preview, Origin/CSRF and Gateway local settings tests | Validate Control Plane / full unittest discovery; Cross-platform Recovery / explicit Local Auth Proxy test step |
| `tests/test_cloud_gateway.py` | 8 | HTTP tests use temporary SQLite and a local fake provider; no live provider is contacted | Validate Control Plane / full unittest discovery |

### Additional security assertions established from named tests

- Proxy GET routes: allow only explicit project/job/artifact/runner/terminal/infrastructure paths; reject unknown paths, duplicate/unbounded query parameters and invalid UUID/SHA forms before forwarding.
- Proxy mutations: session + same-origin + CSRF required; runner drain/enable, job resume/cancel and Terminal actions are constrained to exact paths and empty-object schemas where applicable.
- Infrastructure: independent cloud-provisioning and VM-creation gates default OFF; Owner confirmation/readiness required; operators cannot delete resources; Terminal catalog remains inert.
- Document Workflow: no write scope by default; exact path scope, current base digest, content digest and confirmation are checked; traversal, hidden/unsupported paths and idempotency-key content conflicts are rejected.
- Test definitions are not execution proof. Exact-head workflow evidence remains the separate matrix in this document.
 
### Updated test inventory accounting

The main recursive tree contains 91 files under `tests/`: 88 `test_*` paths and three supporting assets. This corrects the ambiguity between test-file count and all files under the test directory. Function-level mapping is now recorded for 13 selected security/control-plane modules; all remaining modules are still pending.


## 9. 2026-11-20 — Mainline test-file to requirement-family inventory

The 88 `tests/test_*` paths are grouped below by their primary requirement family. This is a filename-level classification only; files that span multiple areas remain listed once under their primary test concern. All 88 paths are assigned; three other files under `tests/` are support assets, not test modules.

| Requirement family | Count | Test files |
|---|---:|---|
| CORE / Gateway / Auth / policy | 37 | `test_cloud_gateway.py`, `test_cloud_gateway_artifact_download.py`, `test_cloud_gateway_artifacts.py`, `test_cloud_gateway_azure_egress.py`, `test_cloud_gateway_azure_guest_profile.py`, `test_cloud_gateway_azure_provider_runtime.py`, `test_cloud_gateway_azure_security.py`, `test_cloud_gateway_azure_vm.py`, `test_cloud_gateway_budget_lifecycle.py`, `test_cloud_gateway_dynamic_port.py`, `test_cloud_gateway_github_app.py`, `test_cloud_gateway_infrastructure.py`, `test_cloud_gateway_infrastructure_api.py`, `test_cloud_gateway_infrastructure_gates.py`, `test_cloud_gateway_job_control.py`, `test_cloud_gateway_local_mode.py`, `test_cloud_gateway_local_projects.py`, `test_cloud_gateway_oidc_edge_signer.py`, `test_cloud_gateway_oidc_ingress_contract.py`, `test_cloud_gateway_orka.py`, `test_cloud_gateway_orka_bootstrap.py`, `test_cloud_gateway_preflight.py`, `test_cloud_gateway_provider_budget.py`, `test_cloud_gateway_provider_router.py`, `test_cloud_gateway_proxy_authorization.py`, `test_cloud_gateway_runner_bootstrap.py`, `test_cloud_gateway_runner_cleanup.py`, `test_cloud_gateway_runner_registry.py`, `test_cloud_gateway_runner_terminal_grant.py`, `test_cloud_gateway_runtime.py`, `test_cloud_gateway_scheduler_integration.py`, `test_cloud_gateway_terminal_catalog.py`, `test_cloud_gateway_terminal_templates.py`, `test_cloud_runner_openapi.py`, `test_cloud_runner_user_api.py`, `test_local_auth_proxy.py`, `test_local_auth_proxy_project_routes.py` |
| Project intake / import | 3 | `test_local_project_cli.py`, `test_local_project_registry.py`, `test_local_project_snapshot.py` |
| Local Runner / workspace / recovery | 16 | `test_local_runner_agent.py`, `test_local_runner_bootstrap.ps1`, `test_local_runner_checkout.py`, `test_local_runner_cli.py`, `test_local_runner_execution.py`, `test_local_runner_hardlink_containment.py`, `test_local_runner_launcher_contract.py`, `test_local_runner_legacy_launcher_contract.py`, `test_local_runner_manager.py`, `test_local_runner_pipeline_e2e.py`, `test_local_runner_readiness.py`, `test_local_runner_service.py`, `test_local_runner_workspace.py`, `test_runner_agent.py`, `test_runner_agent_gateway_e2e.py`, `test_runner_preflight.py` |
| Build / runtime / preview / browser | 5 | `test_authenticated_preview.py`, `test_browser_test.py`, `test_local_browser_testing.py`, `test_local_runtime.py`, `test_local_web_build.py` |
| Dashboard / UI | 6 | `test_cloud_runner_dashboard_contract.py`, `test_dashboard_contract.py`, `test_dashboard_document_lifecycle_contract.py`, `test_dashboard_dynamic_port.ps1`, `test_dashboard_launcher.ps1`, `test_dashboard_launcher_contract.py` |
| Terminal / OS isolation | 6 | `test_linux_sandbox.py`, `test_terminal_command_pack_schema.py`, `test_terminal_execution_contract.py`, `test_terminal_executor.py`, `test_terminal_grants.py`, `test_terminal_isolation.py` |
| Data / storage | 1 | `test_sqlite_security.py` |
| AI / intelligence | 2 | `test_architecture_planner.py`, `test_project_intelligence.py` |
| Document workflow | 2 | `test_document_workflow_gateway.py`, `test_document_workflow_writer.py` |
| MCP | 2 | `test_native_mcp_engine.py`, `test_native_mcp_server.py` |
| Release / install | 1 | `test_release_packaging.py` |
| Owner security | 1 | `test_reset_owner_password.py` |
| Developer environment | 1 | `test_dev_environment.py` |
| Cross-cutting / manual classification required | 5 | `test_cloud_runner_backend.py`, `test_cloud_runner_e2e_acceptance.py`, `test_cloud_runner_workflow_client.py`, `test_live_gateway_preflight.py`, `test_local_image_lab.py` |

### Workflow execution relationship

- `validate-control-plane.yml` runs full Python unittest discovery, so all discoverable Python `test_*` modules are included in the `validate` job unless their test decorators skip them at runtime. The PowerShell `test_*.ps1` scripts are executed only by named Windows steps.
- `cross-platform-recovery.yml` explicitly executes selected Job Control, Cloud Runner API, Local Runner pipeline/hardlink, Local Auth Proxy, Flutter execution and Linux sandbox modules on Ubuntu/Windows matrix runners.
- `package-release.yml` runs packaging acceptance; `deploy-pages.yml` is a deployment workflow, not a general unit-test workflow.
- This inventory does not assert that every test method passed on every workflow. Exact job/commit evidence remains in Sections 2 and 6.

### Remaining WP-00C work

- Function/class/fixture/skip enumeration is still incomplete for the remaining 75 test modules.
- The five cross-cutting modules need manual requirement ownership and workflow-job classification.
- PowerShell scripts and browser smoke support assets need their own step-level acceptance mapping.


---

## Historical-baseline notice — 2026-11-25

This archived document preserves the detailed WP-00 work product originally authored against main SHA `985a78d5fba459c8a0cbcf47e5d00a858c6e6228`. Its counts, PR heads, check results and implementation statements are historical and must not be treated as current-main facts. The refreshed current baseline is main SHA `57589873583c706d4af9756709596fdba7c22de9`; see [DCP Live Repository Audit 2026-11-25](../DCP-LIVE-REPOSITORY-AUDIT-2026-11-25.md). Preserve this file for its source-level route, test, workflow and architecture detail; reconcile each claim before reusing it.
