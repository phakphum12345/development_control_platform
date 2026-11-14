# DCP Documentation Index

**Repository:** `phakphum12345/development_control_platform`  
**Protocol:** DCP-CEEP v1.0 — Adopted  
**Status:** IN_PROGRESS — index of current documentation; verify source freshness before relying on status claims

## Operating and execution control
- [DCP-CEEP v1.0 Protocol](DCP-CEEP-PROTOCOL.md) — mandatory execution, evidence, resilience, reporting, continuity and merge gates.
- [Continuity Ledger](../checkpoints/DCP-CEEP-CONTINUITY.md) — latest resumable work checkpoint.
- [CEEP Command Reference](DCP-CEEP-COMMAND-REFERENCE.md)
- [CEEP Project Profile Template](templates/DCP-CEEP-PROJECT-PROFILE.md)
- [CEEP v2.0 Proposal](DCP-CEEP-UNIVERSAL-v2.0.md) — proposal only; not adopted.
- [CEEP v2.0 Migration](DCP-CEEP-V2-MIGRATION.md)

## Repository status, requirements and roadmap
- [Implementation Roadmap](DCP-IMPLEMENTATION-ROADMAP.md)
- [Master Feature Backlog](DCP-MASTER-FEATURE-BACKLOG.md)
- [Master Project Plan](DCP-MASTER-PROJECT-PLAN.md)
- [Implementation Status](IMPLEMENTATION-STATUS.md) — source-backed status summary; still in progress.
- [Requirements Traceability](REQUIREMENTS-TRACEABILITY.md) — requirements mapped to source/tests/workflows; still in progress.
- [Remaining Work Inventory](DCP-REMAINING-WORK-INVENTORY.md) — Work Package register and gaps; not the final atomic task count.
- [Repository Audit 2026-11-11](DCP-REPOSITORY-AUDIT-2026-11-11.md)
- [Repository Audit 2026-11-12](DCP-REPOSITORY-AUDIT-2026-11-12.md)
- [Acceptance Test Plan](DCP-ACCEPTANCE-TEST-PLAN.md)

## Architecture and platform
- [DCP Architecture](DCP-ARCHITECTURE.md)
- [Own Platform Architecture](dcp-own-platform-architecture.md)
- [Own Infrastructure Roadmap](dcp-own-infrastructure-roadmap.md)
- [Security and Safety Policy](DCP-SECURITY-AND-SAFETY-POLICY.md)
- [Security Readiness Audit 2026-11-08](security-readiness-audit-2026-11-08.md)

## Gateway, identity and cloud runners
- [Cloud Gateway Core](cloud-gateway-core.md)
- [Cloud Runner Architecture](cloud-runner-architecture.md)
- [Cloud Runner Control Plane](cloud-runner-control-plane.md)
- [Cloud Runner User API](cloud-runner-user-api.md)
- [Cloud Runner Lifecycle Cleanup](cloud-runner-lifecycle-cleanup.md)
- [Cloud Runner Completion Audit 2026-11-12](cloud-runner-completion-audit-2026-11-12.md)
- [Runner Scheduler](runner-scheduler.md)
- [Local Job Control Plane](local-job-control-plane.md)
- [Local Runner Manager](local-runner-manager.md)
- [Local Auth Proxy Dashboard Routes](local-auth-proxy-dashboard-routes.md)
- [Authentication Deployment](authentication-deployment.md)
- [OIDC Ingress](oidc-ingress.md)
- [Gateway Deployment Preflight](gateway-deployment-preflight.md)
- [Live Cloud Gateway Acceptance](live-cloud-gateway-acceptance.md)
- [Infrastructure Manager](infrastructure-manager.md)
- [Azure Production Deployment](azure-production-deployment.md)
- [Azure VM Provisioner](azure-vm-provisioner.md)
- [Azure Runner Bootstrap](azure-runner-bootstrap.md)
- [Azure Identity, Key Vault and Budget](azure-identity-keyvault-budget.md)
- [GitHub App Runner Bootstrap](github-app-runner-bootstrap.md)
- [Orka Adapter](orka-adapter.md)
- [macOS Cloud Runner Control Plane](macos-cloud-runner-control-plane.md)

## Local development, build and browser testing
- [Local-first Mode](local-first-mode.md)
- [Local Folder Build](DCP-LOCAL-FOLDER-BUILD.md)
- [Web Build Engine](web-build-engine.md)
- [Authenticated Preview](DCP-AUTHENTICATED-PREVIEW.md)
- [Playwright Testing](DCP-PLAYWRIGHT-TESTING.md)
- [Local Image Lab](local-image-lab.md)
- [Windows 11 One-click Setup](windows-11-one-click.md)
- [Windows 11 Self-hosted Runner](windows-11-self-hosted.md)

## Terminal Studio and command execution
- [Terminal Studio](DCP-TERMINAL-STUDIO.md)
- [Terminal API](DCP-TERMINAL-API.md)
- [Terminal Execution Architecture](DCP-TERMINAL-EXECUTION-ARCHITECTURE.md)
- [Terminal Security](DCP-TERMINAL-SECURITY.md)
- [Terminal OS Isolation](DCP-TERMINAL-OS-ISOLATION.md)
- [Terminal Runner Setup](DCP-TERMINAL-RUNNER-SETUP.md)
- [Command Library](DCP-COMMAND-LIBRARY.md)

## Developer tools, intelligence and documents
- [Selective Code Monitor and Editor](selective-code-monitor-editor.md)
- [Document Generator Operations](document-generator-operations.md)
- [Self-learning Runner Platform](self-learning-runner-platform.md)
- [Native MCP Engine](native-mcp-engine.md)
- [Native MCP Engine Test Plan](native-mcp-engine-test-plan.md)

## Maintenance rule

Every Work Package must update the relevant implementation, requirements, test and acceptance documentation. Preserve historical audit records; append dated, exact-SHA checkpoints rather than rewriting old evidence. If a document conflicts with source code or a newer exact-SHA checkpoint, mark the older statement stale and reconcile it through a reviewed change.
