# DCP-PSEC DACL State Semantics Protocol v1.0

**Status:** DRAFT — architecture specification; not a production-writer authorization  
**Repository:** `phakphum12345/development_control_platform`  
**Evidence source:** PR #131, exact experiment head `cf5e43aec6b6f7e72fc20b3c41fa052d585ff7e9`  
**Stack:** This specification is a separate documentation-only child of PR #131.  
**Scope:** Windows security-descriptor DACL state classification, comparison, evidence and acceptance.

---

## 1. Purpose

Define unambiguous semantics for DACL state observed through Windows security-descriptor APIs. The protocol prevents three different kinds of state from being conflated:

1. DACL content attached to an object.
2. Descriptor-construction metadata such as `SE_DACL_DEFAULTED`.
3. OS-managed descriptor control state such as `SE_DACL_AUTO_INHERITED` and `SE_DACL_PROTECTED`.

This protocol is derived from the disposable NTFS experiment in PR #131. It does not reinterpret its failing assertion as a pass and does not authorize a production writer.

## 2. Normative state model

Every observation MUST preserve these fields independently.

### 2.1 DACL content state

Capture and compare:

- `dacl_present`;
- `dacl_is_null` (a NULL DACL is not an empty ACL);
- complete binary ACL bytes, including ACL header, revision, size, ACE count and ACE data;
- parsed ACE metadata only as an additional diagnostic, never as a replacement for byte evidence.

A content comparison MUST distinguish absent DACL, NULL DACL, and present non-NULL DACL. Byte equality is meaningful only when presence/null semantics also match.

### 2.2 Descriptor-construction metadata

Capture `dacl_defaulted` exactly as returned by the descriptor API and retain it in in-memory snapshots when the descriptor is in memory.

`SE_DACL_DEFAULTED` (`0x0008`) describes whether the DACL was supplied as a default DACL during descriptor construction. Microsoft documents that this bit is used when computing the final DACL and is not physically stored in the security descriptor control of a securable object.

Therefore:

- An in-memory descriptor construction test MAY assert the requested defaulted marker before object creation.
- A file-object read-back MUST report the value actually returned by the object security APIs; it MUST NOT claim that the original in-memory construction marker was persisted.
- A file-object write/rollback protocol MUST NOT require `SetSecurityInfo` to restore a construction marker that the object representation does not physically retain.
- A TRUE-state object round-trip is NOT EXERCISED when the object does not report TRUE immediately after creation. It is not a PASS and must not be manufactured by editing a post-creation in-memory copy.

### 2.3 OS-managed control state

Capture the complete raw control word and decode relevant bits independently, including:

- `SE_DACL_AUTO_INHERITED` (`0x0400`);
- `SE_DACL_DEFAULTED` (`0x0008`);
- `SE_DACL_PROTECTED` (`0x1000`).

The raw control word MUST be retained in evidence. The implementation MUST NOT silently normalize, mask, clear, or rewrite OS-managed bits merely to obtain equality.

`SE_DACL_AUTO_INHERITED` indicates automatic-inheritance state; it is not proof that any ACE has the `INHERITED_ACE` flag. The actual inherited ACE count and ACE flags MUST be recorded separately.

## 3. Comparison profiles

Comparison MUST name the profile being applied. A bare `equal` or `round_trip_pass` result is insufficient.

| Profile | Compared fields | Intended use |
|---|---|---|
| `DACL_CONTENT_EQUALITY` | Presence, NULL-vs-non-NULL, complete ACL bytes | Determine whether the DACL content is unchanged |
| `DACL_OBJECT_STATE_EQUALITY` | Content equality plus object-readable defaulted state | Compare the object state exposed by the same API |
| `CONTROL_STATE_EQUALITY` | Complete raw control word and decoded relevant bits | Detect all control-word transitions |
| `STRICT_DESCRIPTOR_EQUALITY` | Content, object-readable metadata, and complete raw control word | Exact descriptor-state contract where every bit is required to match |

Rules:

1. A content-equality result MUST NOT be promoted to strict descriptor equality.
2. A control-word transition MUST remain visible even if content equality passes.
3. A protocol consumer MUST declare which comparison profile its operation requires before mutation.
4. If a caller requires strict descriptor equality and the native API cannot restore it, the operation remains FAIL/BLOCKED. The implementation MUST NOT downgrade the profile at runtime.
5. The profile does not change the historical result of an existing test. Existing assertions remain intact until a separately reviewed test-contract change is approved.

## 4. Evidence classification

Each stage MUST be recorded separately:

- `AFTER_CREATE`;
- `AFTER_NATIVE_WRITE`;
- `AFTER_EACH_REPEATED_WRITE` (when applicable);
- `AFTER_ROLLBACK`;
- `AFTER_CLEANUP`.

For each stage record the object identity, volume/filesystem, API and flags, DACL content state, defaulted state, raw control word, decoded control bits, inherited ACE count, API errors, handle lifecycle and cleanup outcome.

The evidence record MUST distinguish:

- `PASS`: the declared comparison profile and lifecycle requirements are satisfied;
- `FAIL`: a declared requirement is violated;
- `SKIPPED`: the required state or platform setup was not exercised;
- `UNKNOWN`: evidence is incomplete;
- `IN_PROGRESS`: execution is still running.

A successful cleanup does not convert a failed write or rollback comparison into PASS. A test runner reporting a successful test process is not sufficient if the test output contains a failed experiment result.

## 5. PR #131 Windows Server 2025 / NTFS observation

The following is the recorded observation for the current experiment head; it is evidence for this runner and filesystem only, not a universal statement about all Windows versions or filesystems.

| Stage | Raw control word | DACL bytes | DACL_DEFAULTED | Inherited ACE count |
|---|---:|---|---|---:|
| After creation | `0x9004` | `0200080000000000` | FALSE | 0 |
| After SetSecurityInfo | `0x9404` | unchanged | FALSE | 0 |
| After rollback attempt | `0x9404` | unchanged | FALSE | 0 |

Observed delta: `0x0400` (`SE_DACL_AUTO_INHERITED`) was added after the native write and remained after rollback. The DACL bytes and object-readable FALSE state remained unchanged. The inherited ACE count remained zero.

Interpretation:

- `DACL_CONTENT_EQUALITY`: observed equal.
- `DACL_OBJECT_STATE_EQUALITY`: observed equal for the reported DACL content and FALSE marker.
- `CONTROL_STATE_EQUALITY`: FAIL; `0x9004 != 0x9404`.
- `STRICT_DESCRIPTOR_EQUALITY`: FAIL.
- The observation does not establish why Windows sets the auto-inherited bit internally, nor does it establish behavior on other filesystems/builds.
- The TRUE object-state case remains NOT EXERCISED when NTFS does not retain TRUE after creation.

The exact failing test `test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file` MUST remain visibly failing under its current strict contract. Do not change its expected outcome merely to make CI green.

## 6. Native API constraints

- Use the documented handle-based `SetSecurityInfo` API for file-system objects.
- Do not substitute undocumented calls, raw on-disk edits, or path-based mutation to bypass observed semantics.
- `SetSecurityInfo` has no `bDaclDefaulted` input parameter.
- `SetSecurityDescriptorDacl` can set the marker on an in-memory security descriptor; this does not prove persistence on a securable object.
- Keep the same retained handle for the disposable experiment's write/read-back/rollback stages and verify object identity at each stage.
- Preserve the original snapshot and all errors. Always attempt safe cleanup of the harness-owned disposable object.

## 7. Production safety gates

This protocol is a classification and evidence contract, not an implementation approval.

Until a separate reviewed change proves the exact semantics required by the production operation:

- Native Writer remains BLOCKED.
- Transactional ACL mutation remains BLOCKED.
- Terminal remains BLOCKED.
- All seven built-in templates remain disabled.
- No Workspace, Scratch, profile, system, repository, or other existing object may be used for native mutation experiments.
- No merge, deployment, process resume, or privilege expansion is authorized by this document.

A future writer design MUST declare its comparison profile, explain how each required state is represented, and fail closed when it cannot prove the declared postcondition. Any decision to accept OS-managed control-bit transitions requires a separate explicit security review and a revised operation contract; it is not implied by this v1.0 document.

## 8. Acceptance checklist for this protocol

- [ ] Review the distinction between DACL content, construction metadata and OS-managed control state.
- [ ] Verify that evidence records retain the full raw control word and separate inherited ACE observations.
- [ ] Verify the current strict FALSE round-trip failure remains visible and unchanged.
- [ ] Verify TRUE-state setup is classified NOT EXERCISED when creation does not retain TRUE.
- [ ] Review the comparison profile required by each future consumer before implementation.
- [ ] Obtain separate security review before changing any production mutation gate.

## 9. Microsoft API references

- [SECURITY_DESCRIPTOR_CONTROL](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control) — control-bit meanings and the non-persistent `SE_DACL_DEFAULTED` marker.
- [Security Descriptor Operations](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-operations) — security descriptor APIs and control-bit handling.
- [SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo) — object-handle security update API.
- [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo) — object-handle security query API.
- [GetSecurityDescriptorDacl](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptordacl) — in-memory descriptor DACL/defaulted output.
- [SetSecurityDescriptorDacl](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setsecuritydescriptordacl) — in-memory descriptor DACL/defaulted input.

---

**Protocol v1.0 disposition:** DRAFT / REVIEW REQUIRED. PR #131 remains the immutable experiment-evidence baseline for this follow-up; no production writer behavior is changed by this document.
