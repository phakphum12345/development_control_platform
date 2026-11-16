# WP-18B.1-M — Protocol v1 Consumer Conformance Checkpoint

**Date:** 2026-11-15  
**Repository:** `phakphum12345/development_control_platform`  
**Branch:** `work/wp18b1m-protocol-v1-consumer-conformance`  
**Base:** PR #132 head `dce31f0dc7231074373ae866515a7a0b73c377dc`  
**Scope:** Read-only source-to-protocol audit; no native writer or ACL mutation.

## READ / ANALYZE

Inspected PR #130 Reader/Transaction source and design documents, PR #131 experiment evidence, and PR #132 Protocol v1.0.

### Findings

1. Reader captures DACL presence, NULL state, ACL bytes, `dacl_defaulted`, and raw control flags from the retained handle.
2. `DescriptorSnapshot` and `DescriptorCandidate` preserve the separate `dacl_defaulted` boolean and raw `dacl_control_flags`.
3. The transaction coordinator uses whole-dataclass equality for preflight drift, candidate read-back, and rollback verification. This is strict-like behavior, but the caller does not declare one of Protocol v1's named comparison profiles.
4. The transaction design document says read-back and rollback equality includes content, defaulted state and control flags. That contract needs reconciliation with Protocol v1's distinction between object-readable metadata and descriptor-construction metadata.
5. No production native writer exists in this inspected slice. The current coordinator is an adapter contract/orchestration layer and its tests use a fake adapter.

## MODIFY

- Added `docs/DCP-PSEC-DACL-PROTOCOL-V1-CONSUMER-CONFORMANCE.md` with a source-to-profile mapping, required contract corrections, proposed deterministic test matrix, and safety boundary.
- Added the audit to `docs/INDEX.md`.
- No source code, tests, workflow, PR #130, or PR #131 were modified.

## Exact-head CI baseline for parent Protocol PR #132

Parent PR #132 head: `dce31f0dc7231074373ae866515a7a0b73c377dc`.

- Local-first Minimal Emulator run #43627931853: PASS (Windows and Linux jobs).
- Validate Control Plane run #43627931856: PASS; Windows runner acceptance matrix SKIPPED because no eligible self-hosted runner was available. SKIPPED is not PASS.
- Cross-platform Recovery Acceptance run #43627931862: FAIL; Ubuntu job PASS; Windows job FAIL at `test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file`. This is the preserved strict evidence failure from PR #131, not a protocol-doc test failure.
- No PR #132 reviews or inline review threads were present at audit time.

## Next gated work

1. Review and approve the consumer mapping.
2. Implement an explicit comparison-profile contract and comparator in a separate code PR, with deterministic tests for all four profiles.
3. Require a declared profile before any adapter write; reject missing/unknown profiles before mutation.
4. Preserve strict comparison failure for `0x9004 → 0x9404`; do not mask the control-bit delta or downgrade automatically.
5. Define and test fail-closed preflight behavior for object snapshots whose `dacl_defaulted` marker cannot be represented/restored by the native object API.
6. Re-run exact-head CI and retain Windows native evidence separately.

## Safety disposition

- PR #130: OPEN / DRAFT / NOT MERGED; untouched.
- PR #131: OPEN / DRAFT / NOT MERGED; immutable experiment evidence.
- PR #132: OPEN / DRAFT / NOT MERGED; Protocol v1.0 remains DRAFT / REVIEW REQUIRED.
- Native Writer: BLOCKED.
- Transactional native ACL mutation: BLOCKED.
- Terminal: BLOCKED.
- Seven built-in templates: DISABLED.
- No merge, deployment, process resume, or privilege expansion authorized.

**Audit disposition:** PARTIAL / REVIEW REQUIRED. The next implementation slice must be non-native comparator and contract tests only.


## 2026-11-16 — Reconciliation and subsequent evidence

- Consumer-conformance branch reconciled onto the updated Protocol v1 line by merge commit `989df05fe999ef5508d879467f522239c3318f6f`, with the current Protocol v1 head as first parent and the original consumer-audit head as second parent.
- PR #131 and PR #132 have since been merged into their shared parent integration branch. This checkpoint's original OPEN/DRAFT statements above are historical creation-time status, not current PR status.
- The historical strict `0x9004 → 0x9404` finding remains valid under `STRICT_DESCRIPTOR_EQUALITY` and `CONTROL_STATE_EQUALITY`.
- A later, separate disposable-experiment audit (PR #145) permits only the OS-managed `SE_DACL_AUTO_INHERITED` transition for that experiment's acceptance check. It does not change the Protocol v1 strict comparator, does not normalize the raw control word, and does not enable production writes.
- The input-descriptor TRUE/FALSE test and the NTFS object-level TRUE persistence probe remain separate. If NTFS does not retain TRUE on the object, the object-level case is `NOT EXERCISED`, not PASS.
- PR #134 is the separate implementation slice for the explicit comparator; its exact-head CI and merge must be evaluated independently.
- Native Writer, production transactional ACL mutation, Terminal execution and all seven built-in templates remain BLOCKED / disabled.
