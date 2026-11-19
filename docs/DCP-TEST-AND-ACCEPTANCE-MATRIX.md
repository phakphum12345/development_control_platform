# DCP Test and Acceptance Matrix — 2026-11-19

**Main baseline:** `985a78d5fba459c8a0cbcf47e5d00a858c6e6228`  
**Evidence source:** GitHub workflow definitions, exact-head workflow run metadata and selected job logs.  
**Current audit state:** PARTIAL — workflow topology and PR #140/#149 outcomes inspected; no tests were executed locally by this audit.

## 1. Workflow-to-acceptance matrix

| Workflow | Trigger / runner | Main test scope | What it proves | What it does not prove |
|---|---|---|---|---|
| `validate-control-plane.yml` | PR/push main/manual; Ubuntu; optional self-hosted Windows matrix | Python unittest discovery, Dashboard JS syntax, Chromium real-app smoke, authenticated Preview Proxy Chromium/Firefox/WebKit, browser smoke, schema/registry validation, optional Windows Runner acceptance | Broad contract/regression and selected browser/API behavior on hosted runners | Real user's local machine, complete app compatibility, full WCAG/visual regression, Windows acceptance when optional job skipped |
| `local-first-emulator.yml` | PR/push main/manual; Ubuntu + Windows hosted | Local doctor, full Python unittest discovery, Gateway health/auth/safe defaults, Windows PowerShell parsing and Auth Proxy → Gateway login/logout/session flow | Local-first emulator and hosted Windows integration | Self-hosted user host, production OIDC, OS sandbox |
| `cross-platform-recovery.yml` | PR/push path-filter/manual; Ubuntu + Windows hosted | JobStore recovery, Runner API, pipeline interruption, hardlink containment, Auth Proxy, Flutter executor policy, Linux bubblewrap policy | Selected cross-platform recovery and policy tests | All failure modes, production sandbox acceptance on every supported host, macOS |
| `package-release.yml` | Dashboard/package PR, manual, release; Windows hosted | Inno Setup install, PWA/portable ZIP/installer build and upload | Packaging pipeline build | Clean-machine install/upgrade/rollback/uninstall and code-signing acceptance |
| `cloud-gateway-live-smoke.yml` | Manual only; explicit input defaults false; Ubuntu | GET-only live health/auth preflight | Read-only live endpoint behavior when explicitly enabled | Provisioning, VM creation, runner-online, live job or teardown |
| `macos-cloud-runner.yml` | Manual only; opt-in boolean defaults false plus repository variables and secrets | Provider request dispatch for allowlisted repository/commit/OS | Guarded request path when every gate is deliberately enabled | Actual macOS runner readiness/job/cleanup unless a separate live acceptance is captured |
| `deploy-pages.yml` | Main dashboard push/manual; Ubuntu | Static Dashboard Pages deployment | Pages artifact/deployment action | Authenticated local Gateway availability or production backend deployment |
| `static.yml` | Manual only | Informational notice | Duplicate Pages workflow is disabled | No product acceptance |

## 2. PR exact-head evidence observed

### PR #140 — head `8bf0b74859c3749070eafbd7906d9c7df6d0822b`

| Workflow / job | Result | Interpretation |
|---|---|---|
| Validate Control Plane / `validate` | PASS | Hosted test and validation job passed |
| Windows dynamic-port launcher integration | PASS | Hosted Windows integration passed |
| Optional Windows runner acceptance | SKIPPED | Not a target-host acceptance result |
| Windows PSEC API Availability Probe workflow | Workflow PASS; internal evidence BLOCKED | Probe JSON says `available=false`, `state=BLOCKED`; `processmodel.dll` unavailable from System32 search path |
| Package Development Control Platform | PASS | Windows package build completed |
| Cross-platform Recovery / Windows + Ubuntu | PASS | Both hosted matrix jobs passed |
| Local-first Minimal Emulator / Linux + Windows | PASS | Both hosted emulator jobs passed |

### PR #149 — head `44ec9f4b95601071b172a9b541387399591745b7`

| Workflow / job | Result | Interpretation |
|---|---|---|
| Validate Control Plane / `validate` | PASS | Hosted test and validation job passed |
| Windows dynamic-port launcher integration | PASS | Hosted Windows integration passed |
| Optional Windows runner acceptance | SKIPPED | Not target-host acceptance |
| Windows PSEC API Availability Probe workflow | Workflow PASS; internal evidence BLOCKED | Probe JSON says `available=false`, `state=BLOCKED`; `processmodel.dll` unavailable |
| Cross-platform Recovery / Windows + Ubuntu | PASS | Both hosted matrix jobs passed |
| Local-first Minimal Emulator / Linux + Windows | PASS | Both hosted emulator jobs passed |

**Important:** A workflow may be green because its probe classifies the hosted image as an expected BLOCKED environment and uploads evidence. The workflow conclusion is not proof that the PSEC capability passed.

## 3. Required host acceptance not yet satisfied

- Windows: PSEC API availability on a supported target, trusted base runtime and stdlib, real AppContainer/LPAC effective access, filesystem deny/enumeration behavior, network denial, process-tree containment, cleanup, scratch profile and no host-profile escape.
- Linux: integrated bubblewrap launcher, mount and namespace verification, seccomp network denial, process cleanup and adversarial host tests.
- macOS: signed helper, entitlements, filesystem/network boundary and actual-host acceptance.
- Windows installation: clean machine install, upgrade, rollback, interrupted install recovery and uninstall preservation.
- Cloud: only with explicit approval; runner create → online → controlled job → offline → deregistration → VM/NIC absence → orphan reconciliation and actual spend evidence.

## 4. Evidence record requirements

Every future acceptance record must include:
- Repository, branch, full commit SHA.
- Workflow URL, run ID, job ID and job conclusion.
- Host OS/build/architecture and runner identity.
- Exact command and environment contract (never secret values).
- Start/end timestamp and exit code.
- Artifact path/URL and SHA-256.
- Cleanup result.
- PASS/FAIL/BLOCKED/SKIPPED/UNKNOWN classification.
- Explicit scope limits.

## 5. Re-run policy

- Re-run required workflows after any source or workflow change.
- Verify the exact current PR head SHA, not a parent or prior run.
- Treat path-filtered workflows that did not trigger as UNKNOWN until manually or otherwise validly executed.
- Keep optional self-hosted jobs SKIPPED unless a registered supported host actually runs them.
- Never use unsandboxed browser fallback or relax security policy merely to make CI green.
