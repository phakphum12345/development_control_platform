# DCP-CEEP v2.0 Migration Guide

**Status:** Draft for review  
**From:** DCP-CEEP v1.0  
**To:** DCP-CEEP v2.0 Universal

## 1. Migration objective

v2.0 generalizes the repository-focused continuity protocol into a task-profiled protocol for multiple work domains. It preserves v1.0's evidence discipline, exact-revision checks, checkpointing, non-destructive behavior, detailed reporting, and explicit merge approval.

This guide does not silently change the status of PRs, grant new permissions, or declare v2.0 adopted.

## 2. Requirements retained from v1.0

| v1.0 requirement | v2.0 location |
|---|---|
| Evidence-backed completion; no unsupported success claims | §§1, 14, 17, 18 |
| Distinct PASS / FAIL / SKIPPED / UNKNOWN / IN_PROGRESS | §17 (adds BLOCKED) |
| Repository/base/head SHA baseline and exact-head CI checks | §§5, 13, 14 |
| Continuous execution loop | §§3, 9, 19 |
| Checkpoint, bounded retry, idempotency, recovery | §§12, 13, 15 |
| Documentation and traceability obligations | §§5, 18 |
| Full progress and final reporting | §§12, 18 |
| Explicit merge authorization | §16 |
| No unapproved deletion, secret disclosure, or billable cloud resources | §§11, 16 |
| Continuity ledger and safe resume | §§13, 15 |

## 3. Additions in v2.0

- Task profiles for software, systems, hardware, CAD, physics, research, data, operations, and other work.
- External research with primary-source preference and freshness/version checks.
- Package, tool, license, provenance, and supply-chain evaluation.
- Root-cause analysis and alternative comparison.
- Dependency-graph planning and safe parallel execution.
- Generalized verification for non-software deliverables.
- Explicit distinction between protocol command labels and actually available automation tools.
- Broader approval gates for package installation, publishing, deployment, data deletion, and costs.

## 4. Status migration

v1.0 defines five statuses. v2.0 adds BLOCKED for work that cannot proceed because of a dependency, permission, decision, or external condition.

Do not convert historical statuses automatically. Preserve the original recorded status and add BLOCKED only for new or explicitly reclassified records with a documented reason.

SKIPPED, UNKNOWN, IN_PROGRESS, and BLOCKED are never PASS.

## 5. Adoption sequence

1. Review v2.0 against the v1.0 protocol and continuity ledger.
2. Resolve conflicting or duplicated wording.
3. Review command names and map them to actual available tools.
4. Add project-specific profiles and acceptance criteria.
5. Update the README and roadmap without deleting prior history.
6. Add requirement-to-document traceability.
7. Obtain explicit project-owner approval to adopt v2.0.
8. Mark v1.0 as superseded only after adoption; retain it for historical reference.

## 6. Compatibility and safety

- Existing v1.0 workflows remain valid until the adoption decision.
- v2.0 does not authorize Push, Merge, Deploy, Delete, package installation, or paid resources.
- Existing repository PR and CI gates remain in force.
- A protocol command does not imply that a corresponding automation implementation exists.
- Any unsupported tool or workflow must be reported as UNKNOWN or BLOCKED, not simulated.

## 7. Current repository integration boundary

This migration package is being prepared on a separate documentation branch. PR #111 already proposes v1.0 adoption on a different branch. Do not merge this package until the relationship between PR #111 and v2.0 has been reviewed and the intended adoption sequence is approved.
