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
| A | DACL explicitly specified; defaulted flag FALSE | Read twice, then perform write/read-back/rollback on a disposable NTFS file | Stable DACL bytes, FALSE state, exact rollback, and cleanup |
| B | Input security descriptor has DACL defaulted TRUE | Inspect the descriptor in memory before it is supplied to object creation | `GetSecurityDescriptorDacl` reports TRUE on that input descriptor; record descriptor control flags and DACL bytes |
| C | Disposable NTFS object created from the TRUE input descriptor | Read immediately after creation; do not assume the flag survives association with the object | Record the object read-back. If NTFS does not retain TRUE, classify the object-level TRUE writer case as NOT EXERCISED |
| D | Case C object, only if its retained-handle read actually reports TRUE | Invoke `SetSecurityInfo` on that exact retained handle | Read back exact DACL bytes, `DaclDefaulted`, and relevant control bits |
| E | Case D after attempted write, only when D was exercisable | Restore original DACL through the same supported handle API | Read back and compare bytes and control state; no best-effort PASS |
| F | Injected failure after the write attempt | Run the same rollback and cleanup path | Preserve primary and rollback errors; attempt cleanup even after failure |

The TRUE input-descriptor contract and the NTFS object-persistence behavior are separate assertions. A TRUE value observed on an in-memory input descriptor is valid evidence for descriptor construction, but it is not evidence that NTFS stores or reads back TRUE on the securable object. The object-level TRUE writer case is exercisable only if the retained-handle read immediately after creation reports TRUE.

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

The input-descriptor TRUE contract can be marked PASS only when the in-memory descriptor test proves all of the following before object creation:

1. `SetSecurityDescriptorDacl` accepts the explicit TRUE defaulted argument.
2. `GetSecurityDescriptorDacl` on that same input descriptor reports TRUE.
3. The corresponding control flag is present and the DACL bytes/presence state are captured.
4. A paired FALSE input descriptor reports FALSE, demonstrating that the test distinguishes the two values.

The NTFS object-level TRUE writer round-trip is a separate acceptance item. It can be marked PASS only if all are true:

1. Case C creates an NTFS object whose retained-handle read reports `dacl_defaulted == true`.
2. Case D executes the documented `SetSecurityInfo` call on that exact retained handle.
3. Read-back proves the expected DACL bytes and TRUE defaulted state.
4. Case E restores the original bytes and TRUE state and verifies both.
5. Case F demonstrates rollback/cleanup behavior under injected failure.
6. All native buffers and handles are released, and the disposable root is removed.
7. Evidence records the exact Windows build, filesystem, Python version, test command, test output, and source commit SHA.

If NTFS does not retain TRUE on the newly created object, classify only the object-level TRUE writer round-trip as NOT EXERCISED. This does not invalidate a separately passing in-memory input-descriptor TRUE test. A FALSE-state object round-trip cannot substitute for the object-level TRUE case.

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

- Every TRUE, FALSE, write-only, and ambiguous-error test emits `DACL_EXPERIMENT_EVIDENCE` with `flush=True` immediately after the harness returns and **before assertions**. A failing assertion therefore does not suppress the measured result. If TRUE setup is not retained, the raised `DaclDefaultedNotExercised` carries the immediate post-create snapshot and the test prints it before classifying the case as SKIPPED / NOT EXERCISED.
- Each run captures three stages where applicable: immediately after `CreateFileW` (before any DACL write), immediately after `SetSecurityInfo`, and after rollback. The write-only case intentionally has no rollback stage.
- The write-only observation and write-plus-rollback acceptance use separate calls to the harness. Each call creates a new unique disposable root and file, so the write-only observation is not contaminated by a later rollback.
- The write-only case reports `OBSERVED`, not PASS. It records whether DACL bytes, `DaclDefaulted`, and control flags changed after the native call. The rollback case alone can report round-trip PASS, and only when exact state equality and cleanup are proven.
- The evidence now includes inherited ACE counts at each available stage. The parser reads only the bounded ACE header fields and counts `INHERITED_ACE (0x10)`; it does not parse or expose SID payloads. ACL capacity after the final ACE is permitted, while every ACE header and size is checked against the declared ACL size.
- The harness reports whether its own retained file handle was opened, whether `CloseHandle` succeeded, and whether it was closed. Windows tests assert this direct lifecycle evidence.
- `GetProcessHandleCount` remains best-effort diagnostic evidence only. Failure to sample it does not abort the experiment, and its process-wide delta is not an acceptance assertion because it cannot identify which component owns a handle.
- The ambiguous-write test still injects an error after the native write call and proves the rollback path is attempted. It also asserts harness-owned handle closure and disposable-root cleanup.

**Validation status:** these are source changes only at this checkpoint. They have not yet been run on a Windows host. Exact-head CI and the designated user-host acceptance remain pending. The TRUE case must still be classified NOT EXERCISED if the newly created NTFS file does not expose `DaclDefaulted=TRUE`. Do not treat `OBSERVED`, SKIPPED, or an old run as PASS.


## 14. Native SecurityInfo flag-isolation matrix — 2026-11-15

The Windows evidence on the current branch showed an unchanged empty DACL and unchanged `DaclDefaulted=FALSE`, while the descriptor control word changed from `0x9004` to `0x9404`. The `0x0400` delta is `SE_DACL_AUTO_INHERITED`; this is a descriptor capability/state bit and is not equivalent to observing an inherited ACE in the ACL.

Microsoft documents that `SetSecurityInfo` may set or clear descriptor control bits as appropriate, and that it supports automatic propagation of inheritable ACEs. Therefore the observed bit transition is a legitimate native API observation, not evidence by itself that an inherited ACE was added.

The follow-up isolates the two allowed flag combinations, each on a new disposable NTFS file:

| Case | SetSecurityInfo SecurityInfo | Purpose |
|---|---:|---|
| F1 | `DACL_SECURITY_INFORMATION (0x00000004)` | DACL-only baseline |
| F2 | `DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION (0x80000004)` | Existing protected-DACL request |

Both are write-only observations first. The existing round-trip test continues to use F2 and retains exact byte/defaulted/control-flag acceptance. The ambiguous-write rollback test also uses F2. No result is treated as PASS merely because the API call succeeds.

Evidence now records the exact SecurityInfo flags in decimal and hexadecimal. Compare the control word before/after, `SE_DACL_PROTECTED`, `SE_DACL_AUTO_INHERITED`, DACL bytes, `DaclDefaulted`, inherited ACE count, API errors, and cleanup independently. A fresh disposable file is used for each flag combination; the matrix never reuses an object after a native mutation.

**Interpretation constraint:** if F1 and F2 both add `SE_DACL_AUTO_INHERITED`, the bit transition is not isolated to the protected flag. If only F2 adds it, the result is correlated with the combined flag set but still requires cautious interpretation. This matrix does not test `SE_DACL_PROTECTED` creation-time policy, parent-directory propagation, or a TRUE-defaulted state; those remain separate questions.

Microsoft references:
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo
- https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-operations
- https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control

**Status:** implementation pending exact-head CI and Windows execution. Native Writer, Terminal, and built-in templates remain BLOCKED.


## 15. Windows flag-isolation run and rollback-injection correction — 2026-11-15

The supplied Windows Server 2025 / NTFS run on head `90e48b693885363183f8990d1f8102ccc06cab30` produced:

| Case | SecurityInfo | DACL bytes | DaclDefaulted | Control flags | Result |
|---|---:|---|---|---|---|
| F1 write-only | `0x00000004` | unchanged empty ACL (`0200080000000000`) | FALSE → FALSE | `0x9004 → 0x9404` | OBSERVED |
| F2 write-only | `0x80000004` | unchanged empty ACL (`0200080000000000`) | FALSE → FALSE | `0x9004 → 0x9404` | OBSERVED |
| FALSE round-trip | `0x80000004` | unchanged empty ACL | FALSE throughout | `0x9004 → 0x9404 → 0x9404` | FAIL |
| TRUE setup | n/a | inherited ACL at create | FALSE | `0x8004` | NOT EXERCISED / SKIPPED |

F1 and F2 both produce the same `SE_DACL_AUTO_INHERITED (0x0400)` control-bit transition. The evidence does not support attributing the transition specifically to `PROTECTED_DACL_SECURITY_INFORMATION`. Both write-only observations report zero inherited ACEs; the bit must not be misreported as proof that an inherited ACE was added.

The FALSE round-trip remains a genuine acceptance failure: rollback restores the same ACL bytes and FALSE defaulted state, but does not restore the original control word. Cleanup and the harness-owned handle close are verified. Do not relax exact control-state comparison.

The first ambiguous-write output is **invalid as evidence that rollback was exercised**. Its injected callback had the old two-positional-argument signature, while the production `_write_dacl` now requires keyword-only `security_info_flags`. The callback therefore raised `unexpected keyword argument 'security_info_flags'` before reaching the native call; its observed call count was zero. The test callback is corrected to accept and forward the keyword-only argument, and inject its exception only after the first native `SetSecurityInfo` call returns. Re-run this case on Windows before claiming rollback-injection acceptance.

**Current disposition:** F1/F2 observations are useful diagnostics; FALSE exact round-trip FAIL; TRUE NOT EXERCISED; ambiguous-write rollback NOT YET VERIFIED pending rerun after callback correction. Native Writer, Terminal, and all seven built-in templates remain BLOCKED.


## 16. Creation-only and repeated-write probes — 2026-11-15

Microsoft's SECURITY_DESCRIPTOR_CONTROL documentation makes an important distinction: SE_DACL_DEFAULTED is used to compute the final DACL and is **not stored physically in the security descriptor of a securable object**. SetSecurityInfo operates on the object descriptor and sets or clears component control bits as appropriate; it does not expose a parameter that persists the caller's in-memory bDaclDefaulted marker. Therefore a file-handle read-back cannot be treated as a round-trip store for that transient descriptor-construction flag.

References:
- https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control
- https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-operations
- https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo

The experiment now adds two isolated observations, each using its own CREATE_NEW disposable NTFS file and retained handle:

1. **Creation-only baseline:** write_repetitions=0 captures the descriptor immediately after creation and performs no SetSecurityInfo call. This distinguishes creation-time behavior from changes caused by a later write.
2. **Repeated native writes:** write_repetitions=3 calls SetSecurityInfo three times on the same retained handle, reading the descriptor control word after every call. This tests whether the 0x0400 transition occurs only on the first call or is repeated. It remains an observation, not a writer acceptance test.

The API sequence is bounded to 0–8 writes. A zero-write probe cannot request rollback. Every native call uses the existing allow-listed DACL_SECURITY_INFORMATION mask or the existing combined protected-DACL mask. No new security-information flags, target paths, or object types are accepted.

Evidence adds native_write_calls and control_flags_after_each_write. The existing exact round-trip assertion is deliberately unchanged: the FALSE case still reports FAIL if the complete control word cannot be restored. The new probes do not convert that result to PASS and do not authorize Native Writer.

**Interpretation boundary:** a creation-only FALSE result is a baseline, not proof that TRUE can be stored. A TRUE setup that is not retained remains NOT EXERCISED. Repeated writes can characterize control-bit stability, but cannot prove that the original descriptor control word is writable or reversible through SetSecurityInfo.
## 17. First-write control-bit transition — 2026-11-15

Exact-head Windows evidence was inspected from Cross-platform Recovery Acceptance run
[43626600331](https://github.com/phakphum12345/development_control_platform/actions/runs/43626600331),
Windows job 132543717452, on PR head
cf5e43aec6b6f7e72fc20b3c41fa052d585ff7e9 (workflow merge checkout
aa32b6f79bd9b2b1e25a69f241ff0bb230276743). Host: Windows Server 2025
build 10.0.26100, CPython 3.12.10, NTFS.

The stage-by-stage observations are:

| Stage / probe | Native SetSecurityInfo calls | Control word | DACL bytes | DaclDefaulted | Inherited ACEs |
|---|---:|---:|---|---|---:|
| FALSE creation-only baseline | 0 | 0x9004 | empty ACL, 0200080000000000 | FALSE | 0 |
| FALSE repeated-write probe, after call 1 | 1 | 0x9404 | unchanged | FALSE | 0 |
| FALSE repeated-write probe, after call 2 | 2 | 0x9404 | unchanged | FALSE | 0 |
| FALSE repeated-write probe, after call 3 | 3 | 0x9404 | unchanged | FALSE | 0 |
| FALSE round-trip, after first write | 1 | 0x9404 | unchanged | FALSE | 0 |
| FALSE round-trip, after rollback | rollback attempted | 0x9404 | unchanged | FALSE | 0 |

The repeated-write evidence records control_flags_after_each_write=[37892, 37892, 37892]
(hex [0x9404, 0x9404, 0x9404]) against the creation baseline 0x9004.
Therefore, on this Windows Server 2025 / NTFS host, the 0x0400
(SE_DACL_AUTO_INHERITED) transition is first observed immediately after
the first SetSecurityInfo call. The second and third calls leave the
observed word unchanged. This is a measured call-order correlation; it does
not establish undocumented internal implementation details.

The flag-isolation probes show the same 0x9004 -> 0x9404 transition for
both DACL_SECURITY_INFORMATION (0x4) and
DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION
(0x80000004). The transition is therefore not isolated to the protected
flag. All these probes retain the same empty DACL bytes, report
DaclDefaulted=FALSE, and count zero inherited ACEs. Do not infer that an
inherited ACE was added from SE_DACL_AUTO_INHERITED alone.

Rollback is separately observable: the round-trip case starts at
0x9004, reads 0x9404 after its first write, then still reads
0x9404 after the rollback SetSecurityInfo attempt. The DACL bytes
and FALSE state remain unchanged, but the original control word is not
restored. The strict exact-state test correctly remains FAIL.

The corrected ambiguous-write injection also ran on this job. Its callback
count was 2: the first native write returned, the injected error was raised,
and the second callback invocation reached the rollback write. The result
reports rollback_attempted=true, final control word 0x9404, unchanged DACL
bytes, zero inherited ACEs, successful owned-handle close and cleanup.
The result field native_write_calls counts the forward write loop and
does not include the rollback call; use the callback count and
rollback_attempted for this injected-path evidence, not that field as a
total native-call count.

**Architecture finding:** this experiment demonstrates that the supported
handle-based SetSecurityInfo path on the tested host changes the object
descriptor control word on its first DACL write and does not restore the
original control word when the same DACL is written again for rollback.
The experiment does not demonstrate a way to clear or restore the
SE_DACL_AUTO_INHERITED bit through the currently permitted
SetSecurityInfo interface. This is a bounded host-specific finding, not
a universal claim about every Windows version or filesystem.

**Disposition:** retain the strict FALSE round-trip FAIL and TRUE
NOT EXERCISED / SKIPPED. No comparator change, no masking of 0x0400,
no expected-outcome downgrade, and no Native Writer or transactional ACL
mutation enablement. PR #134 remains untouched. A future API-capability
investigation must be isolated and must not substitute undocumented or
out-of-scope object mutation APIs.