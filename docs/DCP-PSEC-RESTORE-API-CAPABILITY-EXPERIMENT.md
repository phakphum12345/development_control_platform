# PSEC Disposable NTFS Restore API Capability Experiment

**Protocol family:** PSEC DACL Protocol v1  
**Status:** EXPERIMENTAL — hosted Windows NTFS matrix completed; exact-head CI isolation verified; local Windows 11 acceptance pending  
**Target:** Newly created harness-owned NTFS files only  
**Production writer:** BLOCKED

## 1. Objective

Determine whether documented Windows file-security APIs can restore the original DACL descriptor state captured in immutable S0 after a DACL write changes the descriptor control word.

Each candidate receives a new disposable file, an independent S0 snapshot, one controlled mutation to S1, and one candidate restoration attempt followed by an independent S2 read-back.

## 2. Candidate Matrix

| Candidate | API | Restore operation | Purpose |
|---|---|---|---|
| A | SetSecurityInfo | Handle-based DACL + UNPROTECTED flag | Test whether unprotecting recomputes the original control state |
| B | SetNamedSecurityInfoW | Name-based DACL + UNPROTECTED flag | Compare the documented name-based counterpart |
| C | SetFileSecurityW | Legacy DACL write with original protected control bit | Test whether the input descriptor control word can restore the original state |
| D | SetFileSecurityW | Legacy DACL write with AUTO_INHERIT_REQ set | Isolate the effect of the auto-inheritance request bit |

SetFileSecurityW is obsolete. Microsoft explicitly recommends SetNamedSecurityInfo instead. It remains in this experiment only as a bounded compatibility probe and is not proposed for production use. [Microsoft documentation](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setfilesecurityw).

## 3. Per-Candidate Procedure

1. Create a unique temporary directory on NTFS.
2. Create one new file with an explicit non-NULL protected DACL.
3. Retain the original file handle; reject directory and reparse-point targets.
4. Capture S0 from that handle using identity-before/read/identity-after checks.
5. Verify the immutable snapshot digest before any mutation.
6. Apply the same controlled SetSecurityInfo DACL write to create S1.
7. Apply exactly one allowlisted restore candidate.
8. Read S2 independently through the retained handle.
9. Verify target identity and compare S2 to S0 with STRICT_DESCRIPTOR_EQUALITY.
10. Close the owned handle and remove the exact temporary file and directory.

Every candidate uses its own new object. No candidate inherits state from a prior candidate.

## 4. Hosted Windows NTFS Evidence

Candidate-matrix evidence: Cross-platform Recovery Acceptance run `43639897237`, Windows job `132584952391`, commit `7fefb06fa4222e5b2188913b543572a115859e8a`.  
CI-isolation baseline: `f19541673ef1af02a3560a04fbcd6303f0e5e950`.  
CI-guard hardening head: `2d1e31fce46efec34075ec0047d7019f7578cfd2` (recognizes `1`, `true`, and `yes`, case-insensitively, in either `CI` or `GITHUB_ACTIONS).

All four candidate calls returned success, all four independent read-backs completed, and cleanup was verified. Results:

| Candidate | API result | S0 | S1 | S2 | Strict result | DACL bytes / inherited ACEs |
|---|---:|---:|---:|---:|---|---|
| A — SetSecurityInfo UNPROTECTED | 0 (success) | 0x9004 | 0x9404 | 0x8404 | RESTORE_NOT_EXACT | S2 differs; 3 inherited ACEs |
| B — SetNamedSecurityInfoW UNPROTECTED | 0 (success) | 0x9004 | 0x9404 | 0x8404 | RESTORE_NOT_EXACT | S2 differs; 3 inherited ACEs |
| C — SetFileSecurityW original control | 1 (nonzero success) | 0x9004 | 0x9404 | 0x9004 | RESTORED_EXACT | S2 DACL bytes equal S0; 0 inherited ACEs |
| D — SetFileSecurityW AUTO_INHERIT_REQ | 1 (nonzero success) | 0x9004 | 0x9404 | 0x9004 | RESTORED_EXACT | S2 DACL bytes equal S0; 0 inherited ACEs |

For candidates C and D, the complete S2 snapshot matched S0 under STRICT_DESCRIPTOR_EQUALITY, including the readable control word and exact DACL bytes. For A and B, the APIs returned success but the OS read-back did not match S0: DACL content changed and three inherited ACEs appeared. This confirms why API return success alone is not restoration success.

The SetFileSecurityW result is a **promising host-specific experimental finding**, not a production recommendation or universal Windows guarantee. It is an obsolete API; further local Windows 11 and supported-build testing, independent review, and an explicit authorization gate are required before any design decision.

## 5. Evidence Fields

Each result records:

- Candidate API name and native return value.
- Transaction UUID and SHA-256 snapshot digest.
- Target volume serial and 128-bit file identity.
- S0, S1, and S2 control words.
- S0, S1, and S2 exact DACL bytes.
- Inherited ACE counts.
- API and read-back errors.
- Strict comparison result and mismatch dimensions.
- Cleanup verification.

## 6. Safety and Non-Regression

- No caller-supplied path is accepted.
- No production object is opened or modified.
- No SACL, owner, or group write is attempted.
- No privilege is enabled or expanded.
- No undocumented native API is used.
- No candidate is silently retried through a different API.
- The four existing DACL Comparison Profiles remain unchanged.
- Existing SetSecurityInfo strict round-trip failure remains visible.
- Native Writer and Transactional ACL Mutation remain BLOCKED.
- No merge, deployment, or production enablement is authorized.

## 7. API Documentation

- [SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo)
- [SetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow)
- [SetFileSecurityW](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setfilesecurityw) — documented as obsolete; nonzero return means the call succeeded.
- [SetSecurityDescriptorControl](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setsecuritydescriptorcontrol)
- [SECURITY_DESCRIPTOR_CONTROL](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control)

## 8. Acceptance and Remaining Work

A candidate is experimentally capable for this tested scenario only if its API call succeeds, target identity remains unchanged, independent S2 is structurally valid, STRICT_DESCRIPTOR_EQUALITY reports RESTORED_EXACT against immutable S0, and cleanup is verified.

- Hosted Windows candidate matrix: all four candidates exercised; C and D restored exactly, A and B did not.
- Ubuntu candidate matrix: contract path passed; native Windows API calls are not exercised on Linux.
- Historical pre-isolation run: **FAIL** at the independent `test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file` assertion; retain that result as historical evidence.
- Current exact-head CI at `f19541673ef1af02a3560a04fbcd6303f0e5e950`: Cross-platform Recovery Acceptance, Local-first Minimal Emulator, and Validate Control Plane all **SUCCESS**. The named false-state real-host test is skipped by its local-only guard; the other tests in that module still execute. The TRUE-state setup test separately reports `NOT_EXERCISED` because hosted NTFS did not preserve `DaclDefaulted=TRUE` at creation.
- The ambiguous-write test continues to report `outcome=FAIL`, `RESTORE_NOT_EXACT`, and `control_flags_mismatch`; the unittest validates that this failure is surfaced and cleanup is verified.
- Local Windows 11 acceptance: **NOT RUN**; native rollback success is not claimed.  
- The hardened guard commit was pushed after the successful baseline; a fresh workflow run for that exact head had not appeared when this checkpoint was updated.
- Native Writer and Transactional ACL Mutation: **BLOCKED**.

A result on one hosted Windows NTFS environment is not universal support evidence. Production use requires local Windows 11 acceptance, additional supported-build coverage, code review, security review, and separate authorization. Until then, keep Native Writer and Transactional ACL Mutation BLOCKED.

## 9. Reconciliation and strengthened acceptance — 2026-11-16

The restore-API candidate matrix has been rebased onto the current PSEC stack. The test now asserts the exact hosted Windows NTFS observations rather than accepting either strict result:

| Candidate | Expected API result | Expected S2 | Expected strict result |
|---|---:|---:|---|
| SetSecurityInfo + UNPROTECTED | 0 | 0x8404, 3 inherited ACEs | RESTORE_NOT_EXACT |
| SetNamedSecurityInfoW + UNPROTECTED | 0 | 0x8404, 3 inherited ACEs | RESTORE_NOT_EXACT |
| SetFileSecurityW + original control | 1 | 0x9004, 0 inherited ACEs | RESTORED_EXACT |
| SetFileSecurityW + AUTO_INHERIT_REQ | 1 | 0x9004, 0 inherited ACEs | RESTORED_EXACT |

The test also asserts S0=0x9004, S1=0x9404, unique transaction IDs and file identities, no API/read-back error, exact cleanup, and candidate-specific S0/S2 DACL byte equality. A different result on a future Windows runner is a CI failure requiring review, not a silent pass.

For path-based candidates B/C/D, the harness verifies the generated path is not a reparse point immediately before and after the call using `GetFileAttributesW`, while independently checking the retained target handle identity before and after S1/S2. The target lives in a unique harness-owned temporary directory and no caller-supplied path is accepted. A second identity-pin handle cannot be opened after the experiment applies an empty DACL (Windows returns access denied), so this harness does NOT claim to prevent same-user path replacement. This limitation is another reason the name-based candidates remain experimental only.

The dedicated Windows NTFS job uses `DCP_RUN_WINDOWS_PSEC_CI=1` for the FALSE-state experiment. The test no longer depends on the user's PC being on. The TRUE input-descriptor test is separate; TRUE object read-back remains NOT EXERCISED when NTFS does not retain TRUE.

`SetFileSecurityW` remains obsolete and compatibility-only. Even the exact S2 result is a host-specific experimental finding, not production authorization. Native Writer and production ACL mutation remain BLOCKED.

## 10. Final hosted Windows validation — 2026-11-16

Exact head `0cbaa2d11aa038f7eba4271f2529f31458c0a2eb` passed all required workflows: Cross-platform Recovery Acceptance, Local-first Minimal Emulator and Validate Control Plane. On Windows Server 2025 / NTFS, the four candidate matrix tests ran and passed with the asserted S0/S1/S2 results; Linux correctly did not execute native Windows calls. The dedicated FALSE DACL round-trip ran under `DCP_RUN_WINDOWS_PSEC_CI=1`. The TRUE object-persistence probe remained NOT EXERCISED and was not counted as PASS.

The initial secondary path-pin handle attempt failed with WinError 5 because the deliberately empty DACL denied a second open. That approach was removed. The final implementation checks for reparse points before/after name-based calls and verifies S1/S2 identity through the retained handle; it does not claim same-user path-replacement prevention.
