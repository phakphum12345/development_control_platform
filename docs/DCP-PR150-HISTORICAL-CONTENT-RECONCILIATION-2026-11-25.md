# PR #150 Historical Audit Content Reconciliation — 2026-11-25

**Repository:** `phakphum12345/development_control_platform`  
**Compared PR:** [#150](https://github.com/phakphum12345/development_control_platform/pull/150)  
**PR #150 head observed:** `02522a07dff1a06cb854f4809150330e4368f5e7`  
**Current main baseline observed:** `57589873583c706d4af9756709596fdba7c22de9`  
**Reconciliation branch:** `docs/wp00-atomic-acceptance-map-20261125`  
**State:** PARTIAL — historical content inspected; this is not a merge or a closure of PR #150.

## 1. Decision

Do not merge PR #150 wholesale. It is a historical audit branch containing useful architecture and acceptance analysis mixed with stale inventory counts, old PR/branch status, old source assumptions, and continuity edits that predate later mainline changes.

Keep the PR open pending a controlled extraction/reconciliation decision. Preserve its historical baseline statements as historical evidence. Do not overwrite current-main audit documents with the PR's older snapshot.

## 2. Changed-file inventory and disposition

| PR #150 file | Content value | Reconciliation disposition |
|---|---|---|
| `README.md` | Documents the evolved Dashboard-to-Gateway Document Workflow, Owner-scoped grants, immutable proposals, exact-content approval and server read-back; also describes PR Review as read-only | Compare against current source and current README before carrying forward. Do not assume the statement is true solely because it is in the PR. |
| `checkpoints/DCP-CEEP-CONTINUITY.md` | Large historical execution log with WP-18A–E and other work evidence | Preserve as historical chronology. Do not replace current continuity. Extract only still-relevant facts with exact SHA and refreshed evidence. |
| `docs/DCP-ARCHITECTURE-AND-DEPENDENCY-MAP.md` | Useful component boundaries, data flows, security boundaries, and architecture rules | Retain as an architecture reference after updating source paths, ownership and current status against main. Avoid duplicate queues/registries/executors unless an approved ADR exists. |
| `docs/DCP-IMPLEMENTATION-STATUS.md` | Capability-by-capability status and limitations | Historical snapshot only: it names main SHA `985a78d5fba459c8a0cbcf47e5d00a858c6e6228` (2026-11-19). Current main status is in newer dated audit docs; do not copy stale rows verbatim. |
| `docs/DCP-REMAINING-WORK-INVENTORY.md` | Detailed WP register and safety gates | Its 2026-11-19 / 2026-11-23 records are superseded by later mainline dated records. Preserve historical entries; reconcile only durable acceptance requirements. |
| `docs/DCP-REPOSITORY-INVENTORY.md` | Extensive path-level inventory, workflows, PR register and source boundaries | Useful historical inventory; counts (283 files, 81 tools, 91 tests, 63 docs, 8 workflows) and PR register are not current. Refresh from exact main before reusing any counts or state. |
| `docs/DCP-REQUIREMENTS-TRACEABILITY.md` | Requirement-family to source/test/workflow crosswalk | Useful starting map; historical WS labels and file-level anchors require current source validation and atomic test-function/handler tracing. |
| `docs/DCP-TEST-AND-ACCEPTANCE-MATRIX.md` | Explains what workflows prove and do not prove; distinguishes green workflow from blocked probe evidence and skipped host acceptance | Strong reusable acceptance principles. Workflow names/jobs and exact PR SHA evidence must be refreshed against current workflow definitions and runs. |
| `docs/INDEX.md` | Indexes the historical audit set | Current main already has an index; retain links to current dated docs and add only documents that remain authoritative. |
| `docs/document-generator-operations.md` | Describes the local writer, authenticated Dashboard/Gateway integration and its limits | The PR changes the status from feature-branch implementation to mainline presence. Verify every claimed API, grant, approval and read-back path against current source and tests before accepting. |

## 3. Historical facts that must not be presented as current

PR #150's baseline is `985a78d5fba459c8a0cbcf47e5d00a858c6e6228` from 2026-11-19. Its inventory values and branch/PR state are historical. The later mainline audit records a different baseline and larger tree. The 2026-11-25 audit records:

- Current main SHA: `57589873583c706d4af9756709596fdba7c22de9`.
- Recursive tree: 371 entries, 343 blobs/files, 28 tree entries; response not truncated.
- 212 Python files across the repository (path count, not a collected test count).
- 101 files under `tools/`.
- 116 paths under `tests/` (112 Python, 3 PowerShell, 1 JavaScript; path count only).
- 73 files under `docs/`.
- 9 workflow files.
- Main required CI on that exact SHA was observed PASS for Validate, Linux Minimal Emulator, Windows dynamic-port launcher integration and Windows 11 local Auth Proxy + Gateway E2E.
- Current open PRs and their heads must be fetched live before any action; PR status in PR #150 is not authoritative for today.

The current-main dated audit and remaining-work inventory remain the source of current status. This reconciliation does not rewrite those historical documents.

## 4. Reusable architecture and acceptance rules to preserve

1. Dashboard is not an authorization boundary. Every operation must be authorized by the server.
2. Local Auth Proxy owns the browser session boundary; do not trust browser-supplied roles or raw identity headers.
3. Gateway and durable Job Control Plane own job state, leases, checkpoints, idempotency and recovery invariants.
4. Runner enrollment and worker credentials are distinct from human identity/session credentials.
5. Repository import and Local Folder registration are not permission to execute imported content.
6. Terminal execution remains fail-closed until platform-specific OS isolation and target-host adversarial acceptance pass.
7. Provider readiness, Owner approval, budget authorization, provisioning and cleanup remain separate gates. Mock tests are not live provider acceptance.
8. Artifact SHA-256 integrity tests do not alone prove end-to-end Dashboard/source/commit provenance.
9. A green workflow may merely report an expected BLOCKED probe; inspect the uploaded evidence and job conclusion separately.
10. SKIPPED target-host acceptance is not PASS.
11. Document writes must be scope-bound, exact-content approved, idempotent, journaled and read-back verified; a local file write is not a GitHub commit/push.
12. Keep historical baselines append-only and bind every status claim to an exact SHA.

## 5. Remaining reconciliation actions

- [ ] Compare every architecture component path against current main and update only genuinely stale names.
- [ ] Rebuild the requirements crosswalk from current source, exact API routes, schema and exact test functions.
- [ ] Re-evaluate every workflow row from current YAML job IDs, triggers, required-check configuration and exact-head runs.
- [ ] Verify Document Workflow routes, authorization middleware, immutable proposal storage, exact-content approval and read-back tests in current main.
- [ ] Extract any unique, still-valid acceptance criteria into the current WP register without duplicating existing requirements.
- [ ] Add links from the current documentation index only after the target documents are reconciled.
- [ ] Re-run Markdown/link validation and exact-head required CI for each extraction PR.

## 6. Explicit non-actions

This record does not merge PR #150, close PR #150, cherry-pick its commits, deploy code, change runtime behavior, enable Terminal, provision cloud resources, alter production configuration, or claim any package complete.

## 7. Audit conclusion

PR #150 contains reusable historical architecture and test-acceptance analysis, but it is not safe to merge wholesale because its baseline and some status statements are stale. Its unique material should be extracted selectively after current-source verification. WP-00D remains IN_PROGRESS until those comparisons and the full source/test/workflow crosswalk are complete.
