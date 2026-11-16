# PSEC Mathematical Profile Adapter — Protocol v1 Experiment

**Status:** DRAFT / EXPERIMENT ONLY  
**Work package:** WP-18B.1-O  
**Parent:** PR #134 — Explicit DACL Comparison Profiles  
**Protocol:** DCP-PSEC DACL State Semantics Protocol v1.0  
**Scope:** Numeric adapter, deterministic Decimal diagnostics, and conformance tests. No native API calls or ACL mutation.

## 1. Objective

Provide a mathematically inspectable representation of the four existing Protocol v1 DACL comparison profiles without adding profiles, changing profile names, changing comparison semantics, or altering the strict native experiment.

This adapter is not a new comparison model. It is a reversible, typed representation around the existing four-profile resolver.

## 2. Immutable profile set

The adapter uses exactly these four stable integer identifiers:

| Adapter ID | Existing Protocol v1 profile |
|---:|---|
| 0 | `DACL_CONTENT_EQUALITY` |
| 1 | `DACL_OBJECT_STATE_EQUALITY` |
| 2 | `CONTROL_STATE_EQUALITY` |
| 3 | `STRICT_DESCRIPTOR_EQUALITY` |

The integer identifiers are aliases for the existing profile set, not additional profiles. Their mapping MUST NOT be reordered, expanded, reused, or inferred from transformed values.

The authoritative comparator remains `DaclComparisonProfile` and `dacl_states_equal` from `windows_psec_dacl_comparison.py`.

## 3. Mathematical representation

For an accepted integer identifier `n` in the closed range 0..3, the adapter computes:

- Square root: `sqrt(n)`, using Python `Decimal` with precision 50.
- Square: the square of the Decimal square-root representation, used only for a bounded round-trip diagnostic.
- Normalization: `n / 3`, represented as Decimal in the closed interval [0, 1].

These derived values are diagnostic metadata. They are not profile identifiers, comparison weights, security scores, or inputs to the comparator.

## 4. Safe decoding rule

Decoding MUST NOT round a floating-point or Decimal value to guess a profile ID.

Instead, the adapter returns a frozen typed record containing the original integer ID and its derived Decimal values. Decoding:

1. Requires the typed record.
2. Recomputes the canonical representation from the original ID.
3. Rejects any modified or non-canonical derived value.
4. Verifies the square-root/square round trip within the declared Decimal tolerance.
5. Resolves the original integer ID through the fixed four-entry mapping.

Only the original integer ID selects a profile. Unknown IDs, booleans, floats, strings, nulls, negative values, and values above 3 are rejected before comparator use.

## 5. Protocol invariants

- Exactly four existing profiles remain available.
- No default profile is introduced.
- No profile is silently promoted, downgraded, or substituted.
- No transformed Decimal or floating-point value reaches the comparator.
- Structural snapshot validation remains independent and mandatory.
- The full raw control word remains compared under control and strict profiles.
- A `0x9004 → 0x9404` transition remains FAIL under `CONTROL_STATE_EQUALITY` and `STRICT_DESCRIPTOR_EQUALITY`.
- A less strict profile result MUST NOT be described as strict equality or native-writer acceptance.

## 6. Test plan

Run:

- `python -m unittest tests.test_windows_psec_dacl_profile_math`
- `python -m unittest tests.test_windows_psec_dacl_comparison`
- `python -m unittest tests.test_windows_psec_security_descriptor_transaction`

Tests cover the exact four-profile mapping, Decimal square-root representation, normalization boundaries, round-trip tolerance, invalid input rejection, tamper detection, and preservation of the strict control-word transition failure.

## 7. Safety and release boundary

- Pure Python only; no Win32 APIs.
- No native DACL writes, rollback, or object mutation.
- No change to PR #131's strict failing native experiment.
- No change to PR #134's comparator semantics.
- Native Writer: BLOCKED.
- Transactional native ACL mutation: BLOCKED.
- Terminal: BLOCKED.
- Seven built-in templates: DISABLED.
- No merge, deployment, process resume, or privilege expansion is authorized.

**Disposition:** Experiment implementation only; exact-head CI, review, and audit are required.
