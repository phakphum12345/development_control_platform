# DCP Master Feature Backlog

Status labels describe the initial source review only; revalidate against the exact branch head and tests before implementation. EXISTING does not imply production-grade or complete.

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
| BUILD-02 | Generic web build adapters | MISSING | P0 | Start with static HTML/JS and Node/Vite stacks; no arbitrary shell command. |
| RUN-01 | Runtime Manager | MISSING | P0 | Start/stop supervised process trees with port isolation, timeout and logs. |
| RUN-02 | Real application preview | MISSING/PARTIAL | P0 | Preview actual runtime via owner-bound expiring proxy session. |
| TERM-01 | Terminal Studio UI | MISSING | P1 | Tabs, shell selection, working directory, output, exit code, stop and history. |
| TERM-02 | Import Command / Template Library | MISSING | P1 | Import text/JSON/script as inert data; never auto-execute; validate schema and provenance. |
| TERM-03 | Visual Command Builder | MISSING | P1 | Build typed command requests from approved task templates; show exact argv. |
| TERM-04 | Terminal execution broker | MISSING | P1 | Local Agent only; policy allowlist, approval, timeout, output limits, process-tree cancellation. |
| TERM-05 | Terminal API / audit | MISSING | P1 | Auth, CSRF, project scope, owner, command hash, outcome and redacted logs. |
| EDIT-01 | File Explorer / Code Editor | PARTIAL/VERIFY | P2 | Inspect existing Code Navigator; editor writes require diff and approval. |
| GIT-01 | Git visual history / diff / conflict tools | PARTIAL/VERIFY | P2 | Read-only first; mutating actions require confirmation. |
| FLOW-01 | Visual Workflow Builder | MISSING | P2 | Typed nodes, bounded graph, policy gates and resumable jobs. |
| TEST-01 | Playwright against actual preview | PARTIAL/VERIFY | P0 | Existing dashboard smoke tests are not proof of arbitrary project UI testing. |
| TEST-02 | Responsive / cross-browser / visual regression | MISSING/P1 | P1 | Evidence screenshots, browser versions and baseline diff. |
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
