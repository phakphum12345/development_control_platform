# DCP Remaining Work Inventory

**Repository:** `phakphum12345/development_control_platform`  
**Protocol:** DCP-CEEP v1.0 (Adopted)  
**Inventory baseline:** `main` at `62d72bddd028399d0b96cd9c2f6e3b16a704b758`  
**Audit date:** 2026-11-14  
**Status:** IN_PROGRESS — source-driven inventory; not a completion claim

## 1. Baseline and scope

The recursive Git tree at the baseline contains 289 entries: 265 blobs and 24 tree entries. The observed top-level inventory includes 78 files under `tools/`, 86 under `tests/`, 58 under `docs/`, 7 GitHub Actions workflows, 3 schemas, and the Dashboard, launchers, configuration, state and checkpoint assets. First-pass mapping also identified 21 Dashboard views and the Gateway route families; detailed handler-level trace remains open.

This inventory distinguishes implemented code, automated tests, CI evidence, and operational acceptance. A test existing is not proof that it ran on a target host. A passing GitHub-hosted workflow is not proof of the user's Windows host. Workstreams are grouped by acceptance boundary to avoid double-counting overlapping features.

## 2. Work Package register

| WP | Work Package | Current evidence / gap | Status |
|---|---|---|---|
| WP-00A | Repository tree and baseline capture | Exact main SHA and recursive tree captured: 289 entries / 265 blobs | PASS |
| WP-00B | Module/API/Dashboard/Workflow inventory | 78 tool files grouped by subsystem, 21 Dashboard view IDs, Gateway route families and all 7 workflows mapped; per-file entrypoint/handler tracing remains | IN_PROGRESS |
| WP-00C | Test-to-requirement traceability | All 86 baseline test files listed and mapped to 24 requirement groups; function-level and workflow/job-level trace remains | IN_PROGRESS |
| WP-00D | Documentation reconciliation | Added INDEX, IMPLEMENTATION-STATUS and REQUIREMENTS-TRACEABILITY; existing roadmap/backlog/continuity still require full reconciliation | IN_PROGRESS |
| WP-18A | Linux bubblewrap isolation launcher | Integrated into TerminalScriptExecutor; seccomp FD and allowlisted environment wired; real bubblewrap executor and detached-child tests pass on GitHub-hosted Ubuntu; target-host acceptance still UNKNOWN | PARTIAL / IN_PROGRESS |
| WP-18B | Windows native process isolation | PSEC v1.1 capability probe and design added; actual CreateProcessW integration, adversarial tests and target-host acceptance remain BLOCKED | IN_PROGRESS / BLOCKED |
| WP-18C | Process-tree containment and cleanup | Linux bubblewrap parent-death containment now has a detached-descendant timeout test; authenticated Gateway cleanup attestation and conservative terminal-workspace reconciliation added. UNKNOWN, lease-expired, active, mismatched and retained workspaces are preserved; user-host/Windows acceptance remains absent | PARTIAL / IN_PROGRESS |
| WP-18D | Adversarial security and host acceptance | Added real bubblewrap tests for socket families, socketpair, io_uring denial, zero effective capabilities, host-secret symlink isolation, and a target-Linux host acceptance harness; GitHub-hosted CI evidence only, target-host evidence remains UNKNOWN | PARTIAL / IN_PROGRESS |
| WP-18E | Isolation CI, security review and documentation | Cross-platform recovery workflow exists; no platform sandbox acceptance matrix or independent host evidence | IN_PROGRESS |
| WP-19 | Windows host and Dashboard → Local Auth Proxy → Gateway acceptance | Unit/integration contracts exist; live supported Windows-host evidence not present in the reviewed ledger | UNKNOWN |
| WP-20 | Artifact provenance and end-to-end SHA-256 verification | Gateway hashes upload and re-verifies downloaded bytes; tamper tests exist; Dashboard-to-download provenance acceptance remains | PARTIAL |
| WP-21 | Local Folder dependency-managed build targets | Immutable snapshots, trust allowlist and static/Vite builds exist; broader dependency-managed targets and install policy remain | PARTIAL |
| WP-22 | Runner interruption recovery and workspace lifecycle | Durable checkpoints, replay and cleanup code/tests exist; independent process and filesystem cleanup after host interruption remains | PARTIAL |
| WP-23 | Framework build/runtime adapters | Static, Vite, Next.js and Angular build paths exist; broader framework/runtime/HMR/WebSocket coverage remains | PARTIAL |
| WP-24 | Full Dashboard Import → Build → Preview → Test journey | Individual import, build, authenticated preview and browser-test capabilities exist; complete imported-project user journey and host evidence remain | PARTIAL |
| WP-25 | Browser traces, visual regression and accessibility | Browser tests and viewport checks exist; trace retention, visual baselines and full WCAG/axe acceptance remain | PARTIAL |
| WP-26 | Security scanners and supply-chain evidence | Existing security controls and workflow checks require complete scanner coverage review; dependency/license/SBOM policy and artifact evidence remain | PARTIAL |
| WP-27 | Developer Workspace and Visual Workflow Builder | Dashboard navigation, code navigator and route manager contracts exist; full editable workspace and visual workflow execution remain | PARTIAL |
| WP-28 | Operations, monitoring, backup/restore and disaster recovery | Gateway/provider lifecycle, budgets and cleanup controls exist; operational observability, backup restore drills and DR acceptance remain | PARTIAL |
| WP-29 | AI Analyze/Propose/Apply/Verify and plugin ecosystem | Project intelligence/planner/MCP foundations exist; bounded approval-gated end-to-end lifecycle and plugin contracts need completion | PARTIAL |
| WP-30 | DCP self-test, upgrade and rollback | Health/preflight/self-check foundations exist; signed/versioned upgrade, rollback and recovery acceptance remain | PARTIAL |
| WP-31 | Final repository-wide regression and release gate | No final source-to-requirement closure report or complete operational acceptance evidence | NOT STARTED |

**Register count:** 22 Work Packages (WP-00A–D and WP-18A–E and WP-19–WP-31). This is the current work-package grouping, not a claim that every atomic subtask has been discovered. WP-00A–D remain open until the full source/test/workflow/API/dashboard/docs mapping is complete.

## 3. Evidence reviewed

### Terminal isolation and process lifecycle
- `tools/local_runner_agent/terminal_isolation.py` — platform assessment only; Linux bwrap presence cannot become VERIFIED.
- `tools/local_runner_agent/terminal_executor.py` — calls `require_verified_isolation()` before workspace resolution and process launch; uses `taskkill /T /F` on Windows and POSIX process groups elsewhere; timeout/cancel/error cleanup paths exist.
- `tools/local_runner_agent/workspace.py` — owner-bound workspace marker, quotas, symlink rejection, preview retention and cleanup.
- `tests/test_terminal_isolation.py` — six contract tests; no real host sandbox test.
- `tests/test_terminal_executor.py` — process timeout, cancellation, output limits and policy tests; not OS sandbox acceptance.
- `docs/DCP-TERMINAL-OS-ISOLATION.md` — correctly states all platforms BLOCKED and all templates disabled.

### Artifact integrity
- `tools/cloud_gateway/artifacts.py` — hashes upload stream with SHA-256, stores digest, verifies digest when opening download.
- `tests/test_cloud_gateway_artifacts.py` — includes tamper rejection.
- `tests/test_cloud_gateway_artifact_download.py` — includes exact bytes/ETag and tamper rejection.
- Remaining issue is end-to-end provenance acceptance through the Dashboard/user journey, not missing basic hash code.

### Runner and Dashboard integration
- `tools/local_runner_agent/pipeline.py` — Local Folder snapshot/trust checks, build dispatch, artifact upload, preview retention, checkpoints and cleanup.
- `tests/test_local_runner_pipeline_e2e.py` — covers static build, browser test evidence, artifact upload, terminal grant/workspace path, replay and Windows command path.
- `tests/test_dashboard_contract.py` — broad Dashboard route, import, job, preview, Terminal and safety contracts.
- These are code-level/integration tests; live Windows host acceptance remains separate.

## 4. First-pass API and Dashboard map

- Gateway route families: health, owner session, GitHub App repository/refs/project inspection, Local Project registry, Jobs/checkpoints/logs/events, artifacts/download, runners, infrastructure, Cloud Runner, Terminal, document workflow, and Runner v1 registration/ping/claim.
- Local Auth Proxy exposes a separate authenticated same-origin route surface; method/role/CSRF detail remains to be traced.
- Dashboard contains 21 views: `dev-tools`, `account`, `project-import`, `infrastructure`, `cloud-runners`, `github-api`, `repo-selector`, `repo`, `pr`, `user`, `workspace`, `evidence`, `gates`, `checkpoint`, `document-generator`, `terminal-studio`, `code-navigator`, `ui-routes`, `ui-simulator`, `route-colors`, `audit`.
- Detailed view → DOM handler → API call → service → test mapping remains IN_PROGRESS.

## 5. CI baseline

At the inventory baseline, the three main-branch workflows previously checked completed successfully:
- Local-first Minimal Emulator
- Validate Control Plane
- Cross-platform Recovery Acceptance

These runs are tied to the exact baseline SHA recorded above. They are CI evidence only, not real-host acceptance. Re-run and record exact head SHA evidence for each PR.

The repository contains seven workflow files:
- `.github/workflows/cloud-gateway-live-smoke.yml`
- `.github/workflows/cross-platform-recovery.yml`
- `.github/workflows/deploy-pages.yml`
- `.github/workflows/local-first-emulator.yml`
- `.github/workflows/macos-cloud-runner.yml`
- `.github/workflows/static.yml`
- `.github/workflows/validate-control-plane.yml`

## 6. Critical safety gates

1. All seven built-in Terminal templates remain disabled.
2. Do not set any platform to VERIFIED from executable presence or unit tests.
3. Windows AppContainer/LPAC requires a native launcher and actual-host acceptance; Job Objects alone are insufficient.
4. Linux requires an explicit mount namespace, user/PID/IPC/UTS/network namespaces, reviewed seccomp policy, assigned workspace and per-job scratch, plus actual-host adversarial acceptance.
5. Process-tree termination and scratch cleanup must be independently verified after normal exit, timeout, cancellation, lease loss, Runner shutdown and crash.
6. CI results must be tied to exact head SHA and must not be described as user-host acceptance.
7. No PR merge without required gates and explicit user authorization.

## 7. Documentation gaps

Added on the inventory branch (not yet merged):
- `docs/INDEX.md`
- `docs/IMPLEMENTATION-STATUS.md`
- `docs/REQUIREMENTS-TRACEABILITY.md`

These additions provide the first-pass catalog and traceability structure. They do not close all per-file or per-test mapping.

Existing roadmap, backlog and continuity documents require reconciliation with merged PR #115 and current source. Do not overwrite historical audit records; append dated, SHA-scoped checkpoints.

## 8. Next execution sequence

1. Complete WP-00B/00C by mapping every source module, API route, Dashboard view, workflow, test and requirement.
2. Complete WP-00D by reconciling roadmap/backlog/continuity and adding status/traceability docs.
3. WP-18A executor integration is implemented; run WP-18D adversarial tests and the documented Linux target-host acceptance harness before any production enablement.
4. Implement WP-18C process-tree and cleanup verification in parallel only where dependencies allow.
5. Implement WP-18B Windows native isolation separately; do not substitute a POSIX shim.
6. Run exact-head CI, security review and host acceptance before considering any template enablement.
7. Continue WP-19–WP-31 in dependency order and close with WP-31 final audit.

## 9. Current limitations

This inventory is source-driven but still IN_PROGRESS. It does not yet enumerate every atomic acceptance criterion for all 78 tool files and 86 test files. No total atomic task count is claimed until WP-00B/00C produce a traceable one-to-one register. No implementation completion, host acceptance or merge is claimed by this document.
