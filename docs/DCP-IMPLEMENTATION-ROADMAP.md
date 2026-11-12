# DCP Implementation Roadmap

## Phase 0 — Baseline & Safety (current)
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
- Remaining: Dashboard project catalog/picker, authenticated project selection UX, immutable job snapshot/materialization, and end-to-end import-to-job binding.

- Dashboard Project Import workspace added: authenticated owner-only GitHub App repository/ref/commit inspection and Local Project catalog selection. This is a read-only source-selection UI; immutable snapshot materialization and job binding remain outstanding.


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
- An authenticated static Preview Proxy service is now present for owner-bound preview sessions. The PR #71 Playwright implementation still starts RuntimeManager directly, so Playwright-through-Preview-Proxy and the complete Dashboard preview workflow remain separate acceptance work.


## 2026-11-12 implementation checkpoint — PR #71

This checkpoint is tied to the DCP repository branch `feature/real-project-playwright-testing`, not to the user's local machine or a deployed service.

| Workstream | Current evidence-backed state | Remaining acceptance |
|---|---|---|
| Import foundation | Local Folder enrollment, owner-only catalog, verified snapshot materialization and GitHub commit inspection exist in prior slices. | Persisted job binding and end-to-end source-to-runner provenance still require focused acceptance. |
| Project intelligence | Read-only manifest-backed framework detection exists. | Toolchain readiness and broader adapter coverage remain separate. |
| Universal Web Build | Static HTML/CSS/JS and React/Vite + Vue/Vite targets exist; dependency install is not automatic. | Broader framework support and host-specific acceptance. |
| Runtime | Loopback static Runtime Manager exists with bounded health/log/session/process lifecycle. | General application servers and additional runtime adapters. |
| Preview | Authenticated owner-bound static Preview Proxy primitives exist. | Full Dashboard path and browser automation through the proxy. |
| Playwright | Opt-in static-project smoke suite, three viewport screenshots, JSON report and bounded ZIP evidence exist. | Current CI sandbox launch blocker, actionable host diagnostics, and Preview Proxy E2E. |
| Quality/security | Existing baseline controls remain in place. | Dedicated scanners, full accessibility, visual regression and cross-browser suites. |

### PR #71 release gate

The latest observed CI result on `52a99f2403c7ffc5c8d82fe44cbb477f8189b325` installed Python Playwright and Chromium successfully, but the real Chromium smoke test failed at sandboxed browser launch. Later Dashboard browser smoke and registry validation steps were skipped. Windows dynamic-port and Windows Auth Proxy/Gateway checks passed; self-hosted Windows Runner acceptance was skipped. A subsequent code change adds bounded launch-error diagnostics; its exact-commit CI result is still required.

Do not merge PR #71 until the real Chromium sandbox test, Dashboard browser smoke, registry validation, and all required checks pass on the same final head SHA. Do not disable Chromium sandboxing as a CI workaround.

## 2026-11-12 implementation checkpoint — Terminal Studio read-only slice

- Added a curated command catalog for Git status/diff/log and Python/Node version diagnostics.
- Added authenticated owner/operator API endpoints for catalog retrieval and exact argv preview.
- Preview accepts only a known template identifier, rejects arbitrary command fields, and enforces same-origin plus CSRF checks.
- Catalog entries deny network access, declare bounded time/output, and remain `PREVIEW_ONLY` with execution disabled.
- Added unit and authenticated HTTP tests for template safety, defensive copies, authorization, exact argv and rejection paths.
- Remaining Terminal Studio work: inert command-pack import/export, project/workspace binding, typed task submission, Local Agent execution broker, explicit approval, cancellation, bounded/redacted logs and history. No arbitrary shell/PTY is exposed.


## 2026-11-12 implementation checkpoint — Terminal Studio Dashboard

- Added a Dashboard Terminal Studio navigation view.
- Connected the view to the authenticated read-only catalog and argv preview APIs using same-origin credentials and the existing CSRF token.
- Added UI contract coverage and Code Navigator mapping.
- The Dashboard clearly labels this as PREVIEW ONLY; no shell, PTY, command execution, or workspace binding is enabled.


## 2026-11-12 implementation checkpoint — inert Terminal command-pack import

- Added strict v1 JSON command-pack validation with request/template/argv/time/output bounds and allowlisted executable identifiers.
- Added owner-only, same-origin, CSRF-protected import endpoint.
- Imported templates persist in a private SQLite store, with atomic duplicate rejection and audit records.
- Imported templates remain disabled and pending review; preview is informational only and never launches a process.
- Added validator, persistence, rollback, API authorization and unsafe-input tests.
- Remaining: Dashboard import workflow, template review/edit lifecycle, project/workspace binding, approved Local Agent execution broker, cancellation and redacted logs/history.


## 2026-11-12 implementation checkpoint — Terminal Studio import UI

- Added a Dashboard JSON command-pack import form using the existing authenticated owner session and CSRF token.
- The UI submits parsed JSON only, displays the import SHA-256, refreshes the catalog and selects an imported template for pending-review preview.
- Script-file upload and command execution remain out of scope for this increment.
- Added Dashboard contract assertions for the import controls and endpoint.


## 2026-11-12 implementation checkpoint — Terminal template Owner review

- Added explicit approve/reject review states for imported command templates.
- Owner review is bound to the stored source SHA-256 and an exact typed confirmation phrase.
- Added Owner-only review API and Owner/Operator audit-history read API.
- Approval leaves enabled=false and execution_enabled=false; the preview state is APPROVED_NOT_EXECUTABLE.
- Added unit and authenticated API tests for authorization, stale hashes, confirmation, audit and non-executable approval.
- Remaining: Dashboard review controls, workspace-bound typed jobs, policy-approved Local Agent execution, cancellation, redacted logs and history.
