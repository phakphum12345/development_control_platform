# DCP Master Feature Backlog

Status labels describe the evidence-backed state recorded in the dated updates below. Revalidate against the exact branch head and tests before release. `IMPLEMENTED` means the documented slice exists; it does not imply production-grade or complete.

| ID | Capability | Initial status | Priority | Notes / acceptance direction |
|---|---|---|---|---|
| CORE-01 | Local Gateway + Auth Proxy | EXISTING | P0 | Preserve loopback-only behavior and owner data; auth integration tests pass. |
| CORE-02 | SQLite Job Control Plane | EXISTING/PARTIAL | P0 | Verify lifecycle, idempotency, lease recovery, cancellation and audit completeness. |
| CORE-03 | Per-job Workspace Manager | EXISTING/PARTIAL | P0 | Verify path safety, quotas, cleanup and cross-job isolation; not an OS sandbox. |
| CORE-04 | Runner Registry / heartbeat | EXISTING/PARTIAL | P0 | Verify enrollment, capability scheduling, drain and stale worker fencing. |
| CORE-05 | Backend-enforced Cloud Provisioning OFF | PARTIAL/VERIFY | P0 | Inspect all API/provider paths; reject create requests server-side and persist OFF. |
| CORE-06 | Backend-enforced VM Creation OFF | PARTIAL/VERIFY | P0 | Separate gate from Cloud Provisioning; tests prove no provider create call. |
| IMP-01 | GitHub App repository/ref/SHA import | EXISTING/PARTIAL | P0 | Revalidate installation membership and immutable SHA at job acceptance. |
| IMP-02 | Local Folder import via Local Agent | PARTIAL | P0 | Local registry, explicit CLI enrollment, owner-only read APIs, Dashboard source selection and verified snapshot materialization exist; durable job binding and runner integration remain. |
| IMP-03 | Framework/toolchain detection | PARTIAL | P0 | Existing bounded inventory now reports evidence-based framework, package manager, manifest constraints and scripts; installed toolchain readiness and job integration remain. |
| BUILD-01 | Flutter fixed-target executor | EXISTING/PARTIAL | P1 | Opt-in, trusted-repository allowlist, disabled by default; verify artifacts and cleanup. |
| BUILD-02 | Generic web build adapters | PARTIAL | P0 | Static HTML/JS, React/Vite, Vue/Vite, Next.js and Angular build targets implemented using preinstalled local CLIs; dependency installation, SSR runtime/preview and broader framework coverage remain. |
| RUN-01 | Runtime Manager | IMPLEMENTED (STATIC SLICE) | P0 | Loopback-only static runtime supervisor with ephemeral port, health check, bounded logs, expiring session capability and owned-process cleanup. Arbitrary project servers remain unsupported. |
| RUN-02 | Authenticated preview proxy | PARTIAL | P0 | Owner-authenticated static and Next.js loopback runtime support now exists for completed trusted jobs; explicit Owner approval is required for Next.js code execution. Dashboard workflow coverage, broader server types, HMR/WebSocket and network isolation remain outstanding. |
| TERM-01 | Terminal Studio UI | PARTIAL | P1 | Dashboard Command Library, exact argv preview, JSON import and Owner review/audit controls exist. Interactive terminal sessions, streamed process output, stop and job history remain missing. |
| TERM-02 | Import Command / Template Library | PARTIAL | P1 | Strict v1 JSON command packs persist as inert SQLite templates with source SHA-256 and audit; imported items remain disabled pending review. Clipboard/text and script-file import are not implemented. |
| TERM-03 | Visual Command Builder | MISSING | P1 | A curated catalog and argv preview exist, but a visual typed builder and parameterized task forms are not implemented. |
| TERM-04 | Terminal execution broker | BLOCKED | P1 | No Terminal command execution API or Local Agent broker is enabled. Imported templates remain disabled even after Owner review. Execution requires a verified OS isolation strategy, per-job approval, time/output limits and verified process-tree cancellation. WorkspaceManager alone is not an OS sandbox. |
| TERM-05 | Terminal API / audit | PARTIAL | P1 | Authenticated catalog/preview, Owner-only import/review, source-hash binding and template audit history exist. Project-scoped execution jobs, outcome logs, secret redaction and cancellation evidence remain missing. |
| EDIT-01 | File Explorer / Code Editor | PARTIAL/VERIFY | P2 | Inspect existing Code Navigator; editor writes require diff and approval. |
| GIT-01 | Git visual history / diff / conflict tools | PARTIAL/VERIFY | P2 | Read-only first; mutating actions require confirmation. |
| FLOW-01 | Visual Workflow Builder | MISSING | P2 | Typed nodes, bounded graph, policy gates and resumable jobs. |
| TEST-01 | Real static-project Playwright testing | IMPLEMENTED (STATIC SLICE) | P0 | Opt-in `test_static_web` builds supported static output, starts loopback runtime, runs real Chromium checks and uploads screenshots/report evidence. CI uses a path-scoped AppArmor user-namespace allowance, not `--no-sandbox`. Authenticated Preview Proxy API E2E is covered separately; full app-framework testing remains out of scope. |
| TEST-02 | Responsive / cross-browser / visual regression | PARTIAL | P1 | Three viewport checks and screenshots exist in the static Playwright slice; cross-browser engines, visual baselines and interaction coverage remain missing. |
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
