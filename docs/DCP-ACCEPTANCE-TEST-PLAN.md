# DCP Acceptance Test Plan

Acceptance evidence must be produced on the exact commit under review. A passing test on another branch/head is not evidence for this change.

## Baseline and regression
- Run complete Python unit suite and relevant integration tests.
- Run Dashboard browser smoke tests.
- Run Windows local auth-proxy and dynamic-port launcher integration tests where supported.
- Verify local startup/stop and health endpoints without contacting cloud providers.
- Confirm no existing owner data, local database or backups are reset.

## Project import
- GitHub: public/private authorization as configured, installation membership, refs, immutable full commit SHA and second server-side verification.
- Local: only enrolled allowed roots; reject traversal, symlink escape, inaccessible path and unauthorized Agent.
- Detection: supported framework only when manifests and toolchain evidence exist; report UNKNOWN for incomplete evidence.

## Build/runtime
- Build command comes from an adapter allowlist; no arbitrary shell input.
- Verify successful and failed exit codes, timeout, bounded logs, environment isolation and process-tree cancellation.
- Verify runtime health, port collision handling, preview ownership, expiry and cleanup.
- Test actual sample app runtime; DCP UI Simulator or DCP dashboard smoke test alone is not proof.

## Terminal Studio
- Import command/script/JSON pack without executing it.
- Invalid schema, oversized file, path traversal and unsupported executable are rejected.
- Exact argv, working directory, environment profile and risk level are displayed before execution.
- Approval required for mutating or network-enabled tasks.
- Unauthorized user, cross-project job, CSRF failure, timeout and output-limit tests fail closed.
- Cancellation terminates child processes and confirms cleanup.

## UI testing and artifacts
- Playwright runs against actual preview URL.
- Verify navigation, form interaction, responsive viewport and browser console/network errors.
- Save screenshot, trace, report and logs with job/source provenance and SHA-256.
- Verify artifact access authorization, tamper detection and retention.

## Infrastructure safety
- Cloud Provisioning gate starts OFF after fresh install and restart.
- VM Creation gate starts OFF after fresh install and restart.
- Each gate is independently enforced by backend.
- Requests while OFF are rejected before provider adapter invocation.
- Dashboard never shows ON if backend state is unavailable.
- No CI or local test creates billable cloud resources or VMs.

## Release gate
No phase is accepted until required tests, security checks, documentation, evidence and rollback/cleanup behavior pass on the same commit.
