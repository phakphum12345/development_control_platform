# PSEC DACL Protocol v1.0 — Consumer Conformance Audit

**Status:** DRAFT / REVIEW REQUIRED  
**Work package:** WP-18B.1-M — Protocol consumer mapping  
**Parent:** PR #132, Protocol v1.0  
**Evidence baseline:** PR #131 head `cf5e43aec6b6f7e72fc20b3c41fa052d585ff7e9`  
**Scope:** Read-only audit of the existing Reader and Transaction coordinator contracts. No native writer implementation or ACL mutation is introduced.

## 1. Purpose

Map the normative comparison profiles in `DCP-PSEC-DACL-STATE-PROTOCOL-v1.md` to the existing PR #130 Reader/Transaction code. Identify implicit comparisons and state fields that need explicit policy before a future writer can be implemented.

This audit does not change PR #130, PR #131, or the Protocol v1.0 source document. It is a separate child work package so the findings can be reviewed without rewriting the original evidence.

## 2. Source baseline inspected

| Component | Source | Current behavior observed |
|---|---|---|
| Reader | `tools/local_runner_agent/windows_psec_security_descriptor_reader.py` | Reads through the retained handle using `GetSecurityInfo`; captures DACL presence, NULL state, bytes, `dacl_defaulted`, and control flags. |
| Snapshot | `DescriptorSnapshot` in `windows_psec_security_descriptor_transaction.py` | Stores content, object-readable defaulted output, and raw control flags in one immutable value. |
| Candidate | `DescriptorCandidate` in the same module | Carries the defaulted boolean and control flags into the planned candidate. |
| Apply verification | `NativeSecurityDescriptorTransaction.apply` | Uses dataclass equality for current-vs-preflight and read-back-vs-candidate checks. The selected comparison profile is implicit. |
| Rollback verification | Same coordinator | Uses dataclass equality between restored snapshot and original snapshot. The selected profile is implicit. |

## 3. Protocol profile mapping

| Protocol v1 profile | Required fields | Current PR #130 mapping | Audit disposition |
|---|---|---|---|
| `DACL_CONTENT_EQUALITY` | DACL-present, NULL-vs-non-NULL, complete ACL bytes | Fields exist, but no named comparator exists. | NOT IMPLEMENTED as an explicit profile. |
| `DACL_OBJECT_STATE_EQUALITY` | Content plus object-readable `dacl_defaulted` | Fields exist in snapshot/candidate; dataclass equality includes them. | IMPLICIT ONLY; must be named and tested. |
| `CONTROL_STATE_EQUALITY` | Complete raw control word and decoded bits | Raw `dacl_control_flags` is retained; no profile-specific comparison exists. | NOT IMPLEMENTED as an explicit profile. |
| `STRICT_DESCRIPTOR_EQUALITY` | Content, object-readable metadata, complete raw control word | Whole-dataclass equality currently compares these fields and additional structural metadata. | IMPLICIT STRICT-LIKE behavior; not declared by the caller. |

## 4. Required contract corrections before a future writer

1. Every operation that verifies a descriptor MUST declare a comparison profile before mutation. A generic dataclass equality expression is not an adequate policy declaration.
2. The raw 16-bit control word MUST remain available in snapshots and evidence. No comparator may mask `SE_DACL_AUTO_INHERITED`, `SE_DACL_PROTECTED`, or other bits to manufacture equality.
3. Construction metadata `dacl_defaulted` MUST remain preserved as observed metadata. It MUST NOT be treated as proof that the marker is physically persisted on a securable object.
4. A future native `SetSecurityInfo` adapter MUST fail closed before the first write if its declared postcondition requires restoring a construction marker that the object API cannot represent or restore. The exact preflight predicate and result state must be separately specified and tested.
5. The coordinator MUST distinguish a profile comparison from structural validation. ACL bounds, supported revision, object identity, and resource ceilings remain mandatory regardless of the selected comparison profile.
6. Rollback acceptance MUST use the operation's declared profile. If the operation requires strict equality, a content-only or object-state-only match cannot be reported as verified rollback.
7. A less strict profile MUST NOT be selected implicitly, used as a runtime fallback, or used to convert an existing strict failure into PASS.

## 5. Proposed conformance test matrix

The implementation follow-up should add deterministic unit tests using synthetic snapshots. These tests do not call native APIs and do not authorize host mutation.

| Test | Expected result |
|---|---|
| Same DACL presence/null semantics and bytes; different control word | Content profile PASS; control and strict profiles FAIL |
| Same content and control word; different object-readable defaulted value | Content profile PASS; object-state and strict profiles FAIL |
| Different DACL bytes; same defaulted/control metadata | All profiles that include content FAIL |
| Identical full snapshot | All four profiles PASS |
| NULL DACL versus empty non-NULL DACL | Content and all broader profiles FAIL |
| Change only an unrelated descriptor/ACL structural field | Structural validation/comparison policy must be explicit; no silent omission |
| Missing/unknown profile | Reject before any adapter write |
| Strict profile with control transition `0x9004 → 0x9404` | FAIL; no downgrade |
| Failed apply followed by rollback with control transition | `ROLLBACK_INCOMPLETE_BLOCKED` under strict profile |

## 6. Evidence interpretation retained

The PR #131 Windows Server 2025 / NTFS observation remains:

- DACL bytes unchanged.
- Object-readable `DACL_DEFAULTED` remained FALSE.
- Inherited ACE count remained zero.
- Raw control word changed from `0x9004` to `0x9404`.
- `CONTROL_STATE_EQUALITY` and `STRICT_DESCRIPTOR_EQUALITY` remain FAIL for that observed transition.
- The original `test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file` assertion remains unchanged and failing.

A successful content comparison is not an overall writer acceptance result. The evidence remains scoped to the observed Windows Server 2025 / NTFS environment.

## 7. Safety and implementation boundary

- PR #130 and PR #131 are not modified by this audit.
- No production Native Writer, transaction mutation adapter, Launcher integration, process resume, or Terminal enablement is introduced.
- No existing Workspace, Scratch, profile, system, repository, or user object may be used for native mutation experiments.
- Native Writer, Terminal, and all seven built-in templates remain BLOCKED / disabled.
- PR #132 remains the normative Protocol v1.0 document and is not silently amended by this consumer audit.
- This audit does not authorize merge or deployment.

## 8. Acceptance checklist

- [ ] Review the source-to-profile mapping.
- [ ] Confirm the current dataclass equality is documented as implicit strict-like behavior, not an explicit policy contract.
- [ ] Approve the proposed comparison API and missing-profile behavior.
- [ ] Approve the rule for object-readable `dacl_defaulted` and native preflight rejection.
- [ ] Implement the comparator and tests in a separate reviewed code PR.
- [ ] Run exact-head CI; Windows native acceptance remains a separate gate.
- [ ] Obtain security review before any production mutation behavior changes.

**Disposition:** Consumer conformance is PARTIAL / REVIEW REQUIRED. The next code change must be a separately reviewed, non-native comparator/test slice. Native Writer remains BLOCKED.
