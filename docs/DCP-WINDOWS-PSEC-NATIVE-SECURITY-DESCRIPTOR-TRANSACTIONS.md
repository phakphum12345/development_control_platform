# Windows PSEC Native Security Descriptor Transactions — WP-18B.1-D

**Status:** IMPLEMENTATION DESIGN / GATE DEFINITION — native mutation code not yet accepted  
**Protocol:** DCP-CEEP v1.0  
**Parent:** PR #123, `work/wp18b1-native-handle-acl-engine`  
**Parent HEAD at branch creation:** `ad60202116804f6eecb70fe26c3d7ce850d96431`

## 1. Objective

Implement a transaction layer that reads, modifies, verifies, and if necessary restores DACLs using the exact retained kernel handles produced by WP-18B.1-B/C. It must not reopen targets by path, follow reparse points, mutate a shared ancestor, or allow a child process to resume before authorization is verified.

This document is a design gate. It does not claim the transaction engine is implemented or that Package-SID access is working.

## 2. Scope boundary

In scope:

- Handle-based security descriptor retrieval through `GetSecurityInfo`.
- DACL snapshotting that distinguishes a NULL DACL, an empty DACL, and a populated DACL.
- ACE inspection that fails closed for unsupported or malformed structures.
- Least-privilege Package SID ACE planning for the disposable job root, Workspace projection, and Scratch.
- Handle-based DACL application through `SetSecurityInfo`.
- Read-back verification against the intended policy.
- Reverse-order rollback and verification of restoration.
- Deterministic fault injection and Windows real-host tests on disposable fixtures.

Out of scope for this workstream:

- Launcher integration or `ResumeThread` changes.
- Source Workspace or host profile ACL mutation.
- Any grant to Everyone, Users, Authenticated Users, or other broad principals.
- Recursive traversal beyond the explicit bounded manifest produced by the handle-tree layer.
- Enabling Terminal execution or any built-in template.
- Merging this PR or any stacked PR.

## 3. Required invariants

1. **Handle identity binding:** every operation uses the retained handle and its captured volume serial, full 128-bit file ID, type, attributes, and reparse tag. Re-query the same handle immediately before mutation and reject identity drift.
2. **No path fallback:** the transaction layer accepts an opened-object/handle reference, not a path. It must never call `GetNamedSecurityInfoW`, `SetNamedSecurityInfoW`, or reopen a target by name.
3. **Preflight barrier:** enumerate and open every target, validate every object, inspect every existing DACL, and construct every proposed DACL before the first write. Any preflight failure means zero writes.
4. **Preserve existing policy:** retain all existing ACEs and descriptor semantics not explicitly changed by the Package-SID policy. Unknown ACE types, object ACEs, callback ACEs, conditional ACEs, resource attributes, integrity labels, or unsupported control states must not be silently dropped or misparsed.
5. **Least privilege:** Package SID gets only traversal on the disposable job root, read/execute on projected Workspace objects, and modify on per-job Scratch objects. No write permission on Workspace and no grant on the job-root parent.
6. **Atomicity is not assumed:** multiple DACL writes are not a kernel-atomic transaction. Maintain an ordered journal and restore successfully changed targets in reverse order on any later failure.
7. **Rollback proof:** after rollback, read each affected DACL back through the same retained handle and compare its security-relevant binary representation and DACL control state to the preflight snapshot. A failed rollback or unverifiable restoration is a distinct fatal state, not ordinary failure.
8. **No execution on uncertainty:** authorization setup, read-back, rollback, or handle-close uncertainty blocks launch. This stage does not change launcher behavior.
9. **Handle ownership:** all retained handles and allocated security descriptors/ACL buffers have explicit ownership and deterministic cleanup. Cleanup errors are surfaced and cannot be overwritten by a later success result.
10. **Bounded work:** cap object count, descriptor/ACL byte lengths, ACE count, and aggregate journal memory. Exceeding any cap fails before mutation.

## 4. Descriptor and DACL snapshot model

The implementation must model, at minimum:

- descriptor revision and control flags;
- DACL-present state;
- DACL pointer state (NULL versus non-NULL);
- DACL defaulted state returned by `GetSecurityDescriptorDacl`, plus protected/auto-inherited descriptor control state;
- ACL revision, size, ACE count, and exact bytes;
- each ACE's type, flags, size, trustee SID (when the ACE format supports one), and access mask (when the ACE format supports one).

Do not equate a NULL DACL with an empty DACL. Do not assume every ACE contains a conventional SID at a fixed offset. ACE decoding must be type-aware. If a descriptor contains a construct that the implementation cannot preserve exactly, reject the entire transaction before the first mutation.

Snapshots and candidates must preserve the exact original DACL bytes, the separate `dacl_defaulted` boolean, and descriptor control information required to restore protection/inheritance semantics. Read-back and rollback equality includes all three.

### Win32 defaulted-state limitation — mandatory native-writer gate

The read API exposes `DaclDefaulted` through `GetSecurityDescriptorDacl`, but `SetSecurityInfo` accepts a DACL pointer and `SECURITY_INFORMATION`; it has no `bDaclDefaulted` parameter. Microsoft documents that `SetSecurityInfo` sets or clears descriptor control bits as appropriate, while `SetSecurityDescriptorDacl` is the API that explicitly accepts `bDaclDefaulted`. Therefore, the transaction model's ability to carry and compare this bit does **not** prove that a native `SetSecurityInfo` writer can restore a prior TRUE value.

Until a disposable Windows-host experiment proves the exact round-trip semantics, a future native adapter must reject a preflight snapshot with `dacl_defaulted == true` before the first write. It must not claim rollback equivalence for such an object, attempt a path-based or undocumented workaround, or silently drop the state. Native-writer implementation and acceptance remain BLOCKED on this question. See [GetSecurityDescriptorDacl](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptordacl), [SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo), and [SetSecurityDescriptorDacl](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setsecuritydescriptordacl).
 Do not serialize and later reconstruct the original policy from lossy SDDL text.

## 5. Native API contract

The implementation should isolate native calls behind an injectable adapter so unit tests can deterministically inject failures.

Expected native operations:

- Query descriptor: `GetSecurityInfo(handle, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, ...)`.
- Apply DACL: `SetSecurityInfo(handle, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION plus the explicitly selected protection flags, ...)`.
- Inspect ACL: `GetAclInformation` and `GetAce`, with strict bounds checking.
- Allocate/free native memory with matching allocator ownership and checked return values.

Before adopting any API signature, flag, allocator, or ACE-ordering rule, verify it against the Windows SDK/official API contract. The adapter must preserve the native error code and operation name in diagnostics. Never infer success from a non-exceptional return when the API reports failure.

### ACE construction and ordering

- Construct only the required Package-SID allow ACEs and exact masks.
- Preserve pre-existing ACEs, including ACEs not understood by the policy evaluator, only if byte-for-byte preservation is supported and verified.
- Reject unsupported ACE layouts rather than treating them as allow or deny.
- Do not append allow ACEs blindly: verify canonical ordering and ensure explicit deny ACE precedence remains intact.
- Reject existing Package-SID ACEs that exceed the policy. Do not broaden or silently normalize them.

## 6. Transaction algorithm

### Phase A — read-only preflight

1. Validate the exact Package SID obtained from the matching suspended child token; bind it to a unique launch-attempt context.
2. Receive a bounded, complete manifest of retained objects from the native handle-tree layer.
3. Re-query and validate each object's identity and type on its retained handle.
4. Read each descriptor and snapshot the DACL bytes and relevant control flags.
5. Parse ACEs type-safely; reject malformed, unsupported, ambiguous, or over-broad policy.
6. Construct each candidate DACL in memory and validate its size, ACE count, ordering, and exact Package-SID grant.
7. Confirm that no target is the shared parent, source Workspace, user profile, or an ancestor outside the disposable job root.
8. Confirm the entire plan and rollback journal fit configured resource ceilings.

**Invariant:** no call to `SetSecurityInfo` is allowed in Phase A.

### Phase B — apply

1. Process targets in deterministic parent-before-child order.
2. Re-query the same retained handle's identity immediately before mutation.
3. Apply the candidate DACL to that handle only.
4. Immediately read the DACL back from the same handle.
5. Compare the read-back with the planned policy, including ACE masks/flags/order and DACL protection semantics.
6. Append a target to the committed journal only after its read-back has passed.
7. On any error, stop applying new targets and enter rollback.

### Phase C — rollback

1. Restore every committed target in reverse order using its original snapshot and the same retained handle.
2. Read each restored DACL back and compare it to the original snapshot and control state.
3. Continue attempting restoration of remaining targets after an individual rollback failure.
4. Return one of:
   - `ROLLED_BACK_VERIFIED`: all changed targets restored and verified;
   - `ROLLBACK_INCOMPLETE_BLOCKED`: one or more targets could not be restored or verified.
5. Never report a successful transaction after any rollback path.

### Phase D — success result

Return `APPLIED_VERIFIED` only if every target was updated and read back successfully, all identity checks passed, and all owned native resources were released or transferred under an explicit owner. This status alone does not authorize process resume.

## 7. Test matrix

### Portable adapter/contract tests

- NULL DACL versus empty DACL.
- Populated DACL with allow, deny, inherited, object-specific, callback, and unknown ACE types.
- Malformed ACL header, invalid ACL size, ACE count overflow, ACE size underflow/overflow, invalid SID bounds.
- Package SID mismatch, duplicate Package SID ACE, over-broad Package SID rights.
- DACL protected/unprotected and inherited ACE combinations.
- Canonical and non-canonical ACE ordering.
- Exact byte preservation for every supported untouched ACE.
- Resource-ceiling enforcement before mutation.
- No writes on any preflight error.
- Deterministic fault injection at every native operation.

### Transaction fault-injection tests

Inject failure at:
- descriptor query for each target;
- ACL parse and candidate construction;
- identity re-query;
- first, middle, and last `SetSecurityInfo`;
- each read-back query and comparison;
- each rollback write;
- each rollback verification;
- each native allocation/free and handle close.

Assert:
- no mutation before preflight completes;
- writes stop at first apply failure;
- rollback order is reverse commit order;
- all remaining rollback entries are attempted after one rollback error;
- rollback status is never reported PASS unless every restoration is verified;
- no handle is closed twice and no allocated buffer is leaked.

### Windows real-host tests

Run only in a disposable temporary tree on the target Windows host:

- snapshot and read-back without mutation;
- apply exact Package-SID policy to disposable objects and inspect effective descriptor state;
- verify parent DACL remains byte-for-byte unchanged;
- verify Workspace read/execute and write denied; Scratch modify allowed;
- verify inherited child behavior;
- exercise NULL/empty DACL safely on isolated fixtures;
- inject controlled failures and prove rollback;
- race/replacement/reparse adversarial tests against retained-handle identity checks;
- verify no changes escape the disposable root.

A real-host test that is skipped is not PASS. A successful DACL write/read-back is not, by itself, proof that AppContainer effective access works; that requires a later suspended-child acceptance stage.

## 8. Acceptance gates and status vocabulary

Allowed statuses: PASS / FAIL / SKIPPED / UNKNOWN / IN_PROGRESS. SKIPPED and UNKNOWN are never PASS.

WP-18B.1-D is complete only when:
- portable transaction tests pass;
- Windows real-host transaction tests pass without skip;
- fault-injection rollback matrix passes;
- parent and out-of-scope ACL snapshots remain unchanged;
- source review confirms there is no path-based mutation fallback;
- CI for the exact PR head is complete and required jobs pass.

Until then:
- launcher integration: BLOCKED;
- effective AppContainer authorization acceptance: BLOCKED;
- Terminal execution: BLOCKED;
- all seven built-in templates: DISABLED;
- PRs remain draft/unmerged pending Protocol v1 review and explicit user authorization.

## 9. Evidence ledger

| Evidence | Status | Notes |
|---|---|---|
| Parent WP-18B.1-B/C real-host traversal/enumeration | PASS | User ran 1 Windows real-host test on `ad60202116804f6eecb70fe26c3d7ce850d96431`; result `OK`. |
| Parent handle-tree/native-handle/ACL regression | PASS | User ran 34 tests on the same SHA; result `OK`. |
| Native descriptor transaction implementation | IN_PROGRESS | Not implemented in this design checkpoint. |
| Transaction fault-injection matrix | UNKNOWN | Not run. |
| Windows real-host DACL transaction | UNKNOWN | Not implemented/run. |
| AppContainer effective Workspace/Scratch access | FAIL (prior acceptance) | Earlier host acceptance failed Workspace read and Scratch write; this checkpoint does not overwrite that result. |
| Launcher integration | SKIPPED / BLOCKED | Intentionally not started. |

## 10. Next implementation sequence

1. Add an injectable handle-security API adapter and typed snapshot/result models.
2. Implement strict ACL/ACE parsing and exact snapshot capture.
3. Implement candidate DACL construction with preservation and canonical-order checks.
4. Implement apply/read-back journal and reverse rollback.
5. Add portable and fault-injection tests.
6. Add Windows-only real-host tests and run them on the target host.
7. Review the exact PR head, CI, and all Protocol v1 evidence before proceeding to launcher integration.
