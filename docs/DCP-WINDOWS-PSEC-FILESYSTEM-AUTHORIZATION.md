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


## 8. Windows-managed AppContainer profile path — read-only investigation

Microsoft documents two relevant APIs:

- `CreateAppContainerProfile` creates a per-user, per-AppContainer data profile and returns the Package SID. Microsoft states that its profile folders have ACLs that protect them from other users and apps. The profile name is constrained and an `ERROR_ALREADY_EXISTS` result is distinct from successful creation.
- `GetAppContainerFolderPath` accepts an AppContainer SID string and returns that container's local application-data path. The returned path is the AppContainer's `FOLDERID_LocalAppData` location. The caller must release the returned string with `CoTaskMemFree`.

References:
- https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer
- https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile
- https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getappcontainerfolderpath

Important limits:
- `GetAppContainerFolderPath` is a path lookup, not documented proof that a profile is registered, that the directory exists, or that a child process can access it.
- `CreateAppContainerProfile` creates a profile from a name and returns the SID for that profile. It cannot be assumed to adopt an independently-created PSEC Package SID. Do not create a persistent profile as an experiment or change the PSEC identity lifecycle without an explicit design and cleanup contract.
- The target host acceptance harness now records the exact Package SID's managed profile path, directory existence, ACL snapshot, and whether the child's reported `LOCALAPPDATA` matches it. This probe is read-only and does not create profiles or modify ACLs.
- A captured path or ACL is diagnostic evidence only. The child must still prove access from its own PSEC token. If PSEC does not use a registered profile for the exact Package SID, this route is unavailable and the isolated-root authorization design remains unresolved.

## 9. Protocol v1 checkpoint — 2026-11-14

- Recon: PR #121 exact head was `c7e23fcb1716a12ad7ed364355328ae5a1045408`; all three CI workflows succeeded, while the Windows runner acceptance matrix was skipped.
- Inventory: projection primitives and fail-closed token identity validation exist; Package-SID ACL application, native handle-based traversal, and launcher lifecycle integration do not.
- Gap: the original host acceptance still fails Workspace read and Scratch write with `PermissionError`. The derived Workspace write-denial result remains invalid evidence.
- Implementation: add a read-only `GetAppContainerFolderPath` diagnostic to the Windows host acceptance harness. It reports path, directory existence, ACL evidence, and child `LOCALAPPDATA` match without changing host state; add mocked unit tests for successful lookup, environment mismatch, HRESULT failure, and missing SID.
- Testing: the exact implementation/test head is now `88af4eddba5bb892027b95e4954466ee5a716b9b`; fresh CI and target-Windows execution are pending. CI success alone cannot establish the profile mapping or child access.
- Safety: no ACL mutation, no persistent profile creation, no direct host-process fallback, no Terminal template activation, no merge.
- Next: run the updated harness on the target Windows host. Use its evidence to decide whether the PSEC-created Package SID has a Windows-managed profile root. Only then finalize the per-job scratch/projection authorization strategy.


## 10. Package-SID ACL manager — first implementation checkpoint

Branch `work/wp18b1-package-sid-acl-manager` adds `windows_psec_acl.py` and mocked unit coverage.

- Accepts only a syntactically valid AppContainer Package SID (`S-1-15-2-...`).
- Requires sibling `workspace` and `scratch` roots beneath a `dcp-psec-job-*` directory.
- Applies the exact Package SID's `READ_EXECUTE` (`0x001200a9`) to every projected Workspace directory/file and `MODIFY` (`0x001301bf`) to every Scratch directory/file.
- Adds only `FILE_TRAVERSE` (`0x20`) to the disposable job root so the child can traverse to its authorized roots. It does not add an ACE to the job-root parent.
- Uses `ConvertStringSidToSidW`, `GetNamedSecurityInfoW`, `SetEntriesInAclW`, `SetNamedSecurityInfoW`, and SDDL read-back verification. Existing DACL entries are merged, not replaced.
- Rejects reparse points, unsupported objects, non-canonical roots, overlap, and unexpected directory layout. It snapshots the job-root parent SDDL and fails if that parent changes.
- Rejects an overbroad Package-SID allow ACE detected in the resulting SDDL.

**Important limitations / not yet launchable:**
- This first implementation uses path-based enumeration and Win32 named-security APIs. It is not yet native handle-relative traversal and therefore is not approved as a complete security boundary.
- It is not yet integrated into `WindowsPsecLauncher`; no process may be resumed on the assumption that this module has already run.
- The caller must supply the disposable projection layout produced by `create_workspace_projection`. The existing launcher still accepts the older Workspace/Scratch layout.
- Descriptor read-back is necessary but not sufficient. Target Windows acceptance must prove Workspace read, PSEC-enforced Workspace write denial after successful read, Scratch create/write/read/delete, traversal from the real parent, and unchanged shared-parent ACLs.
- No host ACL has been changed by this repository-side work. Terminal execution remains blocked and all seven built-in templates remain disabled.

### Interpretation of the latest profile probe

The target run's `GetAppContainerFolderPath` result `0x80070002` is an API lookup failure, not conclusive proof that PSEC creates an anonymous or unregistered AppContainer. In the current launcher, `_apply_sandbox_profile_environment` explicitly overrides `LOCALAPPDATA` to the supplied Scratch path. The child's environment value is therefore not independent evidence of Windows-managed profile placement. Do not infer profile lifecycle from that environment variable alone.


## 11. Real Win32 ACL API smoke test — opt-in target-host checkpoint

Commit `fa5955e328360eba7e68d3ff93b1eef91166292c` adds
`tests/test_windows_psec_acl_real_host.py`. This test is intentionally
opt-in and Windows-only. It exercises the real `_WindowsAclApi` calls
(`ConvertStringSidToSidW`, `GetNamedSecurityInfoW`,
`SetEntriesInAclW`, `SetNamedSecurityInfoW`) and verifies SDDL read-back
against a disposable tree under the pre-created acceptance parent.

Run only on the dedicated Windows acceptance host, after confirming the
acceptance parent is the intended test directory:

```powershell
$env:DCP_PSEC_REAL_ACL_TEST = "1"
$env:DCP_PSEC_REAL_ACL_PACKAGE_SID = "S-1-15-2-4048921270-1110085035-832899681-549863699-8652410-2260480956-1408363724"
$env:DCP_PSEC_ACCEPTANCE_PARENT = "C:\\DCP-PSEC-Acceptance"

py -3 -m unittest tests.test_windows_psec_acl_real_host -v
if ($LASTEXITCODE -ne 0) {
    throw "Real Win32 ACL API smoke test failed"
}
```

The test creates a unique temporary child below the acceptance parent, then
creates only its own `dcp-psec-job-*` tree. It snapshots both the acceptance
parent and the immediate temporary parent DACLs and requires them to remain
byte-for-byte identical in SDDL. The disposable child tree is removed by
`TemporaryDirectory` cleanup.

This is deliberately **not** an AppContainer effective-access test and does
not validate a race-resistant traversal boundary. It only confirms that the
native ACL API round-trip and descriptor verification work on the target
filesystem. Do not interpret a pass as permission to integrate the path-based
manager into the launcher.

## 12. Native handle-relative traversal — implementation gate

The next security implementation must replace the current path-based
preflight/apply sequence before launcher integration:

1. Open the job root, Workspace, Scratch, and each descendant with handles
   opened using `FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT`
   (or a verified native relative-open equivalent). Reject every handle whose
   file attributes include `FILE_ATTRIBUTE_REPARSE_POINT`.
2. Record stable object identity from `BY_HANDLE_FILE_INFORMATION`:
   volume serial number and the 64-bit file index. Also record object type.
3. Enumerate each directory from its already-open directory handle; open each
   child relative to that directory handle where supported. Do not trust a
   second path lookup to identify the object that was preflighted.
4. Retain all validated handles through ACL application. Before changing a
   DACL, re-query identity and type on the same handle and require exact
   equality with the preflight record.
5. Use handle-based security APIs (`GetSecurityInfo` and
   `SetSecurityInfo`) for the retained object handles; do not fall back to
   `GetNamedSecurityInfoW` / `SetNamedSecurityInfoW` for the security write.
6. Read back the descriptor from the same handle and verify the exact SID,
   mask, inheritance flags, and absence of overbroad Package-SID allow ACEs.
7. Close all retained handles deterministically. Any enumeration, identity,
   access, descriptor, or cleanup uncertainty is a hard failure before
   `ResumeThread`.

The `CreateFileW` flags alone do not make a multi-step path walk handle-relative:
the implementation must prove that each opened child is the child of the
already-validated parent handle, not merely an object reached by re-resolving
an absolute path. If that cannot be established with the selected Win32 API,
use `NtCreateFile` with `OBJECT_ATTRIBUTES.RootDirectory` and a relative
`UNICODE_STRING`, with explicit status conversion and exhaustive handle
cleanup. Do not ship a path-based approximation under a handle-relative name.

The handle traversal change requires dedicated Windows tests for:
- a junction/reparse swap between enumeration and open;
- replacement/rename between preflight and ACL application;
- file and directory identity stability;
- parent-child relationship enforcement;
- no ACL writes after any failed preflight;
- exact SDDL read-back on the retained handle;
- no mutation of the acceptance parent or any shared ancestor.

Launcher integration remains blocked until this gate and the real-host API
round-trip both pass. Job Object drain must then be strengthened so cleanup
waits for `ActiveProcesses == 0`; timeout or inability to prove zero is a
cleanup failure, not permission to remove the projection or Scratch tree.


### Ancestor traversal dependency — explicitly unresolved

The current ACL manager grants `FILE_TRAVERSE` on the disposable job root but
intentionally leaves its parent unchanged. That is safe with respect to shared
ACL mutation, but it does **not yet prove** that an AppContainer can reach the
job root by pathname. Windows may bypass directory traversal checks when the
token has the relevant enabled privilege; the current host evidence does not
record whether `SeChangeNotifyPrivilege` is present and enabled. Do not infer
that it is.

Before treating the ACL layout as viable, capture the child token's complete
privilege set and test actual pathname access from the suspended-then-resumed
PSEC child. If traversal fails, do not add an ACE to a shared acceptance parent.
Redesign placement so any additional traversal ACE is confined to a newly
created per-job ancestor whose own parent is already traversable under the
actual token, or establish another documented safe mechanism. Handle-relative
opens by the host do not, by themselves, grant the child access to PSEC policy
paths. The child must still prove effective access.
