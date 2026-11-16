# WP-18B.1-N — Explicit DACL Comparison Profiles

**Date:** 2026-11-15  
**Repository:** `phakphum12345/development_control_platform`  
**Branch:** `work/wp18b1n-explicit-dacl-comparison-profiles`  
**Base:** PR #133 exact head `4b85276233f94264809a78395fe4d58c9f66e4fb`  
**Scope:** Pure comparator, required profile contract, deterministic tests; no native calls or ACL mutation.

## READ / ANALYZE

- Re-verified PR #130–#133 are OPEN / DRAFT / NOT MERGED.
- PR #133 exact-head-associated workflows completed: Local-first Minimal Emulator PASS; Validate Control Plane PASS; Cross-platform Recovery Acceptance FAIL on the preserved Windows strict FALSE round-trip assertion.
- Inspected the Windows job log: Windows Server 2025 build 10.0.26100, NTFS, control word `0x9004 → 0x9404`, unchanged DACL bytes, object-readable DACL_DEFAULTED FALSE, inherited ACE count zero.
- The strict assertion remains untouched. Evidence cases and test-runner totals are kept distinct.

## MODIFY

- Added `tools/local_runner_agent/windows_psec_dacl_comparison.py` with the four Protocol v1 profiles and no-fallback resolver.
- Integrated a required per-operation `comparison_profile` into `NativeSecurityDescriptorTransaction.apply`.
- Applied the selected profile consistently to pre-write drift, candidate read-back, and rollback verification.
- Added validation of read-back and restored snapshots before comparison.
- Updated existing transaction tests to declare strict equality explicitly.
- Added deterministic tests for all four profile dimensions, absent/NULL/empty distinction, missing/unknown profile rejection, and synthetic `0x9004 → 0x9404` behavior.
- No native API implementation, workflow edit, production ACL mutation, or PR #130–#133 edit.

## TEST

- Local execution: NOT RUN in this session.
- Exact-head CI: PENDING until the child Draft PR is opened and workflows finish.
- The test-only synthetic adapter is not evidence of Windows native behavior.

## AUDIT / SAFETY

- Native Writer: BLOCKED.
- Transactional native ACL mutation: BLOCKED.
- Terminal: BLOCKED.
- Seven built-in templates: DISABLED.
- PR #130–#133 remain unchanged and unmerged.
- No merge, deployment, process resume, or privilege expansion authorized.

## NEXT GATE

Review the profile semantics and exact-head CI. Do not proceed to a native writer until the profile contract, structural validation, and the non-persistent DACL_DEFAULTED handling have a separate security review.

## Exact-head audit update — 2026-11-15

**Audited PR #134 HEAD:** `f9f528d18cc8ab37c0dfa18acaff0d6b1bc4bd96`  
**PR:** https://github.com/phakphum12345/development_control_platform/pull/134  
**PR state:** OPEN / DRAFT / NOT MERGED. Base remains PR #133 head `4b85276233f94264809a78395fe4d58c9f66e4fb`.

### Exact-head workflow results

| Workflow / job | Result | Evidence |
|---|---|---|
| Local-first Minimal Emulator — Windows Auth Proxy + Gateway E2E | PASS | Run `43629906943`, job `132553985151` |
| Local-first Minimal Emulator — Linux Minimal Emulator | PASS | Run `43629906943`, job `132553985421`; 942 tests passed, 39 skipped |
| Cross-platform Recovery Acceptance — Ubuntu | PASS | Run `43629906933`, job `132553985403` |
| Cross-platform Recovery Acceptance — Windows | FAIL | Run `43629906933`, job `132553985595`; only the disposable NTFS DACL experiment step failed |
| Validate Control Plane — Windows dynamic-port launcher integration | PASS | Run `43629906929`, job `132553985420` |
| Validate Control Plane — validate | PASS | Run `43629906929`, job `132553985616` |
| Validate Control Plane — Windows runner acceptance | SKIPPED | Run `43629906929`, job `132553986503`; not counted as PASS |

The Linux Minimal Emulator log explicitly shows all 7 comparator tests and all 20 transaction tests passing, including missing/unknown profile rejection and strict control-transition rollback behavior.

### Preserved Windows Native API finding

The Windows recovery log records 8 experiment tests: 6 passed, 1 failed, 1 skipped. The sole failure remains `test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file`. Its evidence records `DaclDefaulted=false` before, after write, and after rollback; DACL bytes remain unchanged; raw control flags change `0x9004 → 0x9404`; inherited ACE count remains zero. The TRUE-state case is skipped because NTFS did not retain TRUE at creation.

This is the existing strict native round-trip failure, not a failure in the PR #134 pure comparator or deterministic transaction tests. No native experiment assertion, strict comparison, or CI gate was weakened.

### Audit disposition

- PR #134 comparator and transaction tests: exact-head Linux suite PASS (942 total tests, 39 skipped).
- Validate Control Plane: PASS.
- Windows Native API strict round-trip: FAIL, preserved as evidence.
- Native Writer and transactional native ACL mutation: BLOCKED.
- No code correction is justified by the current failure evidence; no source/test weakening performed.
- PR remains Draft and unmerged pending security review and disposition of the Windows native experiment gate.
