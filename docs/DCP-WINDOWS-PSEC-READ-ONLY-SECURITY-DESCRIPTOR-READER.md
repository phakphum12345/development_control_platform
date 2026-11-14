# WP-18B.1-E — Read-only Native Security Descriptor Reader

**Status:** IMPLEMENTATION CHECKPOINT — read-only descriptor acquisition only  
**Parent:** PR #124, `work/wp18b1-native-security-descriptor-transactions`  
**Parent HEAD:** `1798b74186fdd6a5960f78c52bb491bfbbe0ed45`

## Scope

This checkpoint adds a Windows-only reader that obtains security descriptor state through the exact retained file handle. It uses `GetSecurityInfo` with `SE_FILE_OBJECT` and `DACL_SECURITY_INFORMATION`, validates the returned descriptor and ACL, copies the complete ACL allocation (used plus free bytes), captures DACL presence/null state and descriptor control flags, then releases the API-owned descriptor buffer with `LocalFree`.

It also delegates identity queries to the existing native handle API. It does not reopen by path.

## Explicit non-goals

- No `SetSecurityInfo` call or DACL mutation.
- No ACE decoding, ACE construction, canonical-order repair, or Package-SID grants.
- No integration with the transaction coordinator, Launcher, or process resume.
- No host ACL changes and no change to execution/template defaults.

## Safety constraints

1. The reader accepts only a positive retained handle and uses `GetSecurityInfo` on that handle.
2. It checks the returned security descriptor and DACL with Windows validation APIs.
3. It bounds ACL allocation size to the native ACL size field and ACE count to 4096.
4. It copies the full ACL allocation before freeing the descriptor buffer.
5. It preserves DACL-present and NULL-pointer state separately, so an absent DACL, NULL DACL, and empty non-NULL ACL are not treated as equivalent.
6. It fails closed on malformed sizes, inconsistent ACL metadata, unsupported ACL revisions, API failures, or cleanup failure.

## Required validation

- Run `tests.test_windows_psec_security_descriptor_reader_real_host` on the target Windows host.
- Run the transaction, native handle, handle-tree, and ACL regression suites.
- Inspect the exact PR head and all CI jobs.
- Confirm directory and file DACL snapshots are stable across repeated read-only queries.
- No mutation acceptance is claimed by this checkpoint.

## Next implementation steps

1. Add strict ACE boundary and SID parsing while preserving each ACE's exact bytes.
2. Add Package-SID candidate construction with canonical-order validation and duplicate/overbroad grant rejection.
3. Add a separate handle-based writer only after parser/candidate tests pass.
4. Integrate the adapter with the transaction coordinator only after real-host reader evidence and code review.
5. Keep Launcher integration and effective AppContainer acceptance blocked until native transaction and rollback gates pass.
