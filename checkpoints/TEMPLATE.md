# Development Checkpoint

- Captured at (UTC):
- Product edition: `personal | organization`
- Project ID:
- Repository:
- Branch:
- Exact HEAD SHA (40 hexadecimal characters):
- Baseline SHA:
- Working-tree state:
- Last verified workflow/run:
- Evidence freshness: `fresh | stale | unknown`

## Current phase

- Phase:
- Status: `not_started | in_progress | blocked | ready_for_review | complete`
- Acceptance criteria:
- Project-specific required gates:

## Evidence audit

| Gate | Required? | Result | Exact commit SHA | Observed at (UTC) | Evidence URL | Notes |
|---|---|---|---|---|---|---|
| Format | project-defined | unknown | | | | |
| Analyze | project-defined | unknown | | | | |
| Tests | project-defined | unknown | | | | |
| Platform CI | project-defined | unknown | | | | |
| Security review | project-defined | unknown | | | | |
| Edition acceptance | project-defined | unknown | | | | |
| Evidence audit | yes | unknown | | | | |

These are illustrative gate names, not universal requirements. Record the
actual required gates for this project. Do not mark a gate passing without
verifiable evidence for the exact commit SHA.

## Edition-specific checks

- Personal Edition acceptance evidence:
- Organization authorization and tenant-isolation evidence:
- Integration opt-in and approved permission scopes:
- Human approval reference for any new write scope:

## Blockers

- None recorded / list specific blockers.

## Changes since previous checkpoint

- None recorded yet.

## Safe next actions

1. READ repository state, branch, pull requests, staged and unstaged changes.
2. ANALYZE the diff, requirements, edition boundaries, and evidence freshness.
3. WRITE/MODIFY only the authorized scope.
4. TEST project-specific required gates and capture exact run URLs and SHAs.
5. AUDIT the diff, permissions, evidence, and history before merge.

## Resume rule

Never infer a pass from absent, stale, or different-SHA evidence. Treat
unverified results as unknown. Do not merge if any required gate is failing,
pending, or unknown.
