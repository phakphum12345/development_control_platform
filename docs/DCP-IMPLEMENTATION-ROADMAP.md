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
