# WP-18B.1-G — Pure DACL Candidate Builder

**Status:** IMPLEMENTATION CHECKPOINT — in-memory candidate only  
**Parent:** PR #126, `work/wp18b1f-strict-dacl-ace-parser`  
**Parent HEAD:** `9acb8f1af6424ac8e844bb435e9b3027d96d0490`

## Scope

This checkpoint constructs bounded DACL byte candidates in memory. It does not open files or handles, call Win32 APIs, update security descriptors, or change host ACLs.

## Policy

| Target kind | Object | Access mask | Inheritance |
|---|---|---:|---|
| Workspace | Directory | `0x001200A9` READ_EXECUTE | OI + CI |
| Workspace | File | `0x001200A9` READ_EXECUTE | None |
| Scratch | Directory | `0x001301BF` MODIFY | OI + CI |
| Scratch | File | `0x001301BF` MODIFY | None |
| Job root | Directory | `0x00000020` FILE_TRAVERSE | None |

No other target kind/object combination is accepted.

## Preservation and ordering

- Every existing supported ACE is retained byte-for-byte and in its original relative order.
- ACL revision, reserved header bytes, and unused allocation bytes are preserved.
- The new explicit allow ACE is inserted after existing explicit ACEs and before inherited ACEs.
- Existing explicit deny ACEs must precede explicit allow ACEs.
- Existing explicit ACEs after inherited ACEs, explicit deny after explicit allow, and ACE types without an approved DACL ordering policy are rejected; the builder never silently reorders existing entries.
- An exact, unique existing Package-SID allow ACE is idempotent.
- Duplicate Package-SID ACEs, deny ACEs for that SID, overbroad or wrong-mask grants, and wrong inheritance are rejected.
- Absent or NULL DACLs are rejected. Unknown ACE layouts remain rejected by the parent strict parser.

## Important limitations

The builder supports only a conservative DACL ACE subset (ACCESS_ALLOWED_ACE and ACCESS_DENIED_ACE) for candidate policy. Other layouts that the lower-level parser can decode are rejected here because their DACL ordering/semantics have not been approved. It does not claim to canonicalize all Windows ACL variants.

The function is pure and deterministic. It does not prove that a native descriptor can be installed atomically, that inherited ACE propagation is correct on a real filesystem, or that rollback works.

## Explicit non-goals

- No `SetSecurityInfo`, `SetNamedSecurityInfo`, or other mutation API.
- No native adapter, transaction wiring, Launcher integration, or process resume.
- No host ACL changes and no broad-principal grants.
- Terminal execution remains blocked; all seven built-in templates remain disabled.

## Required validation

Run `tests.test_windows_psec_dacl_candidate_builder` and the full PSEC regression suite on the target Windows host. Inspect CI and exact-head evidence. The next checkpoint must separately validate native descriptor transaction behavior with fault injection before any writer is considered.
