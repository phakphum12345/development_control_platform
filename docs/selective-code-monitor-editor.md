# Selective Code Monitor & Editor

**Status:** PARTIALLY IMPLEMENTED — dashboard document export and a scoped local .md/.txt writer exist; authenticated dashboard-to-writer integration, remote PR lifecycle control, and full recovery service remain pending.  
**Repository:** `phakphum12345/development_control_platform`  
**Scope boundary:** DCP owns the tool. Each enrolled project remains an independent repository with its own source, branches, CI, permissions, and evidence.

## 1. Goal

Add a project-aware tool that lets an authorized user explicitly select what the tool may inspect and, separately, what it may modify. It must support code monitoring, source inspection, proposed edits, controlled application of approved changes, complete Markdown/Roadmap/TXT generation, and resilient recovery from timeout or connection loss without treating all enrolled projects as one workspace.

## 2. Project isolation

- The project registry is opt-in. Never discover-and-enroll repositories automatically.
- Every operation is bound to one immutable project ID plus repository identity, selected ref, and path scope.
- Never copy, merge, or share source trees between projects as part of monitoring.
- Keep project-specific branches, PRs, CI runs, reports, generated documents, and audit records separate.
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

## 4. One-click document generation

Add a dedicated **Generate / Complete Document** action for supported text artifacts:
- Markdown (`.md`);
- Roadmap documents (Markdown roadmap template, with milestones, dependencies, status, acceptance criteria, and next actions);
- Plain text (`.txt`).

The user selects the project, target path, document type/template, and source scope. The action must:
1. Read only selected project files and explicitly selected evidence.
2. Build a structured outline and identify missing inputs, contradictions, stale status, and unverified claims.
3. Generate the complete document, not a truncated preview; if essential information is unavailable, mark it as TBD/UNKNOWN rather than inventing it.
4. Validate required headings/sections for the chosen template, internal links and paths where applicable, UTF-8 encoding, newline consistency, and absence of accidental secrets.
5. Show a preview and exact diff, target path, source references, and validation report before write approval.
6. Write through the controlled write pipeline only; never bypass project/path grants.
7. Read the file back from the target repository/workspace and compare its content digest with the intended output.
8. Report a verifiable result: file path, byte/line count, content digest, resulting commit SHA (if committed), and validation outcome.

For long documents, generation must be chunked or staged internally and assembled before the final write. Never publish a partial document as complete. A failed or interrupted generation leaves the previous file intact; temporary artifacts are clearly marked and safely cleaned up only after reconciliation. Re-running the same operation should be idempotent where possible and must not create duplicate commits or duplicate sections.

## 5. Monitoring and evidence

- Track selected branches, PR metadata, changed files, reviews, workflow runs, and job results where the configured provider permits.
- Bind every CI result to the exact full head SHA; a newer commit invalidates older evidence for the new head.
- Use only `PASS`, `FAIL`, `SKIPPED`, and `UNKNOWN` in gate summaries. Pending, inaccessible, missing, stale, or mismatched evidence is not PASS.
- Monitoring is read-only and cannot approve, merge, push, deploy, or change repository settings.
- Polling cadence and notification delivery are explicit per-project settings; no repository is monitored until enrolled.

## 6. Reliability, timeout, and connection recovery

Every mutating operation must use a durable operation record and a resumable state machine. Required safeguards:
- Create a unique operation/idempotency key before starting; persist project ID, target, base SHA, requested action, and current checkpoint.
- Use bounded timeouts, heartbeat/progress updates, cancellation, and an explicit overall deadline. A timeout must not be interpreted as proof that the remote operation failed.
- Retry only transient failures (network reset, rate limit, selected 5xx) with capped exponential backoff and jitter; respect provider retry guidance/Retry-After. Do not retry validation, permission, conflict, or other permanent errors blindly.
- Before retrying a write after a lost response, reconcile remote state using the operation key, commit SHA, content digest, branch, or PR identity. This prevents duplicate writes, commits, and pull requests.
- Resume from the last durable checkpoint after reconnect/restart. Do not restart the entire workflow if earlier steps are already verified.
- If remote state cannot be determined, stop in `UNKNOWN`, preserve evidence, and require reconciliation; never report PASS or issue a blind second mutation.
- Use bounded queues and concurrency limits per project; prevent two conflicting writes to the same path/ref from racing.
- Keep a durable event log with timestamps, attempt count, error category, checkpoint, and reconciliation outcome. Redact credentials and sensitive payloads.
- After recovery, revalidate permissions, project identity, target ref, and base SHA before continuing. A changed base invalidates prior approval.

## 7. Mandatory lifecycle checkpoints

Run and persist the relevant checks at every occurrence, not just once per session:

### After every file write

1. Confirm provider/local operation result and target path.
2. Re-read the exact file from the target ref/workspace.
3. Compare read-back content digest with the intended content digest.
4. Verify encoding, size, expected sections, and no unintended neighboring-file changes.
5. Capture commit SHA/blob SHA and audit event where applicable.
6. If any check fails or cannot be completed, report FAIL or UNKNOWN and stop dependent steps.

### Before opening a PR

- Verify repository identity, source branch, base branch, and exact head/base SHA.
- Confirm the intended diff contains only approved files and no prohibited deletions.
- Confirm required validation and CI evidence is current for the exact head SHA.
- Confirm PR title/body, reviewers, labels, and draft setting if configured.
- Check for an existing PR for the same head/base to avoid duplicates.
- Recheck user authorization for the PR-create action.

### After opening a PR

- Fetch the PR again and verify number, URL, state, head/base refs and SHAs, and changed-file summary.
- Confirm the PR points to the intended repository and branch.
- Fetch checks/reviews and record their exact SHA association.
- Persist the PR URL/number and lifecycle event. If the create response was lost, search/reconcile before creating another PR.

### Before merging a PR

- Require explicit merge authorization for that specific PR and current head SHA.
- Re-fetch PR state, mergeability, approvals/reviews, branch protection requirements, and CI checks.
- Require all applicable gates to be PASS; SKIPPED, pending, missing, stale, or UNKNOWN blocks merge.
- Confirm base SHA has not changed in a way that invalidates the reviewed diff.
- If any evidence changes, pause and request a fresh review/approval.

### After merging a PR

- Re-fetch PR and verify `merged=true`, merged timestamp, merge commit SHA, and target base branch.
- Fetch the merge commit and verify it is reachable from the intended base branch.
- Re-read changed files from the merged base and compare expected content/diff.
- Fetch post-merge CI for the exact merge commit SHA and record the result.
- Update roadmap/document status only from verified evidence. If merge state or post-merge checks cannot be verified, mark UNKNOWN and stop follow-on work.

### Before closing a PR without merge

- Verify PR number, repository, state, head/base refs, and current SHA.
- Distinguish closing without merge from merging; require explicit authorization for the close action.
- Record the reason and confirm no merge operation is being issued.

### After closing a PR

- Re-fetch and verify `state=closed` and `merged=false` for a non-merged close.
- If merged, classify it as merged rather than closed-without-merge.
- Record closed timestamp, actor/reason where available, final head/base SHA, and final checks.
- Reconcile any timeout before attempting another close; do not duplicate or misclassify the lifecycle action.

## 8. Architecture boundary

- **Dashboard:** project picker, separate Read and Write scope panels, document generator, source/diff viewer, proposal/approval view, monitoring timeline, operation recovery view.
- **Policy service:** authoritative project registry, scope grants, expiry/revocation, path validation, operation policy, audit events.
- **Job coordinator:** durable operation queue, idempotency keys, checkpoints, timeout/retry policy, reconciliation, and per-project concurrency controls.
- **Provider adapter:** server-side GitHub App/OAuth integration with least-privilege permissions. Browser receives no provider token.
- **Workspace adapter:** optional local workspace rooted at an explicitly approved directory; no arbitrary filesystem access.
- **Execution boundary:** analysis and tests run only in a bounded, isolated worker with resource limits. Do not execute repository code in the dashboard process.
- **Evidence store:** project-keyed records with immutable source identity, exact SHA references, document digests, and lifecycle checkpoints.

The existing static public-GitHub dashboard and local read-only MCP engine are not write authorization boundaries. They must remain read-only until a server-side owner-authenticated policy and audit path exists. UI labels or disabled buttons alone are not security controls.

## 9. Delivery sequence

1. **Inventory & threat model:** inspect current project registry, local auth proxy, GitHub App read-only adapter, MCP engine, runner, tests, and audit/evidence models.
2. **Read-only project scope:** add explicit per-project repository/ref/path selection and monitoring, with isolation tests.
3. **Document generator:** add Markdown/Roadmap/TXT templates, completeness validation, preview, and source/evidence traceability. Initially save only through a local controlled workspace or patch proposal.
4. **Durable job coordinator:** add idempotency keys, checkpoints, heartbeats, bounded retries, reconnect/resume, and unknown-state reconciliation.
5. **Write proposal workflow:** generate and validate patches in an isolated workspace; no apply action yet.
6. **Approval and apply:** add server-side authorization, exact-diff approval, stale-base rejection, no-delete policy, read-back verification, and audit.
7. **PR lifecycle controller:** add mandatory pre/post checks for open, merge, and close; keep each action separately authorized.
8. **Provider write adapter:** only after GitHub App permissions and backend controls are explicitly configured; feature branches only.
9. **Verification:** unit, API, browser, path traversal, cross-project isolation, permission-revocation, stale-SHA, timeout/reconnect, idempotency, concurrent-update, document-completeness, and PR lifecycle tests.
10. **Release gate:** document operational limits; require all applicable checks on the exact PR head SHA. No skipped or unknown check counts as pass.

## 10. Acceptance criteria

- [ ] Project enrollment is explicit; projects remain isolated.
- [ ] Read and write grants are separate, visible, revocable, and enforced server-side.
- [ ] Read-only mode cannot reach a write endpoint.
- [ ] One-click generation supports complete Markdown, Roadmap, and TXT artifacts with preview, validation, and source traceability.
- [ ] Incomplete or unavailable facts are marked TBD/UNKNOWN rather than invented.
- [ ] Every file write is followed by read-back and digest verification.
- [ ] Timeouts and disconnects resume/reconcile safely without duplicate writes, commits, or PRs.
- [ ] Unknown remote outcomes fail closed and are never reported as PASS.
- [ ] Writes are restricted to approved paths and feature branches/workspaces.
- [ ] Deletion, force-push, merge, and deploy are unavailable by default.
- [ ] Every write requires approval bound to exact diff digest and base SHA.
- [ ] PR open, merge, and close each have explicit preconditions and post-action verification.
- [ ] Stale SHA, changed scope, revoked grant, or cross-project path access fails closed.
- [ ] Browser never receives provider credentials.
- [ ] CI/evidence is SHA-bound and missing/pending/skipped evidence is never reported as PASS.
- [ ] Audit records can be independently inspected and correlate to the applied commit and PR lifecycle.
- [ ] Tests cover allowed and denied paths, project isolation, retries, recovery, and all lifecycle checkpoints.

## 11. Current limitations / non-claims

The dashboard now has a one-click Markdown/Roadmap/TXT generator that previews, checks for a small set of credential patterns, computes a content digest, and requests a browser download. Browser download is not repository persistence and cannot prove disk read-back. A separate local Python writer supports .md/.txt files inside one explicitly approved workspace, path-prefix grants, expected-base SHA checks, an external SQLite operation journal, idempotency, atomic replacement, and post-write read-back digest verification. It does not expose a network endpoint or GitHub write actions. The Dashboard now also includes a read-only PR Lifecycle Checkpoints panel for before/after open, merge, and close states. It re-fetches PR metadata, current head SHA, reviews, checks, and branch-protection evidence where available; missing evidence remains UNKNOWN. It does not execute lifecycle mutations. Dashboard-to-local-writer integration, authenticated server-side policy, durable distributed job coordination, webhook/automatic lifecycle event hooks, remote write access, and end-to-end execution of the new tests remain pending. The existing MCP adapter remains read-only.
