# DCP Implementation Status — Current Main Baseline

**Repository:** `phakphum12345/development_control_platform`  
**Main SHA:** `985a78d5fba459c8a0cbcf47e5d00a858c6e6228`  
**Audit date:** 2026-11-19  
**Protocol:** DCP-CEEP v1.0 (adopted)  
**Overall:** IN_PROGRESS — no repository-wide completion claim.

## Status vocabulary

- **EXISTING:** capability/source slice is present; not necessarily complete.
- **PARTIAL:** meaningful implementation exists but one or more acceptance boundaries remain.
- **ENHANCE:** implementation exists and needs hardening or coverage.
- **MISSING:** required capability was not found in the inspected mainline evidence.
- **VERIFY:** source exists but behavior/coverage has not yet been fully traced.
- **BLOCKED:** safety or environment gate prevents execution/acceptance.
- **DEFERRED:** intentionally not activated or not in current delivery scope.

## 1. Capability status

| Capability | Status | Mainline evidence | Remaining acceptance / limitation |
|---|---|---|---|
| Local Gateway and Auth Proxy | PARTIAL | `tools/cloud_gateway/server.py`, `tools/local_auth_proxy.py`; local emulator and Auth Proxy tests | Complete endpoint/method/auth/CSRF matrix; deployed identity edge and production session acceptance |
| Owner identity / OIDC ingress | PARTIAL | OIDC client, assertion, signer, trusted-proxy and deployment modules/docs | Live deployed OIDC callback, issuer/audience/nonce/replay/session revocation and reverse-proxy acceptance not evidenced |
| SQLite Job Control Plane | PARTIAL | `job_control.py`, `store.py`, scheduler and durable checkpoint tests | Full lifecycle/idempotency/lease-loss/cancel/restore acceptance and data migration audit |
| GitHub App project intake | PARTIAL | `github_app.py`, `github_app_runtime.py`, public catalog and commit inspection | Immutable source binding and complete Dashboard → Job → Runner provenance acceptance |
| Local Folder intake | PARTIAL | `local_project.py`, `checkout.py`, snapshot/workspace/pipeline tests | Main documented slice supports bounded static targets; real Windows host and artifact/download journey acceptance remain |
| Framework/toolchain intelligence | PARTIAL | Project intelligence and manifest-backed detection modules | Toolchain readiness and job-level enforcement for all advertised targets |
| Build adapters | PARTIAL | `web_build.py`, pipeline; static/Vite/Next.js/Angular and fixed Flutter paths described in docs | Dependency install policy, framework-specific acceptance, imported-code trust and wider support |
| Runtime Manager / Preview | PARTIAL | `runtime.py`, `preview.py`, Auth Proxy integration | Static and selected fixed runtime slices exist; arbitrary servers, HMR/WebSocket and general app compatibility are not established |
| Terminal Studio UI / command packs | PARTIAL | Dashboard Terminal view, catalog/templates/grants and JSON schema | UI/catalog and inert import exist; interactive PTY and unrestricted command execution are not supported |
| Terminal process execution | BLOCKED | `terminal_executor.py` requires verified isolation; seven built-in templates documented disabled | No template enablement until platform sandbox, adversarial host acceptance and process-tree cleanup pass |
| Linux OS isolation | BLOCKED | `linux_sandbox.py`, `terminal_isolation.py`, tests | Builder/policy and CI checks do not establish production integration or independent host acceptance |
| Windows AppContainer/LPAC | BLOCKED | No Windows PSEC implementation in current main tree; code exists on PR #140/#149 branches | Trusted runtime, native PSEC support, effective ACL, host acceptance and target machine evidence |
| macOS App Sandbox | BLOCKED | Design/adapter references and cloud runner workflows | Signed helper, entitlements, real host acceptance and process/network/filesystem boundary |
| Artifact SHA-256 integrity | EXISTING / PARTIAL | `artifacts.py`, Runner artifact modules, tamper tests | End-to-end job/source/commit provenance, retention and Dashboard download evidence |
| Browser testing | PARTIAL | Playwright tests and Chromium/Firefox/WebKit Preview Proxy fixture checks | Full imported-app coverage, traces, visual regression, keyboard and WCAG/axe evidence |
| Dashboard Control Center | PARTIAL | `dashboard/index.html`, contract tests, browser smoke | Full view/action/API/auth/error/loading/accessibility trace and live user journey |
| Cloud Runner provider adapters | PARTIAL / DEFERRED | Azure/Orka/provider/budget/bootstrap/cleanup modules and tests | Production composition/live provider acceptance absent; provisioning and VM creation remain OFF |
| Monitoring and diagnostics | PARTIAL | Local doctor, preflight, health, logs and runner diagnostics | Durable metrics, alerting, diagnostics bundle and operational restore drill |
| Backup / restore / disaster recovery | PARTIAL / VERIFY | SQLite and recovery foundations/tests | Backup format, restore preview, corruption drill and actual host recovery evidence |
| Document workflow / local writer | PARTIAL | Document workflow gateway/writer and dashboard scope/proposal flow | Full authenticated end-to-end write lifecycle and durable cross-restart evidence |
| MCP integration | EXISTING (READ-ONLY SLICE) | `tools/mcp_engine/`, native MCP tests/docs | Current server intentionally has bounded read/inspect/diff/preview; no write, shell, Git or cloud execution |
| AI Analyze/Propose/Apply/Verify | PARTIAL / MISSING | Project intelligence/planner and read-only MCP foundations | Complete approval-gated edit/apply/diff/test/audit loop is not established |
| Packaging / Windows installation | PARTIAL | `package-release.yml`, `packaging/package-release.ps1`, Inno Setup definition | Real clean-machine install, upgrade, rollback, uninstall and recovery acceptance |
| Collaboration / plugin ecosystem | MISSING / DEFERRED | No complete signed plugin/role collaboration lifecycle evidenced | Design only after core security and product requirements are accepted |

## 2. Hard safety gates

1. Cloud Provisioning, VM Creation and Cloud Deployment remain OFF unless the Owner separately authorizes an exact provider, target, scope and cost ceiling.
2. No automatic cloud fallback is authorized.
3. Terminal templates remain disabled while OS isolation is not VERIFIED.
4. Workspace isolation, browser restrictions and Job Objects alone must not be described as an OS sandbox.
5. GitHub-hosted CI success does not substitute for real target-host acceptance.
6. PR #140 and #149 are not merged; their Windows PSEC work is not part of this main baseline.
7. Do not infer production OIDC readiness from code or configuration templates.

## 3. Exact PR evidence reviewed

- PR #140 head `8bf0b74859c3749070eafbd7906d9c7df6d0822b`: five workflows completed successfully. Its Validate Control Plane self-hosted Windows acceptance job was SKIPPED. The informational Windows PSEC probe emitted `state=BLOCKED` because `processmodel.dll` was unavailable from the System32 search path.
- PR #149 head `44ec9f4b95601071b172a9b541387399591745b7`: four workflows completed successfully. Its optional self-hosted Windows acceptance job was SKIPPED. The informational PSEC probe also emitted `state=BLOCKED` for missing `processmodel.dll`.
- PR #149 has an overlapping launcher/test scope with #140 and divergent branch ancestry. No reconciliation or merge was performed.
- A previous real target-host attempt recorded exit code 106 and `No pyvenv.cfg file` inside the sandboxed child. Treat this as historical failure evidence; do not assume the current branch has resolved it.

## 4. What this status does not claim

This document is a source-and-evidence status snapshot, not a live service health check, local-machine inspection, release certification, security certification, or assertion that all tests were rerun on this branch.
