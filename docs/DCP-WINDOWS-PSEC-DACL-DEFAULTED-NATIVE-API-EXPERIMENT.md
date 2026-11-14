# WP-18B.1-K — DACL defaulted-state Native API experiment

**Status:** IMPLEMENTED HARNESS — native ACL writes are confined to disposable NTFS files; host acceptance remains UNKNOWN until exact Windows run evidence is captured  
**Repository:** `phakphum12345/development_control_platform`  
**Protocol:** DCP-CEEP v1.0  
**Related checkpoint:** PR #130 (`fix(psec): preserve DACL defaulted state in snapshots`)  
**Branch:** `work/wp18b1k-dacl-native-api-experiment-stack`  
**Base:** PR #130 head `a2e336eb034fdb2afc4340fe8228e87164afca9d` (stacked experiment base)

## 1. Objective

Determine, on a supported Windows host and NTFS, whether the documented handle-based `SetSecurityInfo` operation can preserve or restore the `SE_DACL_DEFAULTED` state observed through `GetSecurityDescriptorDacl`.

This experiment is deliberately separate from PR #130. It does not implement or enable the production Native Writer, transaction coordinator, Launcher, Terminal, or any template.

## 2. Evidence-based API boundary

Microsoft documents:

- `GetSecurityDescriptorDacl` returns `lpbDaclDefaulted` as the `SE_DACL_DEFAULTED` state when a DACL exists.
- `SetSecurityDescriptorDacl` accepts an explicit `bDaclDefaulted` argument, but modifies a security descriptor in memory; it is not an object-write API.
- `SetSecurityInfo` operates on an object handle and sets/clears descriptor control bits as appropriate. Its signature has no `bDaclDefaulted` argument.
- `SetKernelObjectSecurity` must not be used for file-system objects; Microsoft directs callers to `SetSecurityInfo`.

References:

- https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptordacl
- https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setsecuritydescriptordacl
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-operations
- https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setkernelobjectsecurity

**Decision constraint:** do not substitute `SetKernelObjectSecurity`, path-based `SetNamedSecurityInfo`, `SetFileSecurity`, undocumented calls, or raw on-disk edits for the documented file-handle API.

## 3. Disposable-object boundary

The harness may create only a unique temporary directory and files beneath it, on a verified NTFS volume. It must:

1. Create a fresh root using a collision-resistant name and verify the volume file-system name is NTFS.
2. Keep every opened handle bound to the exact object created by the harness.
3. Use `CreateFileW` with `CREATE_NEW`; reject pre-existing paths, reparse points, unexpected file identities, or a non-NTFS volume.
4. Never accept a caller-supplied target path.
5. Never resolve, enumerate, or mutate Workspace, Scratch, profile, system, repository, or other existing directories.
6. Remove only the harness-owned disposable root after handles are closed; record cleanup failure as a blocking result.

The test must not run if it cannot prove the disposable-root boundary.

## 4. Experiment cases

Run each case against a separate disposable file so a failed case cannot contaminate another case:

| Case | Initial state | Operation | Required observation |
|---|---|---|---|
| A | DACL explicitly specified; defaulted flag FALSE | Read twice, no write | Stable DACL bytes and FALSE state |
| B | Security attributes contain a descriptor whose DACL is marked defaulted TRUE | Read immediately after creation | Record whether NTFS retains TRUE; if it does not, classify the TRUE-state writer test as NOT EXERCISED |
| C | Case B object with observed TRUE state | Invoke `SetSecurityInfo` on retained handle using the same DACL bytes | Read back exact DACL bytes, `DaclDefaulted`, and relevant control bits |
| D | Case C after attempted write | Restore original DACL through the same supported handle API | Read back and compare bytes and control state; no best-effort PASS |
| E | Injected failure after the write attempt | Run the same rollback and cleanup path | Preserve primary and rollback errors; attempt cleanup even after failure |

Case B is a setup probe, not proof that the filesystem supports a TRUE state. Case C is the decisive API observation only if Case B actually reads back TRUE before the write.

The harness must not manufacture a TRUE observation by changing only an in-memory descriptor after the object has been created.

## 5. Capture and comparison requirements

Before the first object mutation, capture:

- volume serial and full file ID from the retained handle;
- file type and attributes, including reparse status;
- DACL-present and NULL-pointer state;
- `DaclDefaulted` returned by `GetSecurityDescriptorDacl`;
- descriptor control word and relevant DACL control bits;
- ACL revision, `AclSize`, `AceCount`, and the complete ACL allocation bytes;
- the exact native API, arguments/flags, return value, and `GetLastError` on failure.

Read-back must use the same retained handle. Compare the complete DACL bytes and all recorded control state; do not use SDDL text as a substitute for binary equality.

## 6. Rollback and cleanup contract

- Preserve the original snapshot before any write.
- Attempt rollback through the same documented handle API, even when the write reports failure after a possible partial effect.
- Read back after rollback and classify exact binary/control-state equality.
- Always close every owned handle and free every API-owned descriptor buffer with its matching allocator.
- Always attempt deletion of the harness-owned disposable tree after handles are closed.
- If exact rollback cannot be proven, the object must remain inside the disposable root and be deleted; report `ROLLBACK_NOT_VERIFIED_CLEANUP_REQUIRED` or `CLEANUP_FAILED_BLOCKED`, never PASS.
- Cleanup success does not convert failed rollback semantics into a successful round-trip result.
- Preserve both the primary experiment error and every rollback/cleanup error.

No production object may be used as a recovery target.

## 7. Acceptance vocabulary

Use only: PASS / FAIL / SKIPPED / UNKNOWN / IN_PROGRESS.

The TRUE-state round-trip can be marked PASS only if all are true:

1. Case B creates an NTFS object whose retained-handle read reports `dacl_defaulted == true`.
2. Case C executes the documented `SetSecurityInfo` call on that exact retained handle.
3. Read-back proves the expected DACL bytes and the TRUE defaulted state.
4. Case D restores the original bytes and TRUE state and verifies both.
5. Case E demonstrates rollback/cleanup behavior under injected failure.
6. All native buffers and handles are released, and the disposable root is removed.
7. Evidence records the exact Windows build, filesystem, Python version, test command, test output, and source commit SHA.

If the setup cannot produce a TRUE state, the TRUE-state writer question remains UNKNOWN / NOT EXERCISED. A FALSE-state test, a mock, CI success, or a skipped non-Windows test cannot satisfy this gate.

## 8. Explicit non-goals and safety gates

- No changes to PR #130.
- No production writer adapter or transaction integration.
- No Workspace, Scratch, user-profile, system-directory, or repository ACL writes.
- No Launcher integration, process resume, Terminal enablement, or template enablement.
- No merge or deployment authorization is implied by this branch.

PR #130 remains a separate Reader/Transaction checkpoint. Native Writer semantics and Terminal remain BLOCKED until the experiment produces target-host evidence and a separate security review approves the next step.

## 9. Implementation checkpoint

- Added `tools/local_runner_agent/windows_psec_dacl_experiment.py`.
- Added `tests/test_windows_psec_dacl_experiment.py`.
- The harness creates a unique temporary directory under the OS temp root, verifies the backing volume is NTFS, creates one file with `CREATE_NEW`, retains the handle, and builds an explicit empty DACL in an absolute security descriptor with the requested defaulted flag.
- The only mutation call is `SetSecurityInfo` on that retained file handle. The same captured DACL bytes are supplied for the write and rollback attempt.
- Read-back uses the existing `WindowsHandleSecurityReader` on the same handle. The harness captures volume serial and full 128-bit file ID, rejects directory/reparse targets, and rechecks identity after write and rollback. Rollback compares DACL bytes, `DaclDefaulted`, and descriptor control flags.
- Rollback is unconditional after every write attempt, including when read-back itself fails; primary write, read-back, rollback-write, and rollback-read errors are retained in the failure diagnostic.
- Cleanup closes the retained handle, deletes only the exact harness-created file, and removes only its exact empty temporary directory. Any cleanup failure blocks a successful result.
- The CI workflow now invokes this test module on Ubuntu and Windows. The native cases are skipped off Windows; the Windows CI result is GitHub-hosted runner evidence, not the user's local Windows-host acceptance.
- No experiment has been executed in this authoring session. No native round-trip result is claimed.

## 10. GitHub-hosted Windows evidence — 2026-11-14

Run: [Cross-platform Recovery Acceptance #43609971342](https://github.com/phakphum12345/development_control_platform/actions/runs/43609971342), merge checkout commit `36554d3f995a741ecac023b99e39da935b287d12`, PR head `4c11a6bdb4c91faf51cd7e17081ee9596d3e07bb`.

- Host: Microsoft Windows Server 2025 Datacenter, build `10.0.26100`; runner image `windows-2025-vs2026`.
- Python: CPython `3.12.10`, 64-bit AMD64.
- Filesystem: NTFS; volume serial `9823700658284110452`.
- Probe File ID: `8cb7040000006f000000000000000000`.
- FALSE case: initial and post-write/post-rollback `DaclDefaulted=false`; API error list empty; cleanup verified.
- Binary DACL before write: `0200080000000000` (8 bytes; explicit empty ACL).
- Binary DACL after write and rollback: `020048000300000000101400ff011f0001010000000000051200000000101800ff011f000102000000000005200000002002000000101400ff011f00010100000000000304000000` (72 bytes).
- Descriptor control words: before `36868 (0x9004)`; after write and rollback `33796 (0x8404)`. The protected-DACL bit was cleared and auto-inherited state appeared; the resulting ACL contains ACEs absent from the original empty ACL. This is consistent with inheritance being re-applied when the DACL is written, not proof of a single internal Windows implementation path.
- The previous test incorrectly allowed an experiment result of `FAIL` while unittest returned success. That acceptance loophole is closed in the current branch: TRUE/FALSE cases now require exact PASS, and process handle count must return to its pre-test value.
- Current code also sets `SE_DACL_PROTECTED` on the creation descriptor and supplies `PROTECTED_DACL_SECURITY_INFORMATION` to `SetSecurityInfo`, to preserve the inheritance boundary during write/rollback. These changes are pending a fresh Windows CI run; do not treat them as validated yet.

The TRUE case was skipped because the filesystem did not retain `DaclDefaulted=TRUE` at creation. Therefore TRUE-state writer semantics remain NOT EXERCISED. This GitHub-hosted run is not acceptance evidence for the user's own Windows host.

## 11. Resource lifecycle checks

- The existing reader copies ACL bytes and releases the descriptor returned by `GetSecurityInfo` using `LocalFree` in a `finally` block; a failed `LocalFree` is surfaced as an error.
- The experiment samples `GetProcessHandleCount` before and after as best-effort diagnostic context only. It is process-wide and is not an acceptance assertion or proof of harness ownership.
- Windows tests instead assert direct lifecycle evidence for the handle created by the harness: it was opened, `CloseHandle` returned success, and the handle was marked closed. This does not prove native heap/RSS stability; repeated-run and process-memory/heap evidence remains outstanding on the designated host.

## 12. Execution checklist

- [x] Review DCP-CEEP v1.0 and Microsoft API contracts.
- [x] Implement the isolated Windows-only harness.
- [x] Add a portable off-Windows fail-closed contract test.
- [x] Add Windows-only TRUE/FALSE disposable NTFS acceptance cases.
- [x] Add the test invocation to Cross-platform Recovery Acceptance.
- [ ] Run exact-head CI and inspect full logs.
- [ ] Run the native experiment on the designated Windows host.
- [ ] Append measured evidence and limitations; do not infer results.


## 13. WP-18B.1-K corrective instrumentation — 2026-11-14

The follow-up implementation changes the acceptance instrumentation without changing the disposable-object boundary:

- Every TRUE, FALSE, write-only, and ambiguous-error test emits `DACL_EXPERIMENT_EVIDENCE` with `flush=True` immediately after the harness returns and **before assertions**. A failing assertion therefore does not suppress the measured result.
- Each run captures three stages where applicable: immediately after `CreateFileW` (before any DACL write), immediately after `SetSecurityInfo`, and after rollback. The write-only case intentionally has no rollback stage.
- The write-only observation and write-plus-rollback acceptance use separate calls to the harness. Each call creates a new unique disposable root and file, so the write-only observation is not contaminated by a later rollback.
- The write-only case reports `OBSERVED`, not PASS. It records whether DACL bytes, `DaclDefaulted`, and control flags changed after the native call. The rollback case alone can report round-trip PASS, and only when exact state equality and cleanup are proven.
- The evidence now includes inherited ACE counts at each available stage. The parser reads only the bounded ACE header fields and counts `INHERITED_ACE (0x10)`; it does not parse or expose SID payloads. ACL capacity after the final ACE is permitted, while every ACE header and size is checked against the declared ACL size.
- The harness reports whether its own retained file handle was opened, whether `CloseHandle` succeeded, and whether it was closed. Windows tests assert this direct lifecycle evidence.
- `GetProcessHandleCount` remains best-effort diagnostic evidence only. Failure to sample it does not abort the experiment, and its process-wide delta is not an acceptance assertion because it cannot identify which component owns a handle.
- The ambiguous-write test still injects an error after the native write call and proves the rollback path is attempted. It also asserts harness-owned handle closure and disposable-root cleanup.

**Validation status:** these are source changes only at this checkpoint. They have not yet been run on a Windows host. Exact-head CI and the designated user-host acceptance remain pending. The TRUE case must still be classified NOT EXERCISED if the newly created NTFS file does not expose `DaclDefaulted=TRUE`. Do not treat `OBSERVED`, SKIPPED, or an old run as PASS.
