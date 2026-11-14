# WP-18B.1-O — PSEC Mathematical Profile Adapter Experiment

**Date:** 2026-11-15  
**Repository:** `phakphum12345/development_control_platform`  
**Branch:** `work/wp18b1o-psec-mathematical-profile-adapter`  
**Base:** PR #134 exact head `b60aeec8bca7e28882afb86ed221f0ded99f9c25`  
**Current implementation checkpoint before this file:** `9d12712d4c6eebe80f3bca8c16f1b893b72688fd`  
**Scope:** Pure Python mathematical adapter, Decimal diagnostics, deterministic tests and documentation. No native calls or ACL mutation.

## READ

- Confirmed PR #131 remains OPEN / DRAFT / NOT MERGED at `7efd55086644555527506a30e18cdb091d3f6448`.
- Confirmed PR #134 remains OPEN / DRAFT / NOT MERGED at `b60aeec8bca7e28882afb86ed221f0ded99f9c25`.
- Read the Protocol v1 normative DACL state model and the four-profile comparator implementation.
- PR #134 exact-head workflows: Local-first Minimal Emulator PASS; Validate Control Plane PASS; Cross-platform Recovery Acceptance FAIL. The Windows strict native experiment failure is preserved and is not attributed to the pure comparator.

## ANALYZE

- Protocol v1 already defines exactly four comparison profiles.
- Mathematical transforms must not become a new comparison dimension or a means of selecting a profile by rounding.
- A floating-point inverse such as `round(sqrt_value ** 2)` would be unsafe as an authority-bearing resolver.
- Use a typed immutable encoding carrying the original integer ID; recompute and validate its Decimal diagnostics before resolving the original ID.
- Keep comparator and transaction code unchanged.

## MODIFY

- Added `tools/local_runner_agent/windows_psec_dacl_profile_math.py`.
- Added `tests/test_windows_psec_dacl_profile_math.py`.
- Added `docs/DCP-PSEC-DACL-MATHEMATICAL-PROFILE-ADAPTER.md`.
- Added the experiment to `docs/INDEX.md`.
- Numeric adapter IDs 0–3 map one-to-one to the four existing Protocol v1 profiles. No fifth profile, alias, or comparator rule is introduced.
- Square root, square round-trip diagnostics and normalization use Decimal values; only the original integer ID reaches the resolver.
- Invalid types, out-of-range IDs, tampered encodings and untyped inputs fail closed.

## TEST

- Local test execution: NOT RUN in this session.
- Exact-head CI: PENDING until the Draft PR is opened and workflows complete.
- Required commands:
  - `python -m unittest tests.test_windows_psec_dacl_profile_math`
  - `python -m unittest tests.test_windows_psec_dacl_comparison`
  - `python -m unittest tests.test_windows_psec_security_descriptor_transaction`
- Must confirm the synthetic `0x9004 → 0x9404` transition still fails under strict equality.

## AUDIT / SAFETY

- PR #131 and PR #134 source files are unchanged by this work branch.
- No Windows API calls, native DACL writes, rollback, or object mutation.
- Native Writer: BLOCKED.
- Transactional native ACL mutation: BLOCKED.
- Terminal: BLOCKED.
- Seven built-in templates: DISABLED.
- No merge, deployment, process resume, or privilege expansion authorized.

## NEXT GATE

1. Inspect the complete branch diff and test source.
2. Run the three required test modules.
3. Open a Draft PR targeting the PR #134 branch, preserving the dependency stack.
4. Inspect exact-head workflow results and logs.
5. Keep this experiment unmerged until review and CI audit are complete.


## Implementation audit update — 2026-11-15

**Audited branch head before this checkpoint amendment:** `dd96e91caad7928b33c16817bd021e7d0e4ce8c4`

- Kept the four-entry mapping immutable and used a frozen typed encoding record.
- Corrected the square diagnostic to run under the declared Decimal precision context.
- Corrected the test fixture to use the canonical eight-byte empty ACL representation.
- Local execution remains NOT RUN; these source corrections are not represented as test passes.
- The next exact commit after this checkpoint update must be used for PR and CI evidence.
