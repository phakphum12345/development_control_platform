# DCP Implementation Roadmap

## Phase 0 — Baseline & Safety (baseline established)
Inventory actual source, tests, workflows, existing APIs and current cloud/VM gate behavior. Reconcile older roadmap statements with code. Establish feature branch, acceptance matrix and non-destructive workflow.

## Phase 1 — Import foundation
Harden existing GitHub App import; add Local Agent enrollment for explicit allowed folders; unify project identity and immutable source snapshot metadata.

## Phase 2 — Project intelligence & adapters
Add framework/toolchain detection and adapter contracts. Start with static HTML/JS and Node/Vite. Keep Flutter executor as a separate existing adapter with its current trust/opt-in constraints.

## Phase 3 — Terminal Studio MVP
Command Library, safe templates, inert import/export, typed Visual Command Builder, exact-command preview, approval and local execution broker. Do not expose arbitrary shell as a browser API.

## Phase 4 — Build, Runtime & Preview
Generic web build adapter, supervised process lifecycle, isolated ports, preview proxy/session expiry and process-tree cleanup.

## Phase 5 — Testing & Evidence
Playwright against real preview, screenshots/traces/reports, artifact provenance and hashes, history and evidence-backed quality gates.

## Phase 6 — Security & Quality
Dependency/secrets/license/SBOM scanners, accessibility, responsive/cross-browser, visual regression, API tests and bounded performance tests.

## Phase 7 — Developer Workspace
File Explorer/editor, Git visual history/diff, dependency graph, Debug Center and Visual Workflow Builder. All write operations require diff and approval.

## Phase 8 — Operations & Delivery
Database/test environment manager, documentation, bug/release workflows, monitoring, backup/restore and disaster recovery.

## Phase 9 — Intelligence & Extensions
AI Analyze/Propose/Apply/Verify with explicit approval; plugin/adapter ecosystem with provenance and permissions; multi-runner after local controls are stable.

## Phase 10 — DCP Self-Test & Upgrade
Run regression against isolated test workspace, verify recovery point, test upgrade compatibility and provide rollback evidence.

## Phase gates
Each phase is a separate feature branch and Draft PR, with narrowly scoped changes, automated tests, security review and exact-commit evidence. No merge without explicit user approval.


## Phase 1 progress — Local Folder intake foundation
- Implemented the Local Agent registry for explicitly enrolled roots and project snapshot fingerprints.
- Added local CLI operations to enroll roots, register projects and list the registry.
- Added owner-only, read-only Gateway endpoints and Local Auth Proxy allowlisting; absolute host paths are not returned.
- Dashboard Project Import workspace provides authenticated owner-only GitHub App repository/ref/commit inspection and Local Project catalog selection.
- Local Folder jobs are accepted only for registered project IDs and current snapshot SHA-256; the Gateway revalidates the fingerprint, safe inventory, framework and supported target before queueing.
- Runner pipeline materializes the registered Local Project snapshot and verifies the selected SHA before building; end-to-end Local Folder build tests are present.
- Remaining: broader project-source provenance and GitHub App import-to-build acceptance for more than the existing Flutter/static-web targets.


## Phase 2 progress — read-only project intelligence
- Extended the existing bounded project inventory with evidence-based primary framework detection for static HTML/JS, React/Vite, Vue/Vite, Next.js, Angular, Flutter, Python, FastAPI, Django and Flask.
- Reports package manager, declared Node/Python/Dart constraints and declared npm scripts without running them.
- Toolchain readiness remains NOT_CHECKED; unknown or malformed evidence is not promoted to a supported build.
- No dependency installation, network access, source execution or build command is performed during detection.


## Universal Build Engine — first implementation slice
- Added Local Runner targets for static HTML/CSS/JS and React/Vite or Vue/Vite.
- Static web builds copy the project into a bounded `dist/` tree without executing source.
- Vite builds invoke only the locally installed Vite CLI through Node; dependency installation and npm lifecycle scripts are not run.
- Vite config/application build code is still executable project code and requires the Runner's explicit execution opt-in and trusted-repository allowlist.
- Build output is packaged as a bounded ZIP artifact and uploaded through the existing authenticated artifact channel.
- Framework detection, job target validation, runner scheduling, and local Runner dispatch are connected.
- Follow-up acceptance: verify the complete host build workflow and SHA-256 provenance on supported local Windows hosts. The initial static Runtime Manager and authenticated static Preview Proxy slices have since been implemented; broader framework runtimes remain out of scope.


## Runtime Manager — initial local static runtime slice
- Added a loopback-only static runtime supervisor for already-built output.
- Starts the Python standard-library HTTP server with an argv array; no shell or project server code is executed.
- Allocates an ephemeral loopback port, verifies HTTP health, records bounded logs, supervises process-tree shutdown and expires runtime sessions.
- Runtime session capabilities are random and required for local status/log/stop operations.
- An authenticated static Preview Proxy service is present for owner-bound preview sessions.
- A dedicated real-Chromium test now starts the preview through the owner-authenticated Local Auth Proxy API and exercises the browser-facing preview URL with sandboxing enabled.


## 2026-11-12 implementation checkpoint — PR #71

This checkpoint is tied to the DCP repository branch `feature/real-project-playwright-testing`, not to the user's local machine or a deployed service.

| Workstream | Current evidence-backed state | Remaining acceptance |
|---|---|---|
| Import foundation | Local Folder enrollment, owner-only catalog, verified snapshot materialization and GitHub commit inspection exist in prior slices. | Persisted job binding and end-to-end source-to-runner provenance still require focused acceptance. |
| Project intelligence | Read-only manifest-backed framework detection exists. | Toolchain readiness and broader adapter coverage remain separate. |
| Universal Web Build | Static HTML/CSS/JS and React/Vite + Vue/Vite targets exist; dependency install is not automatic. | Broader framework support and host-specific acceptance. |
| Runtime | Loopback static Runtime Manager exists with bounded health/log/session/process lifecycle. | General application servers and additional runtime adapters. |
| Preview | Authenticated owner-bound static Preview Proxy and owner-only Dashboard lifecycle are implemented. | Broader cross-owner model and full runtime/framework coverage. |
| Playwright | Opt-in static-project smoke suite, three viewport screenshots, JSON report, bounded ZIP evidence, and sandboxed Chromium through authenticated Preview Proxy are tested. | Cross-browser engines, trace capture, visual baselines and full WCAG/axe coverage. |
| Quality/security | Existing baseline controls remain in place. | Dedicated scanners, full accessibility, visual regression and cross-browser suites. |

### PR #71 release gate — resolved

PR #71 was subsequently corrected with a path-scoped AppArmor user-namespace profile for the exact Playwright Chromium headless-shell executable. The real browser test passed with `chromium_sandbox=True`; no `--no-sandbox` workaround or global AppArmor disable was used. Dashboard browser smoke and registry validation passed on the final PR head. PR #71 was merged to main; its earlier failed runs are historical and are not current acceptance evidence.




## 2026-11-12 current checkpoint — infrastructure gates, job recovery and unified Runner

Merged feature slices on main:
- PR #75: persistent independent Cloud Provisioning and VM Creation gates; owner-only confirmation, provider-readiness checks, audit, Local Auth Proxy routes and fail-closed backend enforcement.
- PR #76: Dashboard controls for both independent gates; UNKNOWN on backend failure; Cloud Runner create UI requires effective Cloud Provisioning.
- PR #77: durable job attempt_count/max_attempts, three-attempt lease recovery, terminal LEASE_EXPIRED, last_worker provenance, and concurrent-claim tests.
- PR #78: two-worker authenticated Gateway HTTP acceptance for lease recovery, stale-worker fencing and current-worker completion.
- PR #79: unified Windows launcher through tools.local_runner_agent, offline enrollment, opt-in --once/--serve, bounded polling/backoff and graceful stop after the current job returns.

Safety remains unchanged: Cloud Provisioning OFF, VM Creation OFF, external providers disabled, no paid cloud/VM resource created by these slices.

## Authenticated Preview Proxy — browser acceptance in progress

A new acceptance slice adds real Chromium coverage through the owner-authenticated Preview Proxy, rather than calling RuntimeManager directly. The browser test uses the same-origin session cookie, sandboxed Chromium, HTML/CSS assertions, request/error checks, screenshot evidence and verifies that stopping the preview makes the browser URL unavailable. CI on the exact PR head is required before this checkpoint is considered accepted.

## Remaining major work packages

1. Runner crash/workspace reconciliation and process-supervisor hardening; lease retries are bounded, but orphaned workspace cleanup must remain fail-closed.
2. Artifact retention policies, provenance manifests and release/report workflows.
3. Flutter Dashboard parity for the existing authenticated DCP APIs; HTML Dashboard remains the supported UI until Flutter parity is tested.
4. Terminal Studio safe command library and typed command builder with inert script import.
5. Broader framework build/runtime adapters and Playwright tests for supported projects through the authenticated preview path.
6. Quality/security scanners, SBOM/license/secret checks, full accessibility and visual regression.
7. Backup/restore, recovery drills, upgrade/rollback and complete local acceptance.
8. Optional live provider acceptance remains disabled and requires separate explicit owner authorization, budget and cleanup evidence.
