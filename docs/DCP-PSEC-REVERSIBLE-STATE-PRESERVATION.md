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

The existing Windows Server 2025 / NTFS experiment observed:

- Original control word: 0x9004.
- After the first SetSecurityInfo call: 0x9404.
- After the rollback write: 0x9404.
- DACL bytes and observed DaclDefaulted=FALSE remained unchanged in this later probe.
- The 0x0400 delta is SE_DACL_AUTO_INHERITED; the experiment observed zero inherited ACEs.

This is evidence that the currently tested SetSecurityInfo DACL write path did not restore the original control word on that host. It is not proof that every Windows version or every supported API behaves identically.

The protocol therefore separates:

- Snapshot capability: capture and integrity-check all readable state.
- Restore capability: establish, per field and API, whether the original value can be written back.
- Verification capability: independently read back and compare the result.

A field that cannot be restored through the tested API remains a restoration limitation. The implementation MUST NOT bypass this limitation by masking the field or silently selecting a weaker profile.

No undocumented API, privilege expansion, alternate object target, or production ACL mutation is introduced by this experiment.

## 9. Implementation Scope and Acceptance

The first implementation slice is platform-independent:

- Immutable S0 record.
- Retained-handle capture that queries object identity before and after descriptor read, rejecting identity drift.
- Transaction and target identity binding.
- SHA-256 integrity verification.
- Explicit-profile read-back comparison.
- Deterministic tests for exact match, control-word drift, identity mismatch, transaction mismatch, tampering, and invalid profile input.

This slice does not call SetSecurityInfo, mutate an ACL, or claim native restoration capability.

The next native experiment must use only a newly created disposable NTFS object and a retained handle. It must record S0, S1, every restoration attempt, and S2 independently. The experiment must isolate each candidate native API and control-bit behavior. A native restoration PASS requires exact read-back equality under the selected profile and verified cleanup.

## 10. Current Gate

- Snapshot preservation implementation: experimental; pending exact-head CI.
- Native restore capability: BLOCKED / NOT PROVEN.
- FALSE 0x9004 → 0x9404 strict round-trip: existing FAIL remains unchanged.
- TRUE DaclDefaulted setup: NOT EXERCISED where the filesystem does not retain TRUE.
- Native Writer: BLOCKED.
- Transactional native ACL mutation: BLOCKED.
- No merge, deployment, process resume, privilege expansion, or Terminal enablement is authorized.
