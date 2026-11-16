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
- Exact-head validation on adc8904ad02cdb242914b7bdc81163ae6c56a971: 44 PSEC snapshot/comparison/transaction regression tests PASS on Ubuntu and Windows.
- Cross-platform Recovery Acceptance: Ubuntu job PASS; Windows job FAILS at the known native FALSE exact-round-trip assertion in tests.test_windows_psec_dacl_experiment. The new PSEC regression step ran before the native experiment and passed on Windows.
- Windows native evidence now shows S0=0x9004, S1=0x9404, S2=0x9404, identical DACL bytes, DaclDefaulted=FALSE, and RESTORE_NOT_EXACT with control_flags_mismatch. Snapshot transaction ID and SHA-256 digest are present in the evidence.
- Local-first Minimal Emulator: Linux and Windows jobs PASS on that exact head.
- Validate Control Plane: PASS on that exact head. Windows runner acceptance matrix remained SKIPPED and is not counted as PASS.
- Current exact-head validation is required again after this documentation update.
- Required test command: python -m unittest tests.test_windows_psec_reversible_state tests.test_windows_psec_dacl_comparison tests.test_windows_psec_security_descriptor_transaction -v.
- Native experiment command: python -m unittest tests.test_windows_psec_dacl_experiment -v.
- Native Windows restore acceptance: NOT RUN; requires a separate disposable NTFS experiment and exact read-back evidence.

## Safety gates

Native Writer, Transactional ACL Mutation, Terminal, and all seven built-in templates remain BLOCKED. No merge, deployment, process resume, or privilege expansion is authorized.

## 2026-11-16 — Reconciliation and dual-status acceptance update

- Current implementation head before this checkpoint update: `b5e9e8fbac3d75f6e69c71fc44bdf3ce4c51c252`.
- Reconciliation parent includes PR #131, #132, #133, #134, #135, #145 and #146.
- The initial strict FALSE round-trip finding remains valid as `RESTORE_NOT_EXACT` under `STRICT_DESCRIPTOR_EQUALITY`.
- The later disposable NTFS experiment accepts only the one-way OS-managed `SE_DACL_AUTO_INHERITED (0x0400)` transition while requiring exact DACL bytes, `DaclDefaulted`, protected state and all other control bits. This is a separate experiment-only acceptance profile.
- `outcome=PASS` / `rollback_verified=true` under that experiment profile does not change `restoration_verification_state=RESTORE_NOT_EXACT` under strict Protocol v1 equality.
- The production transaction coordinator remains strict and has a regression test proving that the OS-managed control transition is rejected and rollback is attempted.
- The dedicated Windows NTFS CI job ran without the user's local PC. FALSE round-trip and rollback passed under the experiment-specific allowance; TRUE object persistence remains NOT EXERCISED when NTFS does not retain TRUE.
- Exact-head CI for `b5e9e8fbac3d75f6e69c71fc44bdf3ce4c51c252`: Windows NTFS acceptance, Windows/Ubuntu recovery, Local-first Windows E2E, Linux emulator and Validate Control Plane PASS; Windows runner matrix SKIPPED (not counted as PASS).
- The current branch has been reconciled onto the shared DACL integration parent; no merge to main or production deployment has occurred.
