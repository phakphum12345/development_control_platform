# WP-18B1-P — PSEC Reversible State Preservation

**Status:** IMPLEMENTATION SLICE CREATED — EXACT-HEAD VALIDATION PENDING  
**Branch:** work/wp18b1p-psec-reversible-state-preservation  
**Base:** PR #135 head e525f8e6d2c247414e476928be195095138a2e35  
**PR:** not created at checkpoint authoring time

## Objective

Implement immutable preservation of the original DACL descriptor snapshot (S0), bind it to a transaction and stable target identity, and verify independent restoration read-back (S2) under an explicit Protocol v1 comparison profile.

## Scope completed in this slice

- Added a frozen original snapshot envelope.
- Captures DACL presence, NULL state, exact ACL bytes, DACL defaulted state, all 16-bit descriptor control flags, descriptor/ACL revisions, and ACE count through the existing DescriptorSnapshot.
- Added retained-handle capture that reads object identity before and after the descriptor snapshot and rejects identity drift.
- Integrated immutable S0 capture into the disposable NTFS native experiment; the harness verifies the digest before writing, uses S0 as the rollback source, and checks S2 through the strict Protocol v1 verifier.
- Adds transaction UUID, snapshot digest, and restoration mismatch evidence to the native experiment output.
- Binds the snapshot to a canonical transaction UUID and target volume serial / 128-bit file ID.
- Computes a SHA-256 integrity digest over metadata and exact binary ACL bytes.
- Adds fail-closed read-back verification under the selected existing comparison profile.
- Adds deterministic cross-platform unit tests for exact restoration, 0x9004 to 0x9404 strict mismatch, explicit content-only profile behavior, transaction/identity mismatch, tampering, invalid profile input, and retained-handle capture boundaries.

## Deliberate limitations

- No Win32 calls or SetSecurityInfo writes were added.
- No ACL mutation or production writer was added.
- Snapshot integrity is not proof that Windows can restore every captured field.
- Native restoration capability remains BLOCKED / NOT PROVEN.
- Existing FALSE exact round-trip failure remains unchanged.
- TRUE defaulted-state setup remains NOT EXERCISED where NTFS does not retain the requested state.
- Existing four comparison profiles are unchanged.

## Validation

- Local unittest execution: NOT RUN in authoring session.
- Previous exact-head validation on 9af105c5d9fb1d996bc5245faf4a27773afcfa96: 39 PSEC snapshot/comparison/transaction regression tests PASS on Ubuntu and Windows.
- Previous exact-head Cross-platform Recovery Acceptance: Ubuntu job PASS; Windows job FAILS only at the known native FALSE exact-round-trip assertion in tests.test_windows_psec_dacl_experiment. The PSEC regression step ran before the native experiment and passed on Windows.
- Local-first Minimal Emulator: Linux and Windows jobs PASS on that exact head.
- Validate Control Plane: PASS on that exact head.
- Current implementation has since added retained-handle snapshot capture and requires a fresh exact-head CI run.
- Required exact-head test command: python -m unittest tests.test_windows_psec_reversible_state tests.test_windows_psec_dacl_comparison tests.test_windows_psec_security_descriptor_transaction -v.
- Native experiment command: python -m unittest tests.test_windows_psec_dacl_experiment -v.
- Fresh exact-head CI is required after the retained-handle/native-experiment integration changes.
- Native Windows restore acceptance: NOT RUN; requires a separate disposable NTFS experiment and exact read-back evidence.

## Safety gates

Native Writer, Transactional ACL Mutation, Terminal, and all seven built-in templates remain BLOCKED. No merge, deployment, process resume, or privilege expansion is authorized.
