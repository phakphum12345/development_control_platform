# WP-18B1-Q — PSEC Restore API Capability Experiment

**Status:** HOSTED WINDOWS NTFS MATRIX COMPLETE — CI ISOLATION VERIFIED — LOCAL HOST ACCEPTANCE PENDING  
**Branch:** work/wp18b1q-psec-restore-api-capability-experiment  
**Base:** WP-18B1-P / PR #136 head d3f7e62fc9992474f42ddf475ab39fa751a59bbd  
**PR:** https://github.com/phakphum12345/development_control_platform/pull/137  
**Candidate-matrix evidence head:** 7fefb06fa4222e5b2188913b543572a115859e8a  
**CI isolation baseline:** f19541673ef1af02a3560a04fbcd6303f0e5e950  
**CI guard hardening head:** 2d1e31fce46efec34075ec0047d7019f7578cfd2

## Objective

Test whether alternate documented Windows file-security APIs can restore S0 after a SetSecurityInfo DACL write changes the control word.

## Exact-head hosted Windows evidence

Run: Cross-platform Recovery Acceptance `43639897237`  
Windows job: `132584952391`

Four candidates each used a fresh disposable NTFS file, immutable S0, controlled S1 mutation, one restore attempt, independent S2 read-back, strict comparison, and verified cleanup.

| Candidate | API return | S0 → S1 → S2 | Strict result |
|---|---:|---|---|
| SetSecurityInfo + UNPROTECTED | 0 | 0x9004 → 0x9404 → 0x8404 | RESTORE_NOT_EXACT; 3 inherited ACEs |
| SetNamedSecurityInfoW + UNPROTECTED | 0 | 0x9004 → 0x9404 → 0x8404 | RESTORE_NOT_EXACT; 3 inherited ACEs |
| SetFileSecurityW + original control | 1 (BOOL nonzero) | 0x9004 → 0x9404 → 0x9004 | RESTORED_EXACT |
| SetFileSecurityW + AUTO_INHERIT_REQ | 1 (BOOL nonzero) | 0x9004 → 0x9404 → 0x9004 | RESTORED_EXACT |

For candidates C and D, S2 DACL bytes equal S0 and strict verification reports no mismatch. For A and B, S2 contains three inherited ACEs and differs from S0 even though the API returned success.

SetFileSecurityW is obsolete and remains a compatibility-only experimental lead. This single hosted environment does not authorize production use.

## Validation status

- Windows PSEC reversible snapshot/comparison regression step: PASS.
- Windows restore API candidate matrix: PASS as an evidence-producing test; candidates A/B are RESTORE_NOT_EXACT and C/D are RESTORED_EXACT.
- Ubuntu PSEC regression and candidate-matrix contract step: PASS; native Windows calls are not run on Linux.
- Local-first Minimal Emulator: PASS.
- Validate Control Plane: PASS.
- Historical pre-isolation run at the earlier head: **FAIL** at `test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file`; retain this as historical evidence.  
- Current exact-head CI at `f19541673ef1af02a3560a04fbcd6303f0e5e950`: Cross-platform Recovery Acceptance, Local-first Minimal Emulator, and Validate Control Plane all **SUCCESS**. The named false-state real-host test is the only test skipped by the new local-only guard. The guard now recognizes common truthy values (`1`, `true`, `yes`, case-insensitively) in either `CI` or `GITHUB_ACTIONS`. The TRUE-state test separately reports `NOT_EXERCISED` because hosted NTFS did not retain `DaclDefaulted=TRUE` at creation; this is a setup limitation, not a pass.  
- The ambiguous-write test still records `outcome=FAIL`, `RESTORE_NOT_EXACT`, and `control_flags_mismatch`; its test passes because it verifies that failure is surfaced and cleanup occurs.  
- Local Windows 11 acceptance remains **NOT RUN**; no claim of native rollback success is made.  
- The CI-guard hardening commit `2d1e31fce46efec34075ec0047d7019f7578cfd2` was pushed after the successful baseline; a fresh workflow run for this exact head has not yet appeared at checkpoint time.
- Local unittest on user's machine: NOT RUN.
- Local Windows 11 acceptance: NOT RUN.

## Next gates

1. Continue hosted CI and source-level audit for all non-local-only tests; do not skip or weaken any other test to obtain a green workflow.
2. Keep `test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file` guarded for local Windows only until the user is ready to run it.
3. When the user's Windows 11 PC is available, inspect temp-root selection and disk-space behavior first; prefer D: because C: has very little free space.
4. Run only the harness-owned disposable NTFS experiment, without elevation unless a specific access error proves it necessary.
5. Compare complete JSON evidence and verify cleanup.
6. Review the legacy API finding, supported-build coverage, and security implications.
7. Keep Native Writer and Transactional ACL Mutation BLOCKED pending independent review and explicit authorization.

No merge, deployment, production enablement, privilege expansion, or real-file ACL testing is authorized.

## 2026-11-16 — Reconciliation and strengthened candidate gates

- Rebased onto current PR #136 head `c89da8337213da09086c83c0a4dff629921254eb`; exact new head is pending CI.
- The Windows matrix test now asserts the known candidate-specific outcomes: A/B return 0 but end RESTORE_NOT_EXACT at S2=0x8404 with three inherited ACEs; C/D return nonzero success and RESTORED_EXACT at S2=0x9004 with zero inherited ACEs.
- Every candidate must preserve the same retained target identity, produce unique transaction/file identities, return no API/read-back error, and verify cleanup.
- Name-based candidates B/C/D now pin the path with a second handle opened using OPEN_REPARSE_POINT and no FILE_SHARE_DELETE, then compare the pinned identity to the retained target. Candidate A remains handle-based.
- The obsolete SetFileSecurityW candidate remains experimental only; no production recommendation or writer enablement.
- The dedicated Windows NTFS job now runs the FALSE-state round-trip with `DCP_RUN_WINDOWS_PSEC_CI=1`, independent of the user's local PC.
- TRUE object persistence remains NOT EXERCISED if NTFS does not retain TRUE at creation.
- Native Writer, transactional production ACL mutation, Terminal and all templates remain BLOCKED.
