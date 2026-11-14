# Windows PSEC Native Handle ACL Engine — WP-18B.1-A

**Status:** DESIGN CHECKPOINT — implementation and host acceptance not yet verified  
**Protocol:** DCP-CEEP v1.0  
**Parent checkpoint:** PR #122, branch `work/wp18b1-package-sid-acl-manager`  
**Starting source SHA:** `0ada90d4e78d701a561f8fcecf238dce746ee00a`

## 1. Purpose and non-goals

Replace the path-based ACL mutation sequence in `windows_psec_acl.py` with a race-resistant, handle-relative authorization engine for a single disposable PSEC job tree.

This checkpoint does not authorize:
- integration into `WindowsPsecLauncher`;
- resuming a child after ACL setup;
- mutation of source Workspace, shared parent, or host profile ACLs;
- broad-principal grants or fallback to path-based security APIs;
- enabling Terminal execution or any built-in template;
- merging this branch or any stacked PR.

The current path-based ACL manager remains a diagnostic/prototype implementation only.

## 2. Required security invariants

1. **Exact identity:** the Package SID must be read from the exact suspended child token. The SID used for ACLs must be bound to that launch attempt and never reused from a previous run.
2. **Private targets only:** the only mutable objects are the disposable job root, projected Workspace tree, and per-job Scratch tree. The source Workspace and every ancestor above the job root are immutable.
3. **Parent-relative traversal:** every descendant is opened relative to an already validated directory handle. Absolute-path re-resolution is not an acceptable substitute.
4. **Stable object identity:** record and revalidate volume identity, 128-bit file ID, object type, and reparse attributes on the same retained handle before every security mutation.
5. **Preflight before mutation:** open, enumerate, validate, and snapshot the complete target set before the first DACL write. Any preflight uncertainty means zero DACL writes.
6. **Handle-based security:** use `GetSecurityInfo` and `SetSecurityInfo` against retained kernel handles. Do not call `GetNamedSecurityInfoW` or `SetNamedSecurityInfoW` in this engine.
7. **Exact least privilege:** Package SID receives only `FILE_TRAVERSE` on the disposable job root, `READ_EXECUTE` on projected Workspace objects, and `MODIFY` on Scratch objects. No grant to Everyone, Users, Authenticated Users, or another broad principal.
8. **Transactional failure:** if any mutation or read-back fails, restore every already-mutated target from its captured original DACL using the same retained handle. If rollback cannot be proven complete, return a distinct fail-closed cleanup state and keep execution blocked.
9. **No resume on uncertainty:** Launcher integration, when separately approved, must not call `ResumeThread` unless authorization is fully verified and ownership of all handles/lifecycle state has transferred successfully.
10. **Drain before cleanup:** do not remove projected Workspace or Scratch until the Job Object reports `ActiveProcesses == 0`, all child handles are closed, and cleanup ownership is exclusive.

## 3. Native traversal design

### 3.1 Root and child opening

- Open the pre-created job root with `CreateFileW` using directory-compatible flags, `FILE_FLAG_BACKUP_SEMANTICS`, and `FILE_FLAG_OPEN_REPARSE_POINT`.
- Verify the root is a directory and not a reparse point using handle-derived file attributes.
- Open each child relative to its validated parent directory handle. Preferred mechanism: `NtCreateFile` with `OBJECT_ATTRIBUTES.RootDirectory` set to the retained parent handle and a single-component relative `UNICODE_STRING`; include `FILE_OPEN_REPARSE_POINT` and non-directory/directory create options as appropriate.
- Convert NTSTATUS values with `RtlNtStatusToDosError` for diagnostics, while preserving the original NTSTATUS in evidence.
- Reject names containing separators, `.`, `..`, alternate-stream separators, NUL, or unsupported Windows namespace forms. Enumerate from the open directory handle; do not reconstruct child identity by joining strings and reopening an absolute path.
- Open with the minimum access required for enumeration, identity, and security descriptor read/write. Do not request write-data access merely to change the DACL.

If the implementation cannot prove that a child handle was opened relative to the exact parent handle, it must stop and report `UNSUPPORTED_HANDLE_RELATIVE_OPEN`; no path-based fallback is permitted.

### 3.2 Object identity

For each retained handle capture:
- volume serial / volume identity;
- complete 128-bit file ID (`FILE_ID_INFO`, not only the legacy 64-bit file index);
- file attributes and reparse tag;
- object kind (directory or regular file);
- parent object identity and relative child name.

Before changing an object's DACL, query the same handle again and require all identity/type fields to match the preflight record. Reject reparse points, hard-link ambiguity where it prevents the intended containment guarantee, unsupported file types, duplicate/case-fold-colliding names, and resource-limit violations.

The identity check is evidence against path substitution; the retained handle is the authority for the subsequent security operation.

## 4. Security descriptor transaction

### 4.1 Snapshot

Before any write, obtain the security descriptor from each target handle with `GetSecurityInfo`. Capture:
- original DACL bytes and ACE order;
- DACL-present and DACL-null state;
- DACL protected/auto-inherited control flags;
- owner/group/control metadata needed to detect unintended changes;
- a stable hash of the captured descriptor for evidence.

The snapshot must own independent copies of all memory; do not retain pointers into a descriptor buffer that is freed.

### 4.2 Mutation

- Parse the native ACL by ACE type and SID, not by lossy SDDL regular expressions.
- Preserve all existing ACEs and their order unless the documented merge algorithm requires a deterministic safe insertion.
- Detect all Package-SID ACEs, including deny, allow, object-specific, callback/conditional, and unsupported ACE variants. If an ACE cannot be fully interpreted, fail closed rather than ignoring it.
- Reject pre-existing Package-SID allow grants broader than the exact target mask.
- Add only the exact allow mask for the target class. Workspace directories may use inheritance only if the implementation separately proves that protected descendants are explicitly handled; the default is explicit per-object grants.
- Use `SetSecurityInfo` on the retained handle. Preserve DACL protection state deliberately; never silently unprotect a protected DACL or change owner/group/SACL.
- Read the DACL back from the same handle and verify the exact Package SID, exact mask, ACE type, flags, and absence of overbroad Package-SID allow ACEs.

### 4.3 Rollback

- Keep original descriptor snapshots and retained handles until all writes and read-backs succeed.
- On any error, restore mutated DACLs in reverse order using `SetSecurityInfo` on the same handles.
- Re-read every restored DACL and compare its canonical binary representation with the original snapshot; SDDL string equality alone is not sufficient.
- Report `ROLLBACK_VERIFIED` only if every object matches. Otherwise report `ROLLBACK_FAILED_FAIL_CLOSED`; never resume the process and never claim cleanup success.
- Close handles deterministically in a `finally` path. Handle-close failures are recorded and block lifecycle success.

## 5. Authorization layout and ancestor traversal

The target-host evidence has not established that the AppContainer can traverse from the unchanged shared parent into the disposable job root. `FILE_TRAVERSE` on the job root does not prove that its ancestors are traversable.

Before considering this layout viable:
- capture the exact child token's complete privilege set, including whether `SeChangeNotifyPrivilege` is present and enabled;
- test pathname traversal and actual Workspace/Scratch operations from the real PSEC child;
- keep the shared parent DACL byte-for-byte unchanged.

If the child cannot reach the job root, do not grant an ACE on the shared parent. Redesign the per-job root placement or establish another documented mechanism whose additional mutable ancestors are themselves job-private. Host-side handle-relative access does not confer access to paths used by the PSEC child.

## 6. Launcher lifecycle contract (future, separately gated)

The future integration sequence must be:

1. Create the process suspended and capture complete identity evidence from its token.
2. Create/own the Job Object and assign the suspended process.
3. Build the private projection and Scratch tree; verify manifests and resource ceilings.
4. Open and preflight the complete object tree by retained handles.
5. Apply Package-SID DACL changes transactionally and verify read-back.
6. Verify ancestor traversal assumptions without changing shared ancestors.
7. Only then resume the child.
8. Transfer an explicit lifecycle owner containing process, Job Object, directory handles, descriptor snapshots, and cleanup state.
9. On normal exit, timeout, cancellation, descendant termination, or runner shutdown, wait for Job Object active process count to reach zero before cleanup.
10. If drain, rollback, or cleanup cannot be proven, keep Terminal execution disabled and persist a failure record.

No step may silently fall back to an unsandboxed host process.

## 7. Adversarial test matrix

| Test | Required outcome |
|---|---|
| Child replaced by junction between enumeration and open | Rejected; no DACL mutation |
| Parent renamed/replaced while child is opened | Relative handle remains bound to original parent; mismatch/replacement rejected |
| File replaced between preflight and mutation | Retained handle identity remains stable; namespace replacement is not mutated |
| Directory replaced between preflight and mutation | Same as above; no path re-resolution |
| Nested reparse point | Rejected before first mutation |
| Unsupported object / alternate stream | Rejected before first mutation |
| Case-folding collision | Rejected before first mutation |
| Unsupported/object/callback ACE | Fail closed; no silent parser omission |
| Existing overbroad Package-SID allow ACE | Rejected; no mutation |
| Failure on Nth SetSecurityInfo | All prior writes rolled back and binary descriptor equality verified |
| Rollback failure | `ROLLBACK_FAILED_FAIL_CLOSED`; no resume |
| Read-back mismatch | Rollback; no resume |
| Shared parent descriptor | Byte-identical before/after |
| Workspace effective access | Read succeeds; write denied by PSEC policy |
| Scratch effective access | Create/write/read/delete succeeds only inside that job |
| Cross-job access | Job A cannot access Job B Workspace or Scratch |
| Job Object drain timeout | No deletion; explicit cleanup failure |
| Concurrent jobs | No cross-job SID, ACL, or cleanup interference |
| Runner restart / abandoned root | Cleanup only after proving no live owner; never by broad glob or age alone |

Tests must include native Windows integration tests on a dedicated disposable volume/root. Mocked API tests are useful for deterministic fault injection but cannot establish kernel behavior.

## 8. Evidence and acceptance gates

Required evidence must bind to the exact tested source SHA and include:
- Windows edition/build, Python architecture/version, filesystem and volume identity;
- PR/base/head SHA;
- child process ID, token AppContainer state, exact Package SID and complete privilege set;
- per-object identity records and pre/post descriptor hashes;
- count and type of objects preflighted/mutated/verified/rolled back;
- injected fault point and rollback result;
- effective Workspace read, PSEC write denial after successful read, Scratch operations;
- unchanged shared-parent descriptor;
- Job Object active-process count and cleanup result.

A unit-test pass, mocked API pass, SDDL read-back, or GitHub-hosted Windows workflow alone is not full target-host acceptance.

## 9. Current checkpoint result

At creation:
- PR #122 is OPEN / DRAFT and unmerged.
- Its exact source head is `0ada90d4e78d701a561f8fcecf238dce746ee00a`.
- Three PR workflow runs on that head report success; Combined Status API returned an empty list (UNKNOWN).
- The user's latest target-host PSEC acceptance is FAIL for Workspace read and Scratch write. Workspace write denial is invalid evidence because read failed.
- The existing ACL manager is path-based and is not integrated into the launcher.
- No host ACL mutation is authorized or performed by this design checkpoint.
- Terminal execution remains BLOCKED; all seven built-in templates remain DISABLED.
- This document is a design artifact only. It does not claim implementation, tests, effective access, or security verification.


## 10. Implementation checkpoint — native relative child opener

Commit sequence on `work/wp18b1-native-handle-acl-engine` now includes a first
Windows-only native primitive in
`tools/local_runner_agent/windows_psec_native_handles.py` and portable
contract tests in `tests/test_windows_psec_native_handles.py`.

Implemented in this increment:
- `NtCreateFile` opens exactly one child component with
  `OBJECT_ATTRIBUTES.RootDirectory` set to the retained parent directory
  handle. There is no absolute-path fallback.
- `FILE_OPEN_REPARSE_POINT` is requested, then the opened handle is checked
  for `FILE_ATTRIBUTE_REPARSE_POINT`.
- Expected directory/file type is enforced with NT create options and verified
  again from handle-derived attributes.
- Stable identity is captured from `FILE_ID_INFO`: volume serial plus the
  complete 128-bit file ID. Re-query operates on the same handle.
- Retained handle close is explicit and idempotent; close failures are surfaced.
- Relative component validation rejects separators, ADS syntax, dot traversal,
  control characters, Win32-normalized suffixes, reserved DOS device names,
  invalid Unicode sequences, and components exceeding the NT limit.

**Explicitly not implemented in this increment:**
- secure root-handle acquisition and handle-based directory enumeration;
- parent-child relationship enumeration proof for a complete tree;
- native ACL descriptor parsing, `GetSecurityInfo` / `SetSecurityInfo`,
  transactional DACL application, and rollback;
- integration into `WindowsPsecLauncher`;
- real-host reparse-race and replacement tests.

The primitive is not yet a complete ACL engine and must not be called by the
launcher. The portable tests exercise name validation, identity data shape,
and handle ownership behavior; they do not exercise the Windows kernel APIs.
The branch CI and dedicated Windows host tests remain required evidence.

- Before each relative open, re-query the retained parent handle and require its
  volume/file identity to match the captured parent identity; reject a parent
  that is not a directory or is itself a reparse point.
- The portable tests now cover parent identity mismatch, non-directory parents,
  and reparse-parent rejection. Native kernel behavior remains untested here.


## 11. Implementation checkpoint — trusted root and directory enumeration

The next increment adds `tools/local_runner_agent/windows_psec_handle_tree.py`
and contract tests in `tests/test_windows_psec_handle_tree.py`.

Implemented in this increment:

- Accept only drive-letter absolute paths (for example, `C:\\work\\job`).
  UNC paths, device/extended namespaces, slash-normalized paths, ADS syntax,
  empty components, and traversal components are rejected.
- Acquire the drive root with `CreateFileW` using directory and
  open-reparse-point flags; validate the root from its handle-derived identity.
- Traverse each subsequent directory component with the existing
  `NtCreateFile` relative-child opener rooted at the retained parent handle.
  Every parent is re-queried and identity-checked before the next open.
- Enumerate direct children from the retained directory handle using
  `FileIdExtdDirectoryRestartInfo` / `FileIdExtdDirectoryInfo` (128-bit
  file IDs). There is no fallback to the legacy 64-bit directory information
  class.
- Open each enumerated child relative to the retained directory handle and
  require its full 128-bit File ID, volume serial, object kind, and non-reparse
  state to match the enumeration record.
- Reject reparse points, duplicate/case-fold-colliding names, duplicate file
  identities (including hard-link aliases in the enumerated directory), invalid
  names, malformed enumeration offsets, and resource-ceiling violations.
- Return retained child handles to the caller; close operations run in reverse
  ownership order and report close failures.

Safety and scope limits:

- This increment is read-only with respect to filesystem contents and ACLs.
  It creates no files, changes no DACLs, and does not touch shared parent ACLs.
- The root path parser intentionally supports only drive-letter paths. UNC,
  volume-GUID, mount-point, and device namespace support is NOT IMPLEMENTED.
- Enumeration is direct-child only. A caller must recurse explicitly and retain
  the required parent/child handles; no full-tree manifest or mutation engine is
  claimed yet.
- The 128-bit extended directory information class is required. Unsupported
  systems/filesystems fail closed; no weaker 64-bit fallback is permitted.
- Portable parser/path tests do not exercise `CreateFileW`, `NtCreateFile`, or
  kernel directory enumeration. Dedicated Windows host tests remain required.
- No ACL mutation, launcher integration, process resume, Terminal execution, or
  built-in template activation is included.

The next gate is dedicated Windows validation of drive-root acquisition,
nested relative traversal, extended-ID enumeration, replacement/reparse races,
resource ceilings, and deterministic handle cleanup. Only after that evidence
should native security-descriptor transaction work begin.
