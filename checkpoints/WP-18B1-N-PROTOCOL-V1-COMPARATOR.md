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
