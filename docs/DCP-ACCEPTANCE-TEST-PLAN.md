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

### Implemented static-project test slice
- `test_static_web` accepts only detected dependency-free Static HTML/CSS/JS projects.
- The pipeline builds static output, starts the DCP loopback RuntimeManager against generated output, and runs a DCP-owned Playwright suite. It does not run project test scripts/configuration or install dependencies.
- Verify page load/title/language, 360/768/1366 viewport overflow, basic image/button/link naming signals, console/page errors, failed requests and blocked external requests.
- Save three viewport screenshots and a JSON report in a bounded ZIP evidence artifact; upload through the Artifact Store.
- This path tests the actual generated static runtime, but it starts RuntimeManager directly. It does **not** prove Playwright access through the authenticated Preview Proxy.
- Trace capture, form/navigation interaction coverage, full WCAG conformance and visual baselines are not part of this implemented slice.

### Required PR #71 acceptance
- Run the real Chromium smoke test with `chromium_sandbox=True` on the exact PR head commit.
- Confirm that missing host sandbox support fails closed and produces actionable diagnostics; never use `--no-sandbox` as a workaround.
- Confirm the JSON report and ZIP evidence are generated and uploaded for normal test completion; failed test or upload must not become PASS.
- Run Dashboard browser smoke and registry/schema validation after the Chromium test succeeds.
- Bind all reported results to the exact full commit SHA and inspect every required CI check.

### Authenticated-preview browser acceptance — implemented
- `tests/test_local_auth_proxy.py::LocalAuthProxyEndToEndTests.test_real_chromium_loads_app_through_authenticated_preview_proxy` starts a completed static job, creates the preview through the owner-authenticated Local Auth Proxy API, and navigates Chromium to the returned same-origin preview URL.
- Chromium runs with `chromium_sandbox=True`; the test verifies HTML/title/content, relative CSS loading, computed style, same-origin requests, no console/page/request errors, screenshot capture, and HTTP 404 after preview stop.
- The API-level acceptance verifies unauthenticated denial, cross-job denial, query rejection, owner CSRF-protected stop, logout denial, and that runtime capability tokens/upstream ports are not exposed.
- The proxy implementation fixes upstream host/port to loopback, rejects path traversal, limits response size and allowed content types, and does not accept browser-selected upstream addresses.
- Remaining: cross-owner identity tests beyond the single local owner model, trace/log evidence, visual baselines, full WCAG/axe coverage and cross-browser engines.

## Infrastructure safety
- Cloud Provisioning gate starts OFF after fresh install and restart.
- VM Creation gate starts OFF after fresh install and restart.
- Each gate is independently enforced by backend.
- Requests while OFF are rejected before provider adapter invocation.
- Dashboard never shows ON if backend state is unavailable.
- No CI or local test creates billable cloud resources or VMs.

## Release gate
No phase is accepted until required tests, security checks, documentation, evidence and rollback/cleanup behavior pass on the same commit.
