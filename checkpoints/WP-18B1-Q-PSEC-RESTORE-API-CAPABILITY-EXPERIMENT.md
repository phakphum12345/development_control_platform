# WP-18B1-Q — PSEC Restore API Capability Experiment

**Status:** EXPERIMENT CREATED — EXACT-HEAD CI PENDING  
**Branch:** work/wp18b1q-psec-restore-api-capability-experiment  
**Base:** WP-18B1-P / PR #136 head d3f7e62fc9992474f42ddf475ab39fa751a59bbd  
**PR:** not created at checkpoint authoring time

## Objective

Test whether alternate documented Windows file-security APIs can restore S0 after a SetSecurityInfo DACL write changes the control word.

## Scope

- Four allowlisted candidate restore operations.
- A fresh disposable NTFS object per candidate.
- Immutable S0 capture from a retained handle.
- One controlled SetSecurityInfo forward mutation to S1.
- One candidate restore attempt.
- Independent S2 read-back and STRICT_DESCRIPTOR_EQUALITY verification.
- Stable target identity and cleanup checks.
- Evidence includes transaction ID, SHA-256 snapshot digest, control flags, DACL bytes, API return/error, mismatch dimensions, and cleanup.

## Candidate APIs

1. SetSecurityInfo with UNPROTECTED_DACL_SECURITY_INFORMATION.
2. SetNamedSecurityInfoW with UNPROTECTED_DACL_SECURITY_INFORMATION.
3. Obsolete SetFileSecurityW with the original protected control state in a self-relative descriptor.
4. SetFileSecurityW with SE_DACL_AUTO_INHERIT_REQ set, to isolate the request-bit effect.

SetFileSecurityW is a documented but obsolete API and is not proposed for production use. It is included only as an isolated compatibility probe.

## Validation

- Local unittest execution: NOT RUN.
- Exact-head CI: pending.
- Required test: python -m unittest tests.test_windows_psec_dacl_restore_api_experiment -v.
- Windows-only disposable NTFS matrix must record all four candidates.
- No candidate is considered successful without strict S2-to-S0 equality.

## Safety Gates

No SACL/owner/group writes, privilege enabling, undocumented APIs, caller-supplied paths, or production ACL targets. Native Writer and Transactional ACL Mutation remain BLOCKED. No merge, deployment, or production enablement is authorized.
