# WP-18B.1-F — Strict DACL ACE Parser

**Status:** IMPLEMENTATION CHECKPOINT — pure parser only  
**Parent:** PR #125, `work/wp18b1e-native-security-descriptor-adapter`  
**Parent HEAD:** `c130b9c44f7259ec736666e3c71fc1329d6d6363`

## Scope

This checkpoint parses the bounded ACL byte allocation returned by the read-only native descriptor reader. It validates the ACL header, declared allocation size, ACE count, ACE boundaries, DWORD alignment, supported ACE type, SID revision/count/length, and preserves each accepted ACE byte-for-byte.

The parser returns unused allocation bytes separately. It does not interpret those bytes as ACEs and does not discard or rewrite them.

## Supported subset

- ACCESS_ALLOWED_ACE (type 0)
- ACCESS_DENIED_ACE (type 1)
- SYSTEM_AUDIT_ACE (type 2)
- SYSTEM_ALARM_ACE (type 3)
- SYSTEM_MANDATORY_LABEL_ACE (type 17)

Object-specific, callback, resource-attribute, access-filter, and all other ACE layouts are rejected. This is intentional fail-closed behavior, not a claim that such ACEs are invalid Windows ACLs.

## Explicit non-goals

- No ACE insertion, deletion, reordering, canonicalization, or DACL candidate construction.
- No Package-SID grants.
- No SetSecurityInfo or other descriptor mutation.
- No transaction adapter or Launcher integration.
- No host ACL changes; terminal execution and built-in templates remain disabled.

## Required validation

- Run `tests.test_windows_psec_dacl_ace_parser` on Windows and the existing PSEC regression suites.
- Test malformed sizes, truncated ACEs, unknown layouts, malformed SIDs, allocation padding, and lossless ACE preservation.
- Review supported ACE types against the actual target filesystem descriptors before any candidate builder is introduced.

## Next gate

A separate candidate-builder checkpoint must decide how to preserve all existing ACEs, reject duplicate/overbroad Package-SID grants, and prove canonical ordering. The writer remains prohibited until that work and fault-injected native transaction acceptance are complete.
