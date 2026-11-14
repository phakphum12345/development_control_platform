# DCP Master Feature Backlog

Status labels describe the evidence-backed state recorded in the dated updates below. Revalidate against the exact branch head and tests before release. `IMPLEMENTED` means the documented slice exists; it does not imply production-grade or complete.

| ID | Capability | Initial status | Priority | Notes / acceptance direction |
|---|---|---|---|---|
| CORE-01 | Local Gateway + Auth Proxy | EXISTING | P0 | Preserve loopback-only behavior and owner data; auth integration tests pass. |
| CORE-02 | SQLite Job Control Plane | EXISTING/PARTIAL | P0 | Verify lifecycle, idempotency, lease recovery, cancellation and audit completeness. |
| CORE-03 | Per-job Workspace Manager | EXISTING/PARTIAL | P0 | Verify path safety, quotas, cleanup and cross-job isolation; not an OS sandbox. |
| CORE-04 | Runner Registry / heartbeat | EXISTING/PARTIAL | P0 | Verify enrollment, capability scheduling, drain and stale worker fencing. |
| CORE-05 | Backend-enforced Cloud Provisioning OFF | IMPLEMENTED (local backend gate) | P0 | Persistent gate defaults OFF, is independent from VM Creation, requires Owner confirmation + provider readiness to enable, and is covered by Gateway API tests. Live deployment must keep it OFF until provider/budget gates pass. |
| CORE-06 | Backend-enforced VM Creation OFF | IMPLEMENTED (local backend gate) | P0 | Separate persistent gate defaults OFF and is independently enforced/audited by Gateway; covered by persistence, authorization and readiness tests. Live VM creation remains blocked pending approved live acceptance. |
| IMP-01 | GitHub App repository/ref/SHA import | EXISTING/PARTIAL | P0 | Revalidate installation membership and immutable SHA at job acceptance. |
| IMP-02 | Local Folder import via Local Agent | PARTIAL (static end-to-end slice) | P0 | Dashboard catalog/selection, owner-only API, UUID + SHA-256-bound job creation, stale-source rejection, Runner snapshot checkout/materialization, static build/test pipeline and focused E2E tests exist. Remaining: real Windows-host acceptance, live Dashboard workflow evidence, artifact/download provenance and dependency-managed Local Folder targets. |
| IMP-03 | Framework/toolchain detection | PARTIAL | P0 | Existing bounded inventory now reports evidence-based framework, package manager, manifest constraints and scripts; installed toolchain readiness and job integration remain. |
| BUILD-01 | Flutter fixed-target executor | EXISTING/PARTIAL | P1 | Opt-in, trusted-repository allowlist, disabled by default; verify artifacts and cleanup. |
| BUILD-02 | Generic web build adapters | PARTIAL | P0 | Static HTML/JS, React/Vite, Vue/Vite, Next.js and Angular build targets implemented using preinstalled local CLIs; dependency installation, SSR runtime/preview and broader framework coverage remain. |
| RUN-01 | Runtime Manager | IMPLEMENTED (STATIC SLICE) | P0 | Loopback-only static runtime supervisor with ephemeral port, health check, bounded logs, expiring session capability and owned-process cleanup. Arbitrary project servers remain unsupported. |
| RUN-02 | Authenticated preview proxy | PARTIAL | P0 | Owner-authenticated static and Next.js loopback runtime support now exists for completed trusted jobs; explicit Owner approval is required for Next.js code execution. Dashboard workflow coverage, broader server types, HMR/WebSocket and network isolation remain outstanding. |
| TERM-01 | Terminal Studio UI | PARTIAL | P1 | Dashboard includes catalog/preview, typed parameter forms, Project Workspace selection, app authorization, separate confirmation, idempotent queue submission, Job history/status/log polling and cancellation. Built-in execution remains disabled by catalog policy; interactive PTY is not included. |
| TERM-02 | Import Command / Template Library | PARTIAL | P1 | Strict v1 JSON command packs persist as inert SQLite templates with source SHA-256 and audit; imported items remain disabled pending review. Clipboard/text and script-file import are not implemented. |
| TERM-03 | Visual Command Builder | PARTIAL | P1 | Typed parameter forms are generated from the trusted template schema and exact argv preview is available. Project/framework/task/environment/mode composition and broader workflow authoring remain outstanding. |
| TERM-04 | Terminal execution broker | BLOCKED | P1 | PR #112 merged the owner-only authorization/grant API, typed durable Job submission, Runner lease-bound grant consumption, fixed-template Local Runner broker, bounded/redacted logs and cancellation path. Every built-in template remains execution_enabled=false, so no process can currently start. Do not enable until a verified OS-isolation strategy, Git helper/config hardening, adversarial tests, process-tree cleanup verification and supported-host acceptance pass. Workspace binding is not an OS sandbox. |
| TERM-05 | Terminal API / audit | PARTIAL | P1 | Owner-only catalog/preview/import/review and source-hash audit coexist with project/workspace-bound grants, idempotent typed Jobs, Runner lease verification, shared Job status/log/cancel APIs and output redaction. Live host execution evidence and independent cleanup verification remain UNKNOWN; template execution is fail-closed. |
| EDIT-01 | File Explorer / Code Editor | PARTIAL/VERIFY | P2 | Inspect existing Code Navigator; editor writes require diff and approval. |
| GIT-01 | Git visual history / diff / conflict tools | PARTIAL/VERIFY | P2 | Read-only first; mutating actions require confirmation. |
| FLOW-01 | Visual Workflow Builder | MISSING | P2 | Typed nodes, bounded graph, policy gates and resumable jobs. |
| TEST-01 | Real static-project Playwright testing | IMPLEMENTED (STATIC SLICE) | P0 | Opt-in `test_static_web` builds supported static output, starts loopback runtime, runs real Chromium checks and uploads screenshots/report evidence. CI uses a path-scoped AppArmor user-namespace allowance, not `--no-sandbox`. Authenticated Preview Proxy API E2E is covered separately; full app-framework testing remains out of scope. |
| TEST-02 | Responsive / cross-browser / visual regression | PARTIAL | P1 | Authenticated Preview Proxy fixture acceptance passed Chromium, Firefox and WebKit in PR #96 CI. Static-project viewport screenshots exist. Full imported-app compatibility, visual baselines, keyboard interactions and WCAG/axe remain outstanding. |
| TEST-03 | API / accessibility / performance testing | PARTIAL/MISSING | P1 | Isolated test targets and bounded traffic only. |
| SEC-01 | Secrets / dependency / license / SBOM scan | PARTIAL/MISSING | P1 | Never expose secret values; attach machine-readable findings. |
| ART-01 | Job artifacts and SHA-256 | EXISTING/PARTIAL | P1 | Verify upload/download authorization, provenance, retention and integrity. |
| DATA-01 | Test Database & Environment Studio | MISSING | P2 | Isolated test data only; production access denied by default. |
| OPS-01 | Diagnostics / resource monitoring | PARTIAL | P1 | Read-only doctor first; CPU/RAM/disk/process metrics. |
| OPS-02 | Backup / recovery / disaster recovery | PARTIAL/MISSING | P1 | Restore preview and integrity checks; preserve existing local data. |
| OPS-03 | DCP self-test / safe upgrade | PARTIAL/MISSING | P2 | Upgrade rehearsal and recovery point before applying. |
| COL-01 | Roles, collaboration, bug and release management | PARTIAL/MISSING | P3 | Add only when multi-user/product scope is justified. |
| EXT-01 | Plugin / adapter system | MISSING | P3 | Signed/provenance-aware, permission-scoped, compatibility checked. |
| AI-01 | AI Analyze/Propose/Apply/Verify | PARTIAL/MISSING | P3 | Apply only after user approval; diff, audit and tests mandatory. |
| INF-01 | Multi-runner / optional provider activation | PARTIAL/BLOCKED | P3 | Local-first scale-out first; cloud/VM stays OFF and blocked. |

## Priority
- P0: safety and MVP workflow blockers.
- P1: first useful product completion.
- P2: advanced development productivity and operations.
- P3: collaboration, extensibility and optional intelligence.

## Definition of Done
A feature is complete only when implementation, unit/integration tests, security tests, UI tests where applicable, documentation, failure behavior and evidence are present on the same commit. A UI-only control is not completion of a backend capability.


## 2026-11-11 implementation status update
- IMP-02 advanced from MISSING to PARTIAL: explicit root enrollment, local project IDs, bounded SHA-256 fingerprints, symlink/path containment checks, CLI registration and owner-only read APIs are implemented on feature branches and covered by focused tests. The full Dashboard import workflow and immutable per-job snapshot are not yet implemented.

- Dashboard Project Import view now reads GitHub App repositories/refs/verified commits and enrolled Local Projects. This remains PARTIAL until selected sources can be materialized into immutable job snapshots and bound to build/test jobs.

- Local Folder snapshot materialization now verifies the registered SHA-256 before/after copy, rejects symlinks and destination overwrites, and produces a bounded read-only-permissions copy. Durable job payload binding and Local Runner execution integration remain outstanding.


## 2026-11-11 project intelligence progress
- Added manifest-backed framework detection to the existing Project Intelligence inventory.
- Detection is read-only and does not imply toolchain readiness or build support.


## Universal Build Engine progress
- Static web and Vite targets are now wired through existing Job Control Plane, Runner Scheduler, Local Runner Pipeline and Artifact Store.
- Dependency installation is intentionally not automated; Vite must already exist in the workspace. Unknown frameworks remain unsupported.


## Runtime Manager progress
- Initial static runtime supervisor implemented for built output only; no arbitrary project server scripts are started.
- Preview session tokens are local capability tokens and must be wrapped by authenticated Gateway owner authorization before Dashboard exposure.


## 2026-11-12 evidence-based status — PR #71 head

Review branch: `feature/real-project-playwright-testing`  
Reviewed source baseline before diagnostics update: `52a99f2403c7ffc5c8d82fe44cbb477f8189b325`.  
A follow-up commit adds bounded Chromium launch diagnostics; its CI result must be checked separately.

- `BUILD-02`: static HTML/CSS/JS and React/Vite + Vue/Vite build adapters are implemented on the merged Universal Web Build Engine slice. Dependency installation remains explicit and is not performed by DCP.
- `RUN-01`: static loopback runtime supervision is implemented. It is not a general project-server runtime.
- `RUN-02`: authenticated static Preview Proxy primitives exist, but the PR #71 Playwright path starts RuntimeManager directly and does not exercise that proxy.
- `TEST-01`: DCP-owned `test_static_web` implementation and tests exist. The latest observed CI run `43047243795` passed the Python contract suite (508 tests) and browser installation, then failed when sandboxed Chromium launched. Dashboard browser smoke and registry validation were skipped after that failure. Windows dynamic-port and Windows Auth Proxy/Gateway checks passed; self-hosted Windows Runner acceptance was skipped.
- The above CI result belongs to commit `52a99f2403c7ffc5c8d82fe44cbb477f8189b325`; it is not evidence for later commits.
- `TEST-02` remains partial: viewport screenshots are not visual regression, cross-browser, keyboard, or full WCAG evidence.

No status in this table proves that the user's local Windows Runner, local services, or deployed environment are currently online.

## 2026-11-12 verified implementation status — PRs #81–#88

- TERM-01: PARTIAL — Dashboard Terminal Studio now has catalog, argv preview, JSON import and Owner review/audit UI. It is not an interactive shell or terminal session.
- TERM-02: PARTIAL — strict v1 JSON command packs are persisted as inert data. Imported templates are disabled and pending Owner review; script/clipboard import is not implemented.
- TERM-03: MISSING — no visual command builder yet.
- TERM-04: BLOCKED — no Terminal execution endpoint or Local Agent execution broker is enabled. WorkspaceManager is not an OS sandbox; do not execute untrusted project code until isolation, explicit job approval and cleanup are verified.
- TERM-05: PARTIAL — authenticated catalog/preview/import/review and audit APIs exist; project-scoped execution jobs, redacted output and cancellation are missing.
- TEST-01: IMPLEMENTED (STATIC SLICE) — the supported static project test path passes real Chromium CI with the scoped AppArmor allowance. This does not imply arbitrary framework or browser-test coverage.
- RUN-02: PARTIAL — authenticated Preview Proxy lifecycle is covered by real API E2E for completed static jobs. General server/HMR/WebSocket preview remains unsupported.
- PR #81: read-only Terminal catalog and exact argv preview API.
- PR #82: Dashboard Terminal Studio catalog/preview integration.
- PR #83: strict inert JSON command-pack import, private SQLite persistence and audit.
- PR #84: Dashboard JSON command-pack import.
- PR #86: source-hash-bound Owner approve/reject review lifecycle.
- PR #88: Dashboard Owner review and audit-history controls.

All above status statements refer to merged code on main and the corresponding CI checks; they do not imply Terminal command execution is available.


## 2026-11-12 implementation checkpoint — Next.js and Angular build targets

- Added Local Runner build targets for Next.js and Angular using preinstalled local CLIs and fixed argv; DCP does not install dependencies or invoke package-manager lifecycle scripts.
- Next.js output is packaged from `.next/`; Angular output is forced to `dist/` and packaged.
- Angular project selection requires one application build target or an explicit valid default project; ambiguous projects fail closed.
- Job queue validation, runner capability scheduling and Dashboard build-target selection include both frameworks.
- These targets execute trusted project build/configuration code and remain behind existing Runner execution opt-in and trusted-source allowlists. Next.js SSR runtime/preview is not included.


## 2026-11-12 implementation checkpoint — Next.js loopback preview runtime

- Added a fixed local Next.js production-server launch path for completed build_next jobs.
- Starting Next.js requires an authenticated Owner request with confirm_code_execution=true; the Gateway rejects other roles, other job targets and missing confirmation.
- Next.js is bound to 127.0.0.1, uses a fixed local CLI argv with shell=False, receives a reduced environment, has bounded logs/TTL, and is stopped through process-tree supervision.
- Runtime session capabilities remain server-side behind the authenticated same-origin Preview Proxy.
- Angular static preview accepts the generated dist/browser output.
- This is trusted-code execution, not an OS sandbox. Outbound network access by the application is not blocked; only trusted repositories/local projects should be built and previewed. The Owner must explicitly approve starting the Next server.


## 2026-11-12 cross-browser Preview Proxy acceptance checkpoint

- Added one shared authenticated Preview Proxy browser scenario with Chromium, Firefox and WebKit launch selection.
- The scenario uses a synthetic static fixture and the real Local Auth Proxy → Gateway → Preview Proxy path; it verifies session cookie scope, HTML/CSS, same-origin resource loading, browser errors, screenshot capture, and access denial after stop.
- Chromium sandboxing remains enabled. Firefox/WebKit are separate browser-engine checks and do not claim OS-level isolation.
- CI installs Firefox/WebKit explicitly and runs each test separately. This was the pre-PR #96 status; PR #96 subsequently passed the exact-head Chromium, Firefox and WebKit checks before merge to `main`.
- This is not full cross-browser application certification, visual regression, keyboard accessibility, or WCAG/axe coverage.


## 2026-11-12 verified `main` update — import and preview

- IMP-02 is beyond a read-only catalog: the Dashboard can select a registered Local Folder project and submit a job bound to its project UUID and current SHA-256; the Gateway refreshes/rejects stale fingerprints; the Local Runner materializes the approved snapshot before supported static build/test execution. See `docs/DCP-LOCAL-FOLDER-BUILD.md` and focused Gateway/snapshot/pipeline tests.
- This remains a partial product capability: Local Folder execution is limited to supported static HTML/CSS/JS targets, and a real Windows-host acceptance run plus end-to-end Dashboard artifact/download evidence are still required.
- TEST-02 authenticated Preview Proxy fixture coverage passed Chromium, Firefox and WebKit on PR #96 before merge. This is not a claim of full application browser certification or visual/WCAG completion.


## 2026-11-14 source-backed checkpoint — WP-00 inventory and PR #115 reconciliation

- Verified `main` baseline for this checkpoint: `62d72bddd028399d0b96cd9c2f6e3b16a704b758`, the merge commit for PR #115.
- PR #115 closed the WP-18 fail-closed contract slice. It did not add a Linux/Windows/macOS production sandbox launcher.
- Earlier WP-17 text in this roadmap that describes PR #114 as OPEN is historical/stale. PR #114 is merged as `ef3bf7e3522119ebbd3a41de693cee254e1ea7cf`.
- A source-driven remaining-work register and first-pass status/requirements docs are being added on PR #116. See `docs/DCP-REMAINING-WORK-INVENTORY.md`, `docs/IMPLEMENTATION-STATUS.md`, `docs/REQUIREMENTS-TRACEABILITY.md` and `docs/INDEX.md`.
- The baseline inventory found 289 recursive tree entries (265 files), 78 tool files, 86 test files, 58 docs and 7 workflows. Dashboard view inventory contains 21 views. These counts are tied to the exact baseline SHA.
- Current register contains 22 Work Packages as a grouping only; atomic task count is not final until per-file, API, Dashboard-handler and test-function traceability is completed.
- WP-18A now has a Linux-only bubblewrap command builder and seccomp network-deny policy on PR #116. The builder is not yet integrated into TerminalScriptExecutor. No real host acceptance is claimed.
- Windows AppContainer/LPAC remains BLOCKED; macOS remains BLOCKED. All seven built-in Terminal templates remain disabled.
- User-host Windows acceptance, independent process cleanup, workspace cleanup after interruption, complete browser visual/accessibility evidence and full operations/upgrade/rollback acceptance remain open.
