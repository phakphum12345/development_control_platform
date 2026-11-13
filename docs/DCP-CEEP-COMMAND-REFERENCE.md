# DCP-CEEP Universal Command Reference

**Applies to:** DCP-CEEP v2.0  
**Status:** Draft reference; command labels do not guarantee tool availability.

## Master entry point

`DCP/INTELLIGENT-E2E` — classify the task, inspect current state, select a suitable profile, plan required stages, enforce approvals, verify, and report.

## Lifecycle commands

| Command | Purpose |
|---|---|
| `DCP/START` | Capture objective, scope, constraints, and authority |
| `DCP/STATUS` | Report current state, evidence revision, blockers, and next action |
| `DCP/PLAN` | Create work packages and dependency graph |
| `DCP/SEARCH` | Search repository, files, and project records |
| `DCP/WEB-SEARCH` | Research public web sources |
| `DCP/AUDIT` | Inspect implementation, configuration, and gaps |
| `DCP/TRACE` | Trace requirements, data flow, and execution paths |
| `DCP/IMPLEMENT` | Perform authorized changes |
| `DCP/TEST` | Run task-appropriate tests |
| `DCP/VERIFY` | Verify deliverables against acceptance criteria |
| `DCP/CHECKPOINT` | Persist a resumable state |
| `DCP/CONTINUE` | Start the next unblocked authorized work package |
| `DCP/RECOVER` | Resume safely after interruption |
| `DCP/ROLLBACK` | Restore a known-good state when authorized |
| `DCP/REPORT` | Produce evidence-backed progress or final report |
| `DCP/STOP` | Stop safely and record a checkpoint |

## Research commands

| Command | Purpose |
|---|---|
| `DCP/OFFICIAL-DOCS` | Find authoritative framework/API documentation |
| `DCP/SOURCE-RESEARCH` | Inspect official source repositories and issue trackers |
| `DCP/PACKAGE-SEARCH` | Discover packages, libraries, SDKs, and tools |
| `DCP/RELEASE-CHECK` | Check releases, deprecations, and breaking changes |
| `DCP/SECURITY-CHECK` | Check advisories and security guidance |
| `DCP/RESEARCH-VERIFY` | Cross-check material claims against primary sources |
| `DCP/KNOWLEDGE-CACHE` | Reuse prior research when scope and freshness remain valid |
| `DCP/ALTERNATIVES` | Compare implementation and tooling options |
| `DCP/COMPATIBILITY` | Check platform/runtime/API compatibility |
| `DCP/SUPPLY-CHAIN` | Assess package provenance, integrity, licensing, and risk |
| `DCP/INTEGRATION-PLAN` | Plan safe integration and rollback |

## Quality and continuity commands

| Command | Purpose |
|---|---|
| `DCP/ROOT-CAUSE` | Determine the supported cause of a failure |
| `DCP/PARALLELIZE` | Identify independent work that can run concurrently |
| `DCP/COMPLETION-AUDIT` | Check requirements and deliverables for omissions |
| `DCP/EVIDENCE-AUDIT` | Check that claims have current, relevant evidence |
| `DCP/DEPENDENCY-AUDIT` | Check internal and external dependency relationships |
| `DCP/PROGRESS-UPDATE` | Publish a meaningful progress checkpoint |
| `DCP/DECISION-RECORD` | Record material choices and rationale |

## Universal statuses

- PASS — criterion met with current evidence.
- FAIL — evidence shows criterion not met.
- SKIPPED — check not run.
- UNKNOWN — insufficient evidence.
- IN_PROGRESS — work is underway.
- BLOCKED — cannot proceed until a dependency, permission, decision, or external condition is resolved.

Never promote a non-PASS status to PASS.

## Tool availability rule

A command is a workflow label, not a claim that a matching tool, connector, package, or automation exists. Discover the actual available tool and inspect its supported arguments and permissions before execution. If unavailable, report the limitation and use an approved alternative or mark the task BLOCKED/UNKNOWN.
