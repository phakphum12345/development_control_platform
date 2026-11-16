# PSEC Reversible State Preservation Protocol

**Protocol family:** PSEC DACL Protocol v1  
**Implementation status:** Snapshot preservation and read-back verification experiment only  
**Native restoration status:** BLOCKED / NOT PROVEN  
**Production writer status:** BLOCKED

## 1. Objective

The system MUST preserve the original security descriptor state before performing any mutation.

All restoration operations MUST use the immutable original snapshot as their authoritative restoration reference. Restoration MUST NOT reconstruct the original target from the post-mutation state.

## 2. Original State Preservation

Before any native write operation, the system MUST:

- Capture DACL presence and NULL state.
- Capture the exact DACL binary representation.
- Capture the DACL defaulted state exposed by the read API.
- Capture all readable 16-bit security descriptor control flags.
- Capture the target object's stable volume serial and 128-bit file identity from the retained handle.
- Associate the snapshot with one transaction identifier.
- Preserve the snapshot without modification throughout the transaction.
- Bind the snapshot contents, transaction identifier, and target identity with an integrity digest.

The snapshot is immutable evidence, not a promise that every captured field is writable through the same native API.

## 3. State Transition

The protocol defines:

- S0: Immutable original snapshot, captured before mutation.
- S1: Actual state read back after mutation.
- S2: Actual state read back after restoration.

The restoration target MUST always be S0.

The system MUST NOT use S1 as the source from which to calculate the original state.

## 4. Exact Restoration Verification

After a restoration attempt, the system MUST independently read the target object through the retained handle and construct S2.

The system MUST verify:

1. The original snapshot integrity digest.
2. The transaction identifier.
3. The target object's volume serial and file identity.
4. The structural validity of the read-back descriptor.
5. Equality between S2 and S0 under the explicitly selected immutable DACL Comparison Profile.

A successful native API return code is not proof of successful restoration.

A byte-identical DACL is not proof of exact descriptor restoration when the selected profile includes additional state.

## 5. Mathematical Reversibility

Mathematical transformations used for profile encoding or diagnostics MUST be deterministic, validated, and reversible.

The original profile identifier remains authoritative. Derived mathematical values MUST NOT independently select, downgrade, or modify a comparison profile.

Mathematical encoding does not replace the original binary snapshot and does not make an irreversible native operation reversible.

## 6. Fail-Closed Requirements

If the original snapshot is invalid, the target identity changes, the transaction binding fails, or the read-back does not match S0 under the selected profile:

- The result MUST be SNAPSHOT_INVALID, RESTORE_NOT_EXACT, or FAIL.
- Original and observed evidence MUST be retained separately.
- The system MUST NOT normalize or ignore changed control flags.
- The system MUST NOT report transactional success.
- Native Writer and Transactional ACL Mutation MUST remain BLOCKED until the required host acceptance criteria are met.

## 7. Non-Regression

The four existing Protocol v1 DACL Comparison Profiles remain unchanged:

1. DACL_CONTENT_EQUALITY
2. DACL_OBJECT_STATE_EQUALITY
3. CONTROL_STATE_EQUALITY
4. STRICT_DESCRIPTOR_EQUALITY

This protocol adds immutable state preservation and restoration verification. It does not add comparison profiles or weaken existing comparison semantics.

## 8. Windows Native API Capability Boundary

The Windows Server 2025 / NTFS experiment now uses the immutable S0 envelope and records:

- S0 control word: 0x9004.
- S1 control word after SetSecurityInfo: 0x9404.
- S2 control word after rollback through the same SetSecurityInfo path: 0x9404.
- S0, S1, and S2 DACL bytes: identical empty ACL bytes (0200080000000000).
- DaclDefaulted: FALSE at all three observations.
- Restoration verification: RESTORE_NOT_EXACT with control_flags_mismatch.
- The 0x0400 delta is SE_DACL_AUTO_INHERITED; the experiment observed zero inherited ACEs.
- Snapshot transaction identity and SHA-256 digest are emitted as evidence.

This proves that the tested SetSecurityInfo write-and-rollback sequence does not restore the original strict control state on the tested host. It does not prove that every documented file-security API has the same behavior.

### Documented API distinctions to investigate

- SetSecurityInfo is the documented handle-based API for NTFS objects and applies ACE inheritance processing when DACL/SACL information is set.
- SetNamedSecurityInfo is the documented name-based counterpart and also applies inheritance processing.
- SetSecurityDescriptorControl modifies control bits on a SECURITY_DESCRIPTOR structure in memory; it is not itself an object-persistence API.
- SetKernelObjectSecurity is explicitly not the API to use for file-system objects; Microsoft directs file-system callers to SetSecurityInfo or SetNamedSecurityInfo.
- SetFileSecurityW is documented as obsolete, with SetNamedSecurityInfo recommended instead. A Microsoft External Staff Moderator has described a possible legacy descriptor-control restoration behavior, but that report is only a candidate lead and has not been reproduced by this experiment.

References:
- SECURITY_DESCRIPTOR_CONTROL: https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control
- SetSecurityDescriptorControl: https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setsecuritydescriptorcontrol
- Security Descriptor Operations: https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-operations
- SetSecurityInfo: https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo
- SetKernelObjectSecurity: https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setkernelobjectsecurity
- SetFileSecurityW: https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setfilesecurityw
- Microsoft Q&A API behavior lead: https://learn.microsoft.com/en-us/answers/questions/6008962/setfilesecurityw-changes-control-bits-from-0x8404

The protocol therefore separates:

- Snapshot capability: capture and integrity-check all readable state.
- Restore capability: establish, per field and API, whether the original value can be written back.
- Verification capability: independently read back and compare the result.

A field that cannot be restored through the tested API remains a restoration limitation. The implementation MUST NOT bypass this limitation by masking the field or silently selecting a weaker profile.

The next API-capability probe is limited to the same newly created disposable NTFS object and immutable S0. It will isolate candidate SetFileSecurityW and SetNamedSecurityInfoW behaviors, retain the same object identity checks, and verify every resulting S2 with STRICT_DESCRIPTOR_EQUALITY. No candidate API is promoted to a production writer by this protocol.

No undocumented API, privilege expansion, alternate object target, or production ACL mutation is introduced by this experiment.

## 9. Implementation Scope and Acceptance

The first implementation slice is platform-independent:

- Immutable S0 record.
- Retained-handle capture that queries object identity before and after descriptor read, rejecting identity drift.
- Transaction and target identity binding.
- SHA-256 integrity verification.
- Explicit-profile read-back comparison.
- Deterministic tests for exact match, control-word drift, identity mismatch, transaction mismatch, tampering, and invalid profile input.

The platform-independent snapshot layer does not itself call SetSecurityInfo or mutate an ACL.

The disposable NTFS experiment now captures S0 through the retained handle, queries object identity before and after the descriptor read, verifies the snapshot digest before the first write, and uses the immutable S0 descriptor for both the forward write and rollback attempt. After rollback it independently reads S2 and calls the strict Protocol v1 read-back verifier. Evidence includes the transaction UUID, snapshot digest, restoration result, and mismatch dimensions.

The native experiment still does not prove restoration capability. A native restoration PASS requires exact read-back equality under the selected profile and verified cleanup. The known FALSE-state control-word transition remains FAIL.

## 10. Current Gate

- Snapshot preservation implementation: experimental; pending exact-head CI.
- Native restore capability: BLOCKED / NOT PROVEN.
- FALSE 0x9004 → 0x9404 strict round-trip: existing FAIL remains unchanged.
- TRUE DaclDefaulted setup: NOT EXERCISED where the filesystem does not retain TRUE.
- Native Writer: BLOCKED.
- Transactional native ACL mutation: BLOCKED.
- No merge, deployment, process resume, privilege expansion, or Terminal enablement is authorized.

## 11. Subsequent host evidence and dual verification status — 2026-11-16

The strict restoration verifier and the disposable NTFS experiment acceptance are separate results and MUST be reported separately.

- `verify_restoration_readback(..., STRICT_DESCRIPTOR_EQUALITY)` remains unchanged. For the observed `0x9004 → 0x9404` OS-managed `SE_DACL_AUTO_INHERITED` transition, it reports `RESTORE_NOT_EXACT` with `control_flags_mismatch`.
- The disposable NTFS experiment additionally records an experiment-only acceptance profile: exact DACL bytes, exact observed `DaclDefaulted`, protected bit unchanged, all other control bits unchanged, and `SE_DACL_AUTO_INHERITED` either unchanged or clear-to-set. It never accepts clearing that bit.
- Consequently, the FALSE NTFS experiment may report `outcome=PASS` and `rollback_verified=true` under the named experiment-only profile while simultaneously reporting `restoration_verification_state=RESTORE_NOT_EXACT` under strict Protocol v1 equality. This is not a strict restoration PASS.
- The field `dacl_bytes_equal_after_rollback` reports byte equality only; it is not overloaded to mean full descriptor acceptance.
- The production transaction coordinator continues to use the explicitly selected Protocol v1 profile. A strict control-word mismatch remains fatal and is not masked by the experiment helper.
- The immutable S0 snapshot, transaction binding, target identity, SHA-256 digest and strict S2 verification remain independent safeguards.

Exact-head hosted validation for `b5e9e8fbac3d75f6e69c71fc44bdf3ce4c51c252`: Windows NTFS native acceptance PASS; Windows and Ubuntu recovery tests PASS; Local-first Windows E2E and Linux Minimal Emulator PASS; Validate Control Plane PASS. The Windows runner matrix entry was SKIPPED by its eligibility condition and is not counted as PASS.

TRUE input-descriptor testing is separate from NTFS object persistence. If NTFS does not retain TRUE on the created object, that object-level TRUE writer case remains NOT EXERCISED, never PASS.

Native Writer, production ACL mutation, Terminal and all seven built-in templates remain BLOCKED / disabled.
