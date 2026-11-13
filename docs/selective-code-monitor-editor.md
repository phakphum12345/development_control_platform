# Selective Code Monitor & Editor

**Status:** DRAFT — design baseline only; implementation and security acceptance are pending.  
**Repository:** `phakphum12345/development_control_platform`  
**Scope boundary:** DCP owns the tool. Each enrolled project remains an independent repository with its own source, branches, CI, permissions, and evidence.

## 1. Goal

Add a project-aware tool that lets an authorized user explicitly select what the tool may inspect and, separately, what it may modify. It must support code monitoring, source inspection, proposed edits, and controlled application of approved changes without treating all enrolled projects as one workspace.

## 2. Project isolation

- The project registry is opt-in. Never discover-and-enroll repositories automatically.
- Every operation is bound to one immutable project ID plus repository identity, selected ref, and path scope.
- Never copy, merge, or share source trees between projects as part of monitoring.
- Keep project-specific branches, PRs, CI runs, reports, and audit records separate.
- Revalidate repository identity and selected branch/ref before every write; do not trust a stale browser selection.
- Reject path traversal, symlinks escaping the approved workspace, ambiguous paths, and paths outside the granted scope.

## 3. Separate capabilities

### Read scope

The user explicitly selects:
- GitHub repository or approved local workspace;
- branch/tag/commit (full SHA for evidence-bound operations);
- one or more directories/files, with optional read-only repository metadata;
- permitted inspection operations (source view, diff, tests/CI metadata, dependency manifests).

Read scope does not imply write permission. Private repository access is only through a configured authenticated server-side integration. Never place GitHub credentials in browser storage or JavaScript.

### Write scope

Write is OFF by default and is separate from read scope. The user must explicitly grant:
- target project and exact branch/workspace;
- allowed file paths or directory prefixes;
- allowed operation types (create/update; deletion remains disabled);
- expiry/revocation boundary and maximum patch size.

The tool must:
1. Generate a proposed patch in an isolated working copy or dedicated feature branch.
2. Validate changed paths against the granted write scope on the server.
3. Show a complete diff, affected-file list, and validation results.
4. Require explicit human approval of that exact diff and base SHA.
5. Recheck the base SHA and permissions before applying; stale approvals are invalid.
6. Record the actor, project, base/head SHA, file list, diff digest, approval, result, and timestamp.
7. Re-read the resulting files/commit and report verifiable evidence.

No direct default-branch writes, force-push, history rewrite, merge, release, or deploy. Commit/push/PR creation must be distinct actions with separate confirmation and server-side authorization. Merge and deploy are never implicit consequences of approving a patch.

## 4. Monitoring and evidence

- Track selected branches, PR metadata, changed files, reviews, workflow runs, and job results where the configured provider permits.
- Bind every CI result to the exact full head SHA; a newer commit invalidates older evidence for the new head.
- Use only `PASS`, `FAIL`, `SKIPPED`, and `UNKNOWN` in gate summaries. Pending, inaccessible, missing, stale, or mismatched evidence is not PASS.
- Monitoring is read-only and cannot approve, merge, push, deploy, or change repository settings.
- Polling cadence and notification delivery are explicit per-project settings; no repository is monitored until enrolled.

## 5. Architecture boundary

- **Dashboard:** project picker, separate Read and Write scope panels, source/diff viewer, proposal/approval view, monitoring timeline.
- **Policy service:** authoritative project registry, scope grants, expiry/revocation, path validation, operation policy, audit events.
- **Provider adapter:** server-side GitHub App/OAuth integration with least-privilege permissions. Browser receives no provider token.
- **Workspace adapter:** optional local workspace rooted at an explicitly approved directory; no arbitrary filesystem access.
- **Execution boundary:** analysis and tests run only in a bounded, isolated worker with resource limits. Do not execute repository code in the dashboard process.
- **Evidence store:** project-keyed records with immutable source identity and exact SHA references.

The existing static public-GitHub dashboard and local read-only MCP engine are not write authorization boundaries. They must remain read-only until a server-side owner-authenticated policy and audit path exists. UI labels or disabled buttons alone are not security controls.

## 6. Delivery sequence

1. **Inventory & threat model:** inspect current project registry, local auth proxy, GitHub App read-only adapter, MCP engine, runner, tests, and audit/evidence models.
2. **Read-only project scope:** add explicit per-project repository/ref/path selection and monitoring, with isolation tests.
3. **Write proposal workflow:** generate and validate patches in an isolated workspace; no apply action yet.
4. **Approval and apply:** add server-side authorization, exact-diff approval, stale-base rejection, no-delete policy, and audit read-back.
5. **Provider write adapter:** only after GitHub App permissions and backend controls are explicitly configured; feature branches only.
6. **Verification:** unit, API, browser, path traversal, cross-project isolation, permission-revocation, stale-SHA, concurrent-update, and negative authorization tests.
7. **Release gate:** document operational limits; require all applicable checks on the exact PR head SHA. No skipped or unknown check counts as pass.

## 7. Acceptance criteria

- [ ] Project enrollment is explicit; projects remain isolated.
- [ ] Read and write grants are separate, visible, revocable, and enforced server-side.
- [ ] Read-only mode cannot reach a write endpoint.
- [ ] Writes are restricted to approved paths and feature branches/workspaces.
- [ ] Deletion, force-push, merge, and deploy are unavailable by default.
- [ ] Every write requires approval bound to exact diff digest and base SHA.
- [ ] Stale SHA, changed scope, revoked grant, or cross-project path access fails closed.
- [ ] Browser never receives provider credentials.
- [ ] CI/evidence is SHA-bound and missing/pending/skipped evidence is never reported as PASS.
- [ ] Audit records can be independently inspected and correlate to the applied commit.
- [ ] Tests cover both allowed and denied paths, including project isolation.

## 8. Current limitations / non-claims

This document is a design baseline, not an implemented capability. The current DCP dashboard describes itself as read-only and does not provide Git write actions. The existing local MCP engine exposes bounded read/inspect/diff/copy-preview operations only. No claim is made that selective writing, server-side authorization, durable audit, or private-repository write access currently exists.
