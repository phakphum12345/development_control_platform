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
- Binds the snapshot to a canonical transaction UUID and target volume serial / 128-bit file ID.
- Computes a SHA-256 integrity digest over metadata and exact binary ACL bytes.
- Adds fail-closed read-back verification under the selected existing comparison profile.
- Adds deterministic cross-platform unit tests for exact restoration, 0x9004 to 0x9404 strict mismatch, explicit content-only profile behavior, transaction/identity mismatch, tampering, and invalid profile input.

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
- Required exact-head CI: pending.
- Required test command: python -m unittest tests.test_windows_psec_reversible_state -v.
- Regression commands: python -m unittest tests.test_windows_psec_dacl_comparison tests.test_windows_psec_security_descriptor_transaction -v.
- Native Windows restore acceptance: NOT RUN; requires a separate disposable NTFS experiment and exact read-back evidence.

## Safety gates

Native Writer, Transactional ACL Mutation, Terminal, and all seven built-in templates remain BLOCKED. No merge, deployment, process resume, or privilege expansion is authorized.
