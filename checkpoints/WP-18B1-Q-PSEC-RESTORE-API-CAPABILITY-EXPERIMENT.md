# WP-18B1-Q — PSEC Restore API Capability Experiment

**Status:** HOSTED WINDOWS NTFS MATRIX COMPLETE — LOCAL HOST ACCEPTANCE PENDING  
**Branch:** work/wp18b1q-psec-restore-api-capability-experiment  
**Base:** WP-18B1-P / PR #136 head d3f7e62fc9992474f42ddf475ab39fa751a59bbd  
**PR:** https://github.com/phakphum12345/development_control_platform/pull/137  
**Exact tested head:** 7fefb06fa4222e5b2188913b543572a115859e8a

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
- Cross-platform Recovery Acceptance overall: **FAIL**, due the independent existing `test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file` assertion. Preserve this failure; do not weaken strict comparison.
- Local unittest on user's machine: NOT RUN.
- Local Windows 11 acceptance: NOT RUN.

## Next gates

1. Inspect and validate temp-root selection and disk-space behavior before asking for a local run; prefer D: because C: has very little free space.
2. Run only the harness-owned disposable NTFS experiment on the user's Windows 11 host, without elevation unless a specific access error proves it necessary.
3. Compare complete JSON evidence and verify cleanup.
4. Review the legacy API finding, supported-build coverage, and security implications.
5. Keep Native Writer and Transactional ACL Mutation BLOCKED pending independent review and explicit authorization.

No merge, deployment, production enablement, privilege expansion, or real-file ACL testing is authorized.
