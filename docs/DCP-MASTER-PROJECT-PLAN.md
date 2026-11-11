# DCP Master Project Plan

## Purpose
Evolve Development Control Platform into an all-in-one, local-first software development workspace. DCP should manage projects imported from GitHub repositories and explicitly approved local folders through analysis, build, runtime, real application preview, testing, diagnostics, artifacts, and recovery.

This is a target plan, not a claim that every listed capability is implemented. The current source and tests remain the authority for implementation status.

## Product principles
- Local-first: local Gateway, Local Agent, local workspaces and local data are the default execution path.
- GitHub and Local Folder are first-class project sources.
- Immutable source identity: every job records repository/folder identity, selected ref where applicable, and commit/content fingerprint.
- Evidence-based results: PASS/FAIL must link to logs, test reports, screenshots, artifact hashes and tool versions.
- Secure-by-default execution: importing source or commands never executes them.
- Explicit approval for untrusted code, dependency installation, external network access and destructive operations.
- Reuse existing Gateway, Job Control Plane, Runner, workspace, artifact and Dashboard foundations; do not create parallel services without an architectural reason.
- No automatic cloud fallback, cloud spend, deployment, VM creation or provider activation.
- All changes go through feature branches, tests and Draft PRs; no direct main edits or merge without explicit approval.

## Product capability map
1. Core Control Center: project catalog, jobs, policies, permissions, audit, events, settings and diagnostics.
2. Project Intake & Intelligence: GitHub App import, local-folder import through Local Agent, framework/toolchain detection, project configuration and templates.
3. Development Workspace: Terminal Studio, Command Library, Visual Command Builder, File Explorer, Code Editor, Git visual tools, dependency graph and multi-workspace sessions.
4. Build & Runtime: framework adapters, generic build jobs, runtime lifecycle, preview proxy/session management, emulator integration and resource limits.
5. Testing & Quality: Playwright UI/E2E, API, accessibility, responsive/cross-browser, visual regression, performance, security, dependency/license and SBOM checks.
6. Debug & Data: logs, console/network inspector, API Studio, isolated test databases, migrations, fixtures and environment profiles.
7. Delivery & Collaboration: artifacts, reports, bug tracking, review/approval, documentation, release readiness, notifications and optional team roles.
8. Operations & Recovery: runner registry, monitoring, backup/restore, self-test, upgrade checks, recovery and extension adapters.
9. Assisted Development: AI Analyze → Propose → user-approved Apply → Verify; every edit must have a diff and audit record.

## Delivery phases
- Phase 0 — Baseline, architecture, security policy and acceptance contract.
- Phase 1 — Project catalog and import: harden GitHub flow; design Local Agent folder enrollment and allowlisted roots.
- Phase 2 — Project intelligence and generic build contracts; framework/toolchain readiness.
- Phase 3 — Terminal Studio foundations: safe command catalog, preview, approval, local execution broker and audit.
- Phase 4 — Runtime lifecycle and real application preview.
- Phase 5 — Playwright UI/E2E and screenshot/report artifacts.
- Phase 6 — Quality/security scanners, API and accessibility testing.
- Phase 7 — Editor, Git visual tools, workflow builder and debugging.
- Phase 8 — Data/environment, collaboration, release and recovery.
- Phase 9 — AI-assisted changes, extension ecosystem and multi-runner scale-out.
- Phase 10 — DCP self-test and controlled self-upgrade.

Phases may be reordered only after dependency and safety review. Each phase requires a scoped feature branch, tests, evidence and review.

## Explicit infrastructure controls
- Cloud Provisioning: OFF by default and remains OFF throughout initial development.
- VM Creation: OFF by default and remains OFF throughout initial development.
- Cloud Deployment: OFF.
- Azure/Orka/provider adapters may be inspected and mock-tested, but provider composition must remain disabled.
- Dashboard controls must reflect backend-confirmed state. Backend policy must reject requests while OFF; hiding/disabling a UI button is not enforcement.
- Enabling either control in a future release requires separate explicit Owner approval, strong confirmation, budget and provider policy, audit, and acceptance testing. No automatic enabling or cloud fallback.
- Disabling blocks new operations; it must not silently delete existing resources.

## Initial release boundary
MVP: GitHub + approved Local Folder import, project detection, secure local workspace, framework adapters for static HTML/JS and selected Node web stacks, controlled build/runtime, real preview, Playwright smoke tests, artifact/report history, diagnostics, and explicit infrastructure OFF controls.

Do not promise Next.js, Angular, Flutter device execution, arbitrary Python apps, production database access, OS-level isolation or arbitrary shell execution until separately implemented and verified.

## Governance
Feature status vocabulary: EXISTING, PARTIAL, ENHANCE, MISSING, VERIFY, BLOCKED.
Every feature record includes owner/module, priority, dependencies, risk, acceptance tests, evidence and release phase.
