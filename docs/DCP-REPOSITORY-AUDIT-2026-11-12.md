# DCP Repository Audit — 2026-11-12

## Scope and reviewed revision

Repository: `phakphum12345/development_control_platform`  
Branch: `feature/real-project-playwright-testing`  
Reviewed branch snapshot: `a8a56184703f70b4c428b93759f3a034c2a06dbb`  
Pull request: [#71](https://github.com/phakphum12345/development_control_platform/pull/71) (Draft, not merged)  
Base branch snapshot recorded by PR: `883c2b8c073a711133209d26f5e95c572a5494ec`

This is a source, test, workflow and documentation audit of the stated Git revision. It does not inspect or certify the user's local Windows machine, running processes, local databases, credentials, backups, registered self-hosted runners, or any deployed service. CI results below are tied to their own exact head SHA and must not be transferred to this reviewed revision.

## Executive result

The earlier 2026-11-11 audit is retained as a historical snapshot and is no longer an accurate status description for the newer implementation. Since then, the repository has gained:
- Universal static and Vite web build adapters.
- A loopback-only static Runtime Manager.
- Authenticated static Preview Proxy primitives.
- Local Folder snapshot materialization and job-related workflow increments.
- An opt-in DCP-owned Playwright smoke-test target for dependency-free static web projects.

PR #71 remains **BLOCKED for release** because its latest previously observed real-Chromium CI run failed during sandboxed browser launch. The code path intentionally does not fall back to an unsandboxed browser. A later commit exposes bounded launch diagnostics; CI must rerun on the exact current head before this blocker can be reclassified.

## Capability matrix

| Capability | Status | Evidence and boundary |
|---|---|---|
| Local-first Gateway and owner Auth Proxy | IMPLEMENTED (existing slice) | Gateway and local auth proxy source plus Windows Auth Proxy/Gateway integration check. Does not prove the user's local stack is running. |
| SQLite Job Control Plane | IMPLEMENTED / PARTIAL | Durable queue, lifecycle, lease and artifact endpoints exist; broader lifecycle and operational acceptance remains. |
| Runner registry and capability scheduler | IMPLEMENTED / PARTIAL | Authenticated registry and capability-based scheduling exist; self-hosted Windows Runner acceptance was skipped in the observed run. |
| GitHub source inspection | IMPLEMENTED / PARTIAL | Owner-authenticated GitHub App repository/ref/commit inspection exists; full immutable job-source binding remains an acceptance boundary. |
| Local Folder enrollment and snapshot materialization | IMPLEMENTED / PARTIAL | Explicit enrolled roots, project fingerprints, path/symlink checks, owner-only read APIs and verified snapshot materialization exist. Durable end-to-end project-to-job provenance still requires validation. |
| Framework detection | IMPLEMENTED / PARTIAL | Read-only manifest-backed detection covers a defined framework set; toolchain readiness is not inferred and unknown evidence remains unsupported. |
| Flutter fixed-target execution | IMPLEMENTED (constrained) | Fixed command allowlist, explicit execution opt-in and trusted repository policy; not an OS sandbox. |
| Static HTML/CSS/JS build | IMPLEMENTED | Bounded copy/build path with artifact handling; no source execution required for static copy. |
| React/Vite and Vue/Vite build | IMPLEMENTED (constrained) | Uses an already-present local Vite CLI; no automatic package installation or npm lifecycle execution. Build/config/application code remains executable and requires trust/opt-in. |
| Static Runtime Manager | IMPLEMENTED (static slice) | Loopback-only static server, health check, bounded logs, expiring capability and owned process cleanup. Not a general project-server runtime. |
| Authenticated static Preview Proxy | IMPLEMENTED (service slice) / PARTIAL (workflow) | Owner/job/session-bound static preview primitives exist. Full Dashboard workflow and Playwright-through-proxy acceptance are not established by PR #71. |
| Real static-project Playwright | PARTIAL / BLOCKED | DCP-owned fixed suite, viewport screenshots, JSON report and bounded ZIP artifact exist. Current CI evidence shows sandboxed Chromium launch failure on a prior head SHA. |
| Authenticated Preview Proxy browser E2E | MISSING | PR #71 launches RuntimeManager directly; it does not test through the authenticated Preview Proxy URL. |
| Cross-browser, visual regression and full accessibility | MISSING / PARTIAL | Three viewport screenshots and a small accessible-name smoke subset exist; no cross-browser matrix, baseline comparison, keyboard suite or WCAG conformance claim. |
| Artifact Store and SHA-256 metadata | IMPLEMENTED / PARTIAL | Authenticated upload/download and integrity metadata exist; provenance and retention acceptance should continue to be expanded. |
| Terminal Studio / arbitrary shell | MISSING | Do not infer general shell capability from fixed Runner adapters. |
| Cloud Provisioning, VM Creation and Cloud Deployment | OFF / FAIL-CLOSED POLICY | Keep independently disabled; no provider activation or automatic fallback is authorized by this audit. |

## PR #71 CI evidence

Observed run: [Actions run 43047243795](https://github.com/phakphum12345/development_control_platform/actions/runs/43047243795)  
Tested head: `52a99f2403c7ffc5c8d82fe44cbb477f8189b325`

| Check | Result | Interpretation |
|---|---|---|
| Python contract and integration suite | PASS | 508 tests passed before browser smoke. |
| Python/Node Playwright installation | PASS | Package installation succeeded. |
| Chromium download | PASS | Browser download succeeded; this does not prove sandbox launch support. |
| Real static-app Chromium smoke | FAIL | Chromium could not start with sandbox enabled. |
| Dashboard browser smoke | SKIPPED | Workflow stopped after the failed application-browser test. |
| Registry/schema validation | SKIPPED | Workflow stopped before this step. |
| Windows dynamic-port launcher integration | PASS | Windows command/launcher integration passed. |
| Windows Auth Proxy + Gateway E2E | PASS | This integration check passed. |
| Self-hosted Windows Runner acceptance | SKIPPED | No acceptance result for a registered local Runner. |
| Linux minimal emulator / safe defaults | PASS | The separate Linux Gateway safe-defaults check passed; it is not Chromium sandbox evidence. |

A follow-up code change adds a bounded diagnostic containing the launch exception class and short message. Its commit and any later documentation commits require a fresh CI run. The failure cause is not considered diagnosed until the underlying Chromium launch message is observed.

## Security and architecture boundaries

1. Browser request routing, WebSocket blocking, WebRTC API denial and service-worker blocking are browser-level defense-in-depth. They are not an OS sandbox, host firewall or network namespace.
2. Workspace directory isolation is not OS process isolation.
3. Imported project code is untrusted. Do not run arbitrary project servers, test scripts, package scripts or dependencies without explicit trust and a suitable host isolation boundary.
4. Keep Chromium sandboxing enabled. Do not use `--no-sandbox` or a silent unsandboxed retry to make CI green.
5. The current Playwright suite tests generated static output through RuntimeManager directly. It does not establish authenticated Preview Proxy E2E.
6. A test PASS is limited to checks implemented in that suite. It is not WCAG, cross-browser, security or production-readiness certification.
7. Cloud Provisioning, VM Creation and Cloud Deployment remain independently OFF. No cloud/VM fallback is permitted.

## Documentation reconciliation completed in this branch

- Master Feature Backlog now distinguishes implemented static Runtime Manager and Preview Proxy primitives from incomplete workflow/E2E coverage.
- Implementation Roadmap now reflects the current build/runtime/preview/testing slices and exact-commit release gate.
- Playwright Testing guide now includes explicit Runner prerequisites, setup commands, failure classification and sandbox troubleshooting.
- Acceptance Test Plan separates direct RuntimeManager testing from deferred authenticated Preview Proxy browser E2E.
- Architecture document labels implemented slices separately from target integration.
- README separates Node-based Dashboard browser smoke from Python Playwright application testing.
- Local Job Control Plane and Runner Scheduler docs include current web build and Playwright targets.

## Required next actions

1. Inspect the exact Chromium launch diagnostic from a fresh CI run on the latest PR head.
2. Configure or select a CI Runner/container that demonstrably supports Chromium sandboxing; verify the sandbox is active rather than weakening it.
3. Rerun the real static-app test, Dashboard browser smoke, registry/schema validation and all required checks on one exact head SHA.
4. Add an authenticated Preview Proxy E2E test covering owner/job/session authorization, expiry, path safety and token non-disclosure.
5. Reconcile any newly discovered source/docs mismatches and keep PR #71 Draft until all required gates pass.
6. Only after all required checks pass may PR #71 be made Ready and merged under the user's prior conditional approval.

## Non-destructive operating rules

- Work only in feature branches; never edit `main` directly.
- Do not run destructive resets, broad cleanup, or remove/overwrite user backups or local data.
- Do not auto-install dependencies or execute imported source during intake.
- Do not enable Cloud Provisioning, VM Creation or Cloud Deployment.
- Do not report PASS without reproducible evidence tied to the exact commit.
