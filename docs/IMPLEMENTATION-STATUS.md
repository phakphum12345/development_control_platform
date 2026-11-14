# DCP Implementation Status

**Repository:** `phakphum12345/development_control_platform`  
**Protocol:** DCP-CEEP v1.0 — Adopted  
**Audit baseline:** `main` at `62d72bddd028399d0b96cd9c2f6e3b16a704b758`  
**Status:** IN_PROGRESS — source inventory and operational acceptance are not complete

## 1. Repository inventory

| Area | Baseline count | Coverage |
|---|---:|---|
| Git tree entries | 289 | Recursive tree captured |
| Files | 265 | File inventory captured |
| `tools/` | 78 | Subsystem map captured; per-file contracts still being traced |
| `tests/` | 86 | Test file inventory captured; requirement-level coverage still being traced |
| `docs/` | 58 | Document inventory captured; status reconciliation remains |
| GitHub Actions workflows | 7 | Workflow inventory captured |
| Dashboard views | 21 | View IDs enumerated from `dashboard/index.html` |
| API route families | 9+ | Gateway and Local Auth Proxy routes mapped at family level |

Counts are tied to the exact baseline above. New files on an unmerged feature branch are not included in these baseline counts.

## 2. Source subsystem map

| Subsystem | Main implementation | Current implementation boundary |
|---|---|---|
| Gateway HTTP/API | `tools/cloud_gateway/server.py`, `service.py` | HTTP routes, auth, jobs, artifacts, runner, infrastructure and terminal APIs exist; live host acceptance remains separate |
| Durable job control | `job_control.py`, `store.py`, `scheduler.py` | SQLite lifecycle, leases, checkpoints, retries, idempotency and scheduling exist; interruption/host recovery acceptance remains |
| Runner lifecycle/providers | `runner_registry.py`, `runner_bootstrap.py`, `runner_cleanup.py`, `provider_router.py`, `azure_*.py`, `orka*.py` | Azure/Orka adapters, budgets, OIDC, cleanup and opt-in gates exist; live provider acceptance is separately gated |
| Local Auth Proxy | `tools/local_auth_proxy.py` | Owner session, CSRF, signed proxy identity, artifact and preview routes exist; actual Windows host acceptance remains UNKNOWN |
| Local Runner | `tools/local_runner_agent/` | Enrollment, checkout, immutable snapshots, execution, build, browser tests, artifacts, workspaces, checkpoints and Terminal executor exist |
| Terminal Studio | `terminal_catalog.py`, `terminal_grants.py`, `terminal_authorization.py`, `terminal_executor.py`, `terminal_isolation.py` | Fixed typed commands, app grants and fail-closed isolation contract exist; platform launcher/acceptance is incomplete; all templates disabled |
| Build/runtime/preview | `web_build.py`, `runtime.py`, `preview.py`, `browser_test.py` | Static/Vite/Next/Angular build paths and authenticated preview exist; broader framework/HMR/WebSocket/visual regression remain |
| Project intelligence | `project_intelligence.py`, `dcp_project_intelligence.py`, `architecture_planner.py` | Framework/project inspection and planning foundations exist; readiness and end-to-end AI workflow need closure |
| Document workflow | `tools/document_workflow/` | Writer/gateway workflow exists; complete Dashboard-to-persistent-writer acceptance and recovery need review |
| MCP engine | `tools/mcp_engine/` | Local STDIO read-only tools exist; browser integration and plugin ecosystem are not implemented |
| Developer environment | `dev_environment.py`, `local_runner_manager.py`, `universal_runner_factory.py` | Environment inspection and runner orchestration foundations exist; full visual workspace and self-upgrade remain |
| Local image lab | `tools/local_image_lab/` | Local image backend exists; complete feature and UI acceptance needs review |

## 3. Dashboard view inventory

The current Dashboard declares 21 views in `dashboard/index.html`:

1. `dev-tools`
2. `account`
3. `project-import`
4. `infrastructure`
5. `cloud-runners`
6. `github-api`
7. `repo-selector`
8. `repo`
9. `pr`
10. `user`
11. `workspace`
12. `evidence`
13. `gates`
14. `checkpoint`
15. `document-generator`
16. `terminal-studio`
17. `code-navigator`
18. `ui-routes`
19. `ui-simulator`
20. `route-colors`
21. `audit`

The view count is not equivalent to complete feature acceptance. Several views are explicitly local-only, metadata-only, prototype-only or read-only.

## 4. API surface map

Gateway route families observed in `tools/cloud_gateway/server.py` include:

- Health: `/healthz`
- Owner session and GitHub App catalog/refs/project inspection: `/api/auth/*`, `/api/github/*`
- Local project registry: `/api/local-projects/*`
- Jobs, checkpoints, logs, events and artifacts: `/api/jobs/*`, `/api/artifacts/*`
- Runner registry and controls: `/api/runners/*`, `/v1/runner/*`
- Infrastructure lifecycle and gates: `/api/infrastructure/*`
- Cloud Runner user API: `/api/cloud-runners/*`
- Terminal authorization, templates, preview and job submission: `/api/terminal/*`
- Document workflow: `/api/document-workflow/*`

Local Auth Proxy routes are implemented separately in `tools/local_auth_proxy.py`. This is a route-family map; full method/path/body/role/CSRF matrix remains an inventory task.

## 5. Workflow inventory

| Workflow | Responsibility | Evidence boundary |
|---|---|---|
| `cloud-gateway-live-smoke.yml` | Explicit live Gateway smoke | Live provider/deployment checks only when deliberately configured |
| `cross-platform-recovery.yml` | Ubuntu/Windows recovery, Runner and auth-proxy suites | GitHub-hosted CI, not user-host acceptance |
| `deploy-pages.yml` | GitHub Pages deployment | Deployment workflow; deployment not authorized by this inventory |
| `local-first-emulator.yml` | Local-first Gateway and safe-default validation | CI simulation/contract evidence |
| `macos-cloud-runner.yml` | macOS Cloud Runner path | Provider-specific acceptance; not equivalent to Windows/Linux isolation |
| `static.yml` | Static checks and site validation | Static/CI evidence |
| `validate-control-plane.yml` | Control-plane contracts and Windows dynamic-port integration | CI and contract evidence; optional self-hosted host evidence remains separate |

## 6. Main-branch baseline evidence

At the recorded baseline SHA, the following three workflows were verified successful:
- Local-first Minimal Emulator
- Validate Control Plane
- Cross-platform Recovery Acceptance

These are historical exact-SHA CI results for the baseline, not current feature-branch results and not actual user-host acceptance.

## 7. Open implementation and acceptance work

- WP-00 source-to-test/API/Dashboard/requirements mapping: IN_PROGRESS.
- WP-18A Linux bubblewrap builder: implementation slice on PR #116; not integrated into TerminalScriptExecutor; host acceptance not complete.
- WP-18B Windows AppContainer/LPAC: BLOCKED; native helper absent.
- WP-18C process-tree and scratch cleanup: PARTIAL. Linux bubblewrap uses parent-death/PID-namespace containment and has a detached-child timeout test on the GitHub-hosted Ubuntu runner. A runner-authenticated Gateway status endpoint permits delayed cleanup only for the same worker's terminal_script workspace when the Gateway explicitly attests cleanup_safe. UNKNOWN, LEASE_EXPIRED, active, recent, mismatched, unavailable and preview-retained workspaces are preserved. User-host and Windows process-tree acceptance remain UNKNOWN.
- WP-18D adversarial acceptance: PENDING.
- WP-18E CI/security/docs: PARTIAL.
- WP-19 Windows host + Dashboard → Local Auth Proxy → Gateway: UNKNOWN.
- WP-20 artifact provenance through user workflow: PARTIAL; upload/download SHA-256 and tamper rejection exist.
- WP-21 Local Folder dependency-managed targets: PARTIAL.
- WP-22 Runner interruption recovery: PARTIAL.
- WP-23 additional framework/runtime adapters: PARTIAL.
- WP-24 full Import → Build → Preview → Test: PARTIAL.
- WP-25 browser traces/visual regression/WCAG: PARTIAL.
- WP-26 dependency/license/SBOM scanner coverage: PARTIAL.
- WP-27 Developer Workspace/Visual Workflow Builder: PARTIAL.
- WP-28 operations/monitoring/backup/restore/DR: PARTIAL.
- WP-29 AI Analyze/Propose/Apply/Verify and plugins: PARTIAL.
- WP-30 self-test/upgrade/rollback: PARTIAL.
- WP-31 final repository-wide regression and release gate: NOT STARTED.

## 8. Completion rule

Do not mark a Work Package PASS based only on source presence, test-file presence, skipped CI, stale SHA evidence, or GitHub-hosted CI where real-host acceptance is required. Keep missing or unverified evidence UNKNOWN. The Repository is not E2E Complete until the full WP register, requirement traceability, critical CI and required operational acceptance are closed.
