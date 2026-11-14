# Windows PSEC Filesystem Authorization — WP-18B.1

**Workstream:** WP-18B.1  
**Parent:** PR #120 — Windows PSEC isolation capability probe  
**Implementation branch:** `work/wp18b1-windows-psec-filesystem-authorization`  
**Baseline:** `f6dc28219658d1fb14e31324f25053ab77aed81a`  
**Status:** PROJECTION PRIMITIVES IMPLEMENTED / WINDOWS AUTHORIZATION AND LAUNCH INTEGRATION BLOCKED

## 1. Problem statement

The target-host acceptance run created a PSEC AppContainer process, but the process could not read the Workspace fixture or write its Scratch fixture. Both operations returned `PermissionError`. The test's Workspace write-denial result is therefore not evidence of PSEC read-only enforcement: the prerequisite read failed.

PSEC filesystem path policy and Windows object DACL authorization are separate enforcement layers. A path declared read-only/read-write in the PSEC policy does not, by itself, add an AppContainer Package SID ACE to the corresponding Windows security descriptors. The effective access decision must satisfy both the ordinary user/group authorization and the AppContainer authorization.

## 2. Non-negotiable safety properties

1. Never broaden ACLs on the user's real Project Workspace, profile, ProgramData, system directories, or shared parent directories to make acceptance pass.
2. Never grant access to `Everyone`, `Users`, `Authenticated Users`, or an unrelated AppContainer.
3. Never infer a capability's meaning from an opaque SID string. Require and record the exact Package SID; record capabilities as observed, not guessed.
4. Never resume a PSEC child until the required filesystem authorization has been applied and independently verified.
5. Never report Workspace write denial as a successful read-only test unless Workspace read succeeded first in the same test run.
6. If staging, ACL application, verification, Job Object drain, or cleanup is uncertain, fail closed and keep Terminal execution disabled.
7. Do not change `require_verified_isolation`, enable templates, or add a direct host-process fallback as part of this work.

## 3. Chosen architecture: isolated per-job projection

The preferred design is a per-job, disposable Workspace projection rather than temporary ACL mutation of the user's real Workspace.

- Treat the assigned Project Workspace as a read-only source.
- Create a unique, private staging root for one job. Copy only regular files and directories into the projection. Reject reparse points, junctions, symlinks, unsupported filesystem objects, and path escapes. Enforce bounded file count, total bytes, path length, and copy duration.
- Do not preserve source DACLs as authorization for the child. The host-side manager creates a known staging tree and applies only the exact child Package SID's read/traverse authorization to that disposable tree.
- Create a distinct per-job writable scratch root. Apply only the exact child Package SID's modify authorization to this scratch root.
- Build the PSEC policy against the projected Workspace path and the per-job scratch path, not the original Workspace path.
- Set the child's working directory to the projected Workspace and scope `HOME`, `USERPROFILE`, `LOCALAPPDATA`, `TEMP`, and `TMP` to the per-job scratch area.
- Keep the projection and scratch outside one another and outside all explicit deny roots. Do not use the host temp directory if it is denied by policy.
- On process completion, terminate/drain the entire Job Object first. Only then remove the projection and scratch. Cleanup failure is an acceptance failure and must be surfaced; do not silently ignore it.

This design intentionally avoids editing/restoring ACLs on the user's source Workspace. It also means changes made by the child are confined to disposable scratch; the current Terminal contract is read-only, so no write-back path is permitted.

## 4. Required implementation contracts

### 4.1 Source-tree inspection and projection

- Canonicalize the source root and ensure it is not a reparse point.
- Walk without following links. Inspect every entry for Windows `FILE_ATTRIBUTE_REPARSE_POINT`; reject rather than follow.
- Reject alternate data streams, device names, reserved DOS names, traversal components, and destination collisions after Windows case-folding.
- Copy regular files with bounded streaming I/O; do not trust source metadata as destination ACLs.
- Re-check source and destination entry types during the copy and fail if the source changes in a way that invalidates the snapshot.
- Record a deterministic manifest (relative path, object type, byte length, content hash) for the staged projection. Verify it after copy before launch.
- Keep the projection private to the runner and one job. No shared mutable staging directories.

### 4.2 Package SID authorization

- Obtain the Package SID from the suspended child token before resume. Require `is_app_container == true`, a syntactically valid Package SID, and complete token diagnostics.
- Apply a narrowly scoped read/execute ACE to every staged directory and file, and a narrowly scoped modify ACE to every scratch object that needs it. Do not assume inheritance reaches protected child DACLs.
- Apply authorization only to newly created, job-private objects. Do not change source Workspace ACLs or shared ancestor ACLs.
- Verify the resulting security descriptors and then prove actual access from the PSEC child. Descriptor inspection alone is not acceptance.
- If Windows path traversal or parent-directory authorization still prevents access, redesign the private root placement/creation strategy. Do not grant Package SID access to a shared parent as a workaround.

### 4.3 Lifecycle and recovery

- Keep staging/scratch ownership in a single idempotent lifecycle object.
- A successful launch transfers lifecycle ownership to the process facade.
- A failed launch before resume must terminate the suspended process (if created), close all handles, and remove only that job's private roots.
- Normal completion, timeout, cancellation, descendant termination, and Runner shutdown must all drain the Job Object before cleanup.
- If the Runner crashes, abandoned private roots must be recognizable by a durable job marker and cleaned only after proving no live Job/process still owns them. Never delete by broad glob or age alone.
- Cleanup must be idempotent and must not follow reparse points.
- A failed cleanup must leave an explicit durable failure record and keep the relevant execution gate closed.

### 4.4 PSEC policy and evidence

- PSEC `read_only_paths` must contain the staged projection, not the original Workspace.
- PSEC `read_write_paths` must contain only the per-job scratch.
- Enumeration paths must be a subset of those allowed roots.
- Explicit denied roots remain denied; staging must not be placed beneath a denied root.
- Record exact repo SHA, OS build, Package SID, token state, source/stage manifest hashes, ACL snapshots, PSEC support flags, child probe results, Job Object counts, and cleanup outcome.
- No evidence from a previous SHA may be silently carried forward after code changes.

## 5. Acceptance matrix

| Check | Required result | Notes |
|---|---|---|
| Package SID captured before resume | PASS | Missing/partial token data blocks launch |
| Source reparse-point rejection | PASS | Include symlink, junction, and nested reparse cases |
| Projection manifest | PASS | Source and staged hashes match |
| Workspace projection read | PASS | Must succeed before write test |
| Workspace projection write | DENIED | Must be denied by PSEC policy, not merely by missing DACL permission |
| Scratch create/write/read/delete | PASS | Only inside per-job scratch |
| Host profile canary read | DENIED | Host baseline read succeeds |
| Shared workspace ACL unchanged | PASS | Capture exact before/after descriptor |
| Shared parent ACL unchanged | PASS | No Package SID ACE added to shared ancestors |
| Cross-job isolation | PASS | Job A cannot access Job B projection or scratch |
| Concurrent jobs | PASS | No ACL or cleanup cross-talk |
| Descendant termination | PASS | Job Object active process count reaches zero |
| Timeout/cancellation cleanup | PASS | No child remains before root deletion |
| Runner-crash recovery | PASS | Only stale, unowned job roots are cleaned |
| Cleanup failure | FAIL-CLOSED | Terminal stays disabled |
| Full Windows Host Acceptance | PASS | Exact tested SHA and host build recorded |

A skipped test is `SKIPPED`, not `PASS`. A denied Workspace write without a successful preceding read is `INVALID_EVIDENCE`, not a passing read-only check.

## 6. Implementation sequence

1. Implement a pure, testable projection planner and path/manifest validation.
2. Implement Windows-only staging and reparse-point-safe traversal with strict resource ceilings.
3. Implement Package-SID ACL application and descriptor verification for private staging/scratch only.
4. Integrate the manager into `WindowsPsecLauncher` before `ResumeThread`; transfer cleanup ownership to `WindowsPsecProcess`.
5. Extend host acceptance to use independent fixtures for source Workspace, projection, and scratch; add cross-job and lifecycle adversarial cases.
6. Run portable unit tests and CI. Then run Windows unit tests and host acceptance on the target machine.
7. Review exact-SHA evidence and update PR #120 only after results are available. Keep PR #120 open and unmerged until its base PR and all required gates are satisfied.

## 7. Current state

The architecture decision and first projection primitives are committed. These primitives do not apply ACLs, do not prove AppContainer traversal, and are not integrated into the launcher. No ACL has been changed on the user's host. No production execution gate has been opened. Unit tests have been added but have not yet been executed in this environment; CI is the next validation source. Windows Host Acceptance remains pending.
