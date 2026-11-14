# PSEC DACL Comparison Profiles — Implementation Slice

**Status:** DRAFT / REVIEW REQUIRED  
**Work package:** WP-18B.1-N  
**Parent:** PR #133 — Protocol v1 Consumer Conformance Audit  
**Scope:** Pure comparison logic and deterministic adapter-contract tests only.

## 1. Implemented contract

`DaclComparisonProfile` is a required per-operation input to `NativeSecurityDescriptorTransaction.apply`.

Accepted values are the exact Protocol v1 names:

- `DACL_CONTENT_EQUALITY`
- `DACL_OBJECT_STATE_EQUALITY`
- `CONTROL_STATE_EQUALITY`
- `STRICT_DESCRIPTOR_EQUALITY`

Missing or unknown values return `PREFLIGHT_REJECTED_BLOCKED` before the adapter is consulted. There is no implicit default, alias, fallback, or automatic profile downgrade.

## 2. Comparison dimensions

| Profile | DACL presence / NULL / bytes | Object-readable `dacl_defaulted` | Complete raw control word |
|---|---:|---:|---:|
| `DACL_CONTENT_EQUALITY` | Yes | No | No |
| `DACL_OBJECT_STATE_EQUALITY` | Yes | Yes | No |
| `CONTROL_STATE_EQUALITY` | No | No | Yes |
| `STRICT_DESCRIPTOR_EQUALITY` | Yes | Yes | Yes |

The control profile compares the complete 16-bit raw word; decoded bits are diagnostics, not a substitute for raw-word comparison. Content equality distinguishes absent, NULL, and present non-NULL DACLs.

The comparator does not replace structural validation. Snapshot and candidate validation remains mandatory during preflight, and read-back / rollback snapshots are validated before comparison. ACL byte content remains the canonical content evidence; parsed metadata is not substituted for those bytes.

## 3. Coordinator integration

The selected profile is applied consistently to:

1. Pre-write drift comparison against the preflight snapshot.
2. Candidate read-back verification.
3. Rollback read-back verification.

A result under a less strict profile is only a result for that explicitly requested comparison dimension. It must not be represented as strict descriptor equality or overall native-writer acceptance.

The deterministic transaction tests retain `STRICT_DESCRIPTOR_EQUALITY` unless a test explicitly exercises another profile. A synthetic adapter test models the observed control-word transition `0x9004 → 0x9404`: content equality can pass when only the raw control word changes, while strict equality fails and rollback remains blocked when the adapter cannot restore the original control word.

## 4. Safety boundary

- No Windows API, `GetSecurityInfo`, `SetSecurityInfo`, or ACL mutation is introduced.
- The synthetic control-transition adapter is test-only and is not a native behavior implementation.
- Native Writer remains BLOCKED.
- Transactional native ACL mutation remains BLOCKED.
- Terminal remains BLOCKED.
- All seven built-in templates remain disabled.
- This PR does not authorize merge, deployment, process resume, or privilege expansion.

## 5. Validation required

- Run `tests.test_windows_psec_dacl_comparison`.
- Run `tests.test_windows_psec_security_descriptor_transaction`.
- Inspect exact-head CI and confirm no unrelated workflows or native experiments were changed.
- Preserve the original Windows Server 2025 strict round-trip failure in PR #131; this implementation slice does not modify that experiment or assertion.
- Obtain review of the profile semantics before any native writer work.

**Disposition:** Comparator contract implemented in a separate child PR; exact-head validation and review remain required.
