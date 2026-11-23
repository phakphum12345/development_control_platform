# DCP-CEEP Continuity Ledger

**Captured:** 2026-11-14  
**Repository:** phakphum12345/development_control_platform  
**Operational protocol:** DCP-CEEP v1.0 — adopted  
**v2.0 status:** Proposal only; NOT adopted.

## Current repository baseline

- Default branch: main
- Main SHA at WP-18 branch creation: ef3bf7e3522119ebbd3a41de693cee254e1ea7cf
- PR #110, #111, #112, #113 and #114: CLOSED / MERGED.
- PR #114 merge commit: ef3bf7e3522119ebbd3a41de693cee254e1ea7cf.
- PR #114 exact head: 26ca10364cd5991e2225777d769d90836bde6dcb.
- PR #114 exact-head CI: Local-first Minimal Emulator PASS; Validate Control Plane PASS; Cross-platform Recovery Acceptance PASS.
- No deployment was performed.

## Completed work packages

| Work Package | State | Evidence / boundary |
|---|---|---|
| WP-M16 — Flutter executor cross-platform acceptance | PASS | PR #110 merged as b2656749749b788b627e0d1ae004b11b69d2a4e1; GitHub-hosted Ubuntu/Windows CI only, not proof of user's local SDK or host cleanup. |
| WP-PROTOCOL — DCP-CEEP v1.0 adoption | PASS | PR #111 merged as 4633b692399745796a9da7b0f18a30481bed88b2; v1.0 is operational. |
| WP-TERMINAL-AUTH — app-authorized Terminal workflow | IMPLEMENTED / EXECUTION BLOCKED | PR #112 merged as b0a2cd0d542491886a529666909024af1fb64ced. All seven built-in templates remain disabled; no OS sandbox is claimed. |
| WP-CEEP-V2-PROPOSAL | INTEGRATED / NOT ADOPTED | PR #113 merged as e008844d8c6e6b15c71b7bf36f00f42e66233387. |
| WP-17 — Terminal Git helper and grant retry hardening | PASS — merged | PR #114 merged as ef3bf7e3522119ebbd3a41de693cee254e1ea7cf. Three exact-head workflows passed on 26ca10364cd5991e2225777d769d90836bde6dcb. This is not OS isolation. |

## Current work package

### WP-18 — OS-level Terminal isolation

- Branch: feat/wp18-os-isolation-contract
- Base SHA: ef3bf7e3522119ebbd3a41de693cee254e1ea7cf
- Initial branch commits:
  - 40caffdb84b42d1fb17e4fa081d7e137e617c14e — fail-closed platform isolation contract
  - f830218ecdddeea292e13214c7027a4eec0038ae — contract tests
  - 880e3705efe777d7f9f4525c1aa46bd51a5abdbc — platform design and acceptance document
- Implemented so far:
  - platform backend assessment for Windows, Linux and macOS;
  - Linux bwrap presence is reported only as READY_FOR_ACCEPTANCE, not as enforced isolation;
  - Windows AppContainer/LPAC and macOS signed App Sandbox helper remain BLOCKED;
  - require_verified_isolation rejects incomplete filesystem, network or process-tree claims and is now called by TerminalScriptExecutor before any process launch;
  - executor unit tests use an explicit test-only VERIFIED assessment to retain coverage of process handling; production host verification remains absent;
  - tests assert fail-closed behavior.
- Not yet implemented: actual OS process launchers, mount/capability policies, native helper signing, seccomp policy, host acceptance and process cleanup verification.
- CI was triggered on earlier head 8e5180376c3b8ea843903d4755e75fe5063969b7 (runs 43530605448 Validate Control Plane, 43530605527 Cross-platform Recovery Acceptance, 43530605511 Local-first Minimal Emulator). These runs are stale after subsequent executor-gate and documentation commits; they are not current-head evidence.
- Earlier CI on head 19bb0b25b6474cd3dff8658bf43914aef843b58e failed across Recovery (Linux/Windows), Validate Control Plane, Linux Minimal Emulator and Windows dynamic-port integration. Log analysis isolated the common failure to test_terminal_template_runs_only_after_grant_in_the_actual_registered_project_workspace: the new production isolation gate correctly blocked execution, while this pre-existing integration test still expected a successful process run.
- Fixed the test boundary on commit 292f539d430f29472247a8701aae7426ce7343aa: the test now injects an explicit test-only VERIFIED assessment to exercise grant/workspace/pipeline behavior, with an explicit reason that this is not production isolation evidence. Production assessment remains fail-closed. Exact-head CI for 292f539d430f29472247a8701aae7426ce7343aa is pending/UNKNOWN until GitHub reports checks.
- No PR has yet been opened for WP-18.

## Outstanding operational gates

| Gate | State | Required evidence |
|---|---|---|
| Actual Windows-host acceptance of supported launcher and Dashboard → Local Auth Proxy → Gateway owner flow | UNKNOWN | Direct run on supported Windows host with captured results |
| Independent process-tree termination | UNKNOWN | OS-level evidence descendants are terminated after timeout/cancel |
| Workspace cleanup after interruption | UNKNOWN | Independent filesystem inspection and recovery evidence |
| Terminal OS isolation / network restriction | BLOCKED | Verified platform-specific launcher and adversarial host acceptance |
| Terminal built-in template enablement | BLOCKED | Keep all seven built-ins disabled until every required security and host gate passes |

## Next exact actions

1. Add integration only behind a verified isolation adapter; fail closed if unavailable.
2. Implement Linux bubblewrap launcher with explicit runtime mounts, assigned workspace, per-job scratch, network namespace denial and seccomp policy; verify arguments against upstream behavior.
3. Implement Windows AppContainer/LPAC native helper; Job Objects alone are insufficient.
4. Implement macOS signed App Sandbox helper or leave macOS unsupported and blocked.
5. Add adversarial filesystem/network/process tests and actual-host acceptance workflows.
6. Verify process-tree termination and scratch cleanup after success, timeout, cancel, lease loss and Runner shutdown.
7. Reconcile the ledger and exact-SHA CI after every branch update.
8. Do not enable templates or merge WP-18 without current exact-head gates and explicit user authorization.

## Resume rule

Never infer PASS from missing, skipped, stale or different-SHA evidence. Re-check repository and exact current head before resuming after interruption. Preserve all branches and files; no deletion or deployment is authorized by this checkpoint.


## 2026-11-14 — WP-00 source-driven inventory checkpoint

- Latest verified main SHA for this inventory: `62d72bddd028399d0b96cd9c2f6e3b16a704b758` (PR #115 merge commit).
- PR #115 is merged; it adds the fail-closed isolation contract, not a platform sandbox launcher.
- Recursive tree: 289 entries / 265 blobs; 78 files under tools/, 86 under tests/, 58 under docs/, 7 GitHub Actions workflow files.
- Open PR count and open issue count were both zero at baseline.
- Created branch `work/wp00-remaining-inventory-wp18a-linux-isolation` from the exact main SHA above.
- Added `docs/DCP-REMAINING-WORK-INVENTORY.md` in commit `34499a2816e1bba514f4e838efbfda72619b259b`.
- Inventory currently groups 22 WPs (WP-00A–D, WP-18A–E, WP-19–WP-31). This is a work-package count, NOT the final atomic task count. WP-00 source/test/API/Dashboard traceability remains IN_PROGRESS.
- Source inspection confirmed the artifact upload/download SHA-256 code and tamper tests already exist; remaining work is end-to-end provenance acceptance, not reimplementation of basic hashing.
- Source inspection confirmed Terminal executor calls the fail-closed verifier before workspace resolution/process launch; no production platform launcher exists. All seven templates remain disabled.
- Current branch head after inventory document: `34499a2816e1bba514f4e838efbfda72619b259b`.
- Next exact action: continue WP-00B/00C source-to-test mapping, then implement Linux-only WP-18A behind a fail-closed boundary. Do not merge without explicit approval.


## 2026-11-14 — WP-18A Linux launcher builder checkpoint

- Branch: `work/wp00-remaining-inventory-wp18a-linux-isolation`
- Base SHA: `62d72bddd028399d0b96cd9c2f6e3b16a704b758`
- Current branch head before PR creation: `e4205ef7465c3f7ed2954d64770616f078937118`
- Added `tools/local_runner_agent/linux_sandbox.py`: Linux-only bubblewrap command builder, explicit read-only workspace, separate scratch, private user/PID/IPC/UTS/network namespaces, cleared environment, dropped capabilities, disabled nested user namespaces, and a seccomp BPF network-deny policy.
- Added `tests/test_linux_sandbox.py`; added the test invocation to Cross-platform Recovery Acceptance.
- Updated `docs/DCP-TERMINAL-OS-ISOLATION.md` and `docs/DCP-REMAINING-WORK-INVENTORY.md`.
- Important limitation: this is a command builder and test coverage only. It is not yet wired into TerminalScriptExecutor; no bubblewrap runtime or adversarial host acceptance has been executed. Linux must remain BLOCKED for production execution; all seven templates remain disabled.
- CI exact-head status: UNKNOWN until PR checks complete.
- Next action: open a draft PR for review/CI, then fix any CI failures. After CI, integrate behind the existing fail-closed verifier and run Linux host acceptance. No merge authorized.


## 2026-11-14 — WP-00 first-pass mapping and WP-18A CI checkpoint

- Baseline remains `main` SHA `62d72bddd028399d0b96cd9c2f6e3b16a704b758`.
- PR #116: [feat(terminal): add Linux bubblewrap launcher builder and remaining-work inventory](https://github.com/phakphum12345/development_control_platform/pull/116), OPEN / DRAFT / NOT MERGED.
- PR #116 base SHA: `62d72bddd028399d0b96cd9c2f6e3b16a704b758`.
- Branch: `work/wp00-remaining-inventory-wp18a-linux-isolation`; branch head before this ledger update: `b7dbfc087ac4a45c67162782c49ede2ba751df65`.
- Current branch includes source inventory, first-pass API and Dashboard mapping, 21 Dashboard view IDs, 86 baseline test-file list, 24 requirement groups, categorized docs index, implementation status and traceability documents.
- Added `docs/INDEX.md`, `docs/IMPLEMENTATION-STATUS.md`, `docs/REQUIREMENTS-TRACEABILITY.md`. WP-00B/00C remain IN_PROGRESS because per-file entrypoint mapping, complete method/path/auth matrix, per-view handler tracing and per-test-function mapping remain.
- Corrected baseline test grouping: 86 files total; Local Runner/Projects has 14 files.
- Appended dated reconciliation notes to `docs/DCP-IMPLEMENTATION-ROADMAP.md` and `docs/DCP-MASTER-FEATURE-BACKLOG.md`. Historical stale WP-17 text is not erased; it is explicitly marked stale by a newer checkpoint.
- WP-18A builder now uses narrow read-only runtime mounts (/usr/bin and shared-library trees), read-only workspace, separate scratch, private user/PID/IPC/UTS/network namespaces, capability drop, disabled nested user namespaces and seccomp denial of socket APIs/io_uring_setup.
- Added a real bubblewrap runtime test to the Ubuntu CI path; it checks unmounted host-path invisibility, workspace read-only behavior, scratch writes and socket denial. This is CI-host acceptance only, not the user's Linux host.
- Latest observed CI on earlier head `b3094c73c5299ae20fe146442fd267aa79bc4385`: Validate Control Plane IN_PROGRESS; Local-first Minimal Emulator IN_PROGRESS; Cross-platform Recovery Acceptance QUEUED. Exact-head results for the newer docs/ledger commits must be rechecked.
- Builder is not yet integrated into TerminalScriptExecutor. Linux production execution remains blocked; Windows AppContainer/LPAC remains BLOCKED; macOS remains BLOCKED; all seven templates remain disabled.
- Next exact action: verify CI on the final branch head, fix any failures, then integrate the Linux launcher behind the existing verifier and run actual-host adversarial acceptance. Do not merge without explicit user authorization.


## 2026-11-14 — PR #116 final pre-CI checkpoint

- PR #116 remains OPEN / DRAFT / NOT MERGED.
- Exact base SHA: `62d72bddd028399d0b96cd9c2f6e3b16a704b758`.
- Branch: `work/wp00-remaining-inventory-wp18a-linux-isolation`.
- Branch head before this checkpoint: `42a8b4b0286ec34d70afca80730e939ea9be0619`.
- Changed files: 11 — workflow, continuity ledger, roadmap, backlog, remaining-work inventory, Terminal OS Isolation doc, Implementation Status, docs index, Requirements Traceability, Linux sandbox tests and Linux sandbox builder.
- Baseline inventory is now documented with 22 grouped WPs, 78 tools, 86 test files, 58 docs, 7 workflows, 21 Dashboard views and 24 requirement groups. The atomic task count remains UNKNOWN until detailed per-file and per-test-function trace is complete.
- WP-18A builder now accepts only a fixed allowlist of sanitized Git/runtime environment variables inside the sandbox; it does not inherit the host environment wholesale.
- Exact-head checks on the previous code head `6a0210b557af258125521124949034481f2bb044` were in progress at last inspection. The current documentation-only head needs fresh PR checks to satisfy the exact-SHA rule.
- No merge authorization exists. Keep PR #116 draft; keep all seven Terminal templates disabled.
- Next exact action: trigger all required workflows for documentation/checkpoint changes, then verify every check on the final head SHA. If checks pass, continue the executor integration as a separate WP-18A implementation slice; do not merge until reviewed and approved.


## 2026-11-14 — WP-18A executor integration and WP-18C recovery continuation

- Repository: `phakphum12345/development_control_platform`; protocol: DCP-CEEP v1.0.
- PR #116 remains OPEN / DRAFT / NOT MERGED; exact head `c811f0fee91f5ad43850359f4adfae506c3a502a`; its three exact-head workflows passed.
- PR #117 — Linux bubblewrap executor integration — remains OPEN / DRAFT / NOT MERGED, stacked on PR #116's branch. Exact head `45b1650e740b4f4667ca21c793fab0d670c84a73`.
- PR #117 exact-head checks: Cross-platform Recovery Acceptance #167 PASS; Validate Control Plane #745 PASS; Local-first Minimal Emulator #531 PASS. Windows runner acceptance matrix SKIPPED because no eligible self-hosted acceptance Runner was available; SKIPPED is not PASS.
- PR #117 integrates the Linux bubblewrap launcher into TerminalScriptExecutor, passes the seccomp FD, pins bubblewrap/workload executables to /usr/bin, performs Git filter discovery inside the sandbox, and retains the VERIFIED gate. All seven built-in templates remain disabled. No user-host acceptance is claimed.
- Started stacked branch `work/wp18c-terminal-recovery` from PR #117 head `45b1650e740b4f4667ca21c793fab0d670c84a73`.
- WP-18C implementation in progress: runner-authenticated cleanup status endpoint; conservative reconciliation only for old terminal_script workspaces with matching ownership and Gateway `cleanup_safe=true`; UNKNOWN, lease-expired, active, mismatched, recent, unavailable and preview-retained workspaces are preserved.
- Added Linux-only detached-child timeout test using bubblewrap parent-death/PID-namespace containment. Exact-head CI for this WP-18C branch has not yet run.
- Current WP-18C branch head: `3fb72e498d7b3b1decda44a16f054532e04ce50f`.
- No merge, deployment, template enablement or deletion is authorized. Continue with tests, exact-head CI, Draft PR and evidence reconciliation; do not merge without separate explicit approval.


## 2026-11-14 — WP-18C exact-head CI completion

- PR #118: [feat(terminal): add conservative WP-18C recovery and descendant cleanup](https://github.com/phakphum12345/development_control_platform/pull/118), OPEN / DRAFT / NOT MERGED.
- PR #118 is stacked on PR #117's branch `work/wp18a-linux-executor-integration`; base SHA `45b1650e740b4f4667ca21c793fab0d670c84a73`.
- Code/test head before this ledger-only update: `a8a79cdf4f0a82b9dc55419f79fc0d8386de8554`.
- Exact-head CI on `a8a79cdf4f0a82b9dc55419f79fc0d8386de8554`:
  - Cross-platform Recovery Acceptance #168: PASS (Ubuntu and Windows jobs).
  - Validate Control Plane #746: PASS.
  - Local-first Minimal Emulator #532: PASS.
  - Windows runner acceptance matrix: SKIPPED; no eligible self-hosted host acceptance Runner. SKIPPED is not PASS.
- Linux executor suite: 23 tests PASS, including actual bubblewrap executor launch with seccomp FD inheritance and a forked child that calls `setsid()`; the child did not survive launcher termination.
- Linux sandbox suite: 5 tests PASS, including actual bubblewrap filesystem/network/scratch boundary test.
- Pipeline E2E verifies Gateway cleanup status is available only to the owning Runner. Workspace reconciliation tests verify that UNKNOWN, recent, mismatched, unavailable and preview-retained workspaces are preserved.
- WP-18C remains PARTIAL: automatic cleanup is limited to Gateway-attested terminal Terminal jobs. UNKNOWN and LEASE_EXPIRED workspaces are intentionally preserved; this is not a universal orphan cleaner. Windows AppContainer/LPAC and macOS helper remain BLOCKED.
- PR #117 remains OPEN / DRAFT / NOT MERGED; PR #116 remains its base dependency. No branch has been merged to main.
- No user-host acceptance, deployment, template enablement or deletion was performed or authorized. After this ledger-only update, re-check exact-head CI on the new branch SHA before treating it as current evidence.


## 2026-11-14 — WP-18D exact-head CI completion

- PR #119: [test(terminal): add Linux adversarial sandbox acceptance](https://github.com/phakphum12345/development_control_platform/pull/119), OPEN / DRAFT / NOT MERGED.
- PR #119 code/test head with completed CI: `57399f94d8ece4c706eb373ec74f9c3bcda3e61f`.
- Exact-head workflows on that code/test head:
  - Cross-platform Recovery Acceptance #170: PASS (Ubuntu and Windows jobs).
  - Local-first Minimal Emulator #534: PASS (Linux and Windows jobs).
  - Validate Control Plane #748: PASS.
  - Windows runner acceptance matrix: SKIPPED; no eligible self-hosted host acceptance Runner. SKIPPED is not PASS.
- Ubuntu host-acceptance harness: PASS on the ephemeral GitHub-hosted runner, 5/5 tests, 0 skipped, 0 failures, 0 errors. Evidence: Bubblewrap 0.11.1; Linux 7.0.0-1016-aws; x86_64; UID/GID 1001. This is CI-host evidence only.
- WP-18D remains PARTIAL until the harness is run on the actual target Linux host. Windows AppContainer/LPAC remains BLOCKED and user-host acceptance remains UNKNOWN.
- This checkpoint is followed by a small evidence-schema refinement that records both the harness interpreter version and the exact /usr/bin Python runtime versions; re-check CI against the resulting new head.
- PR #116, #117 and #118 remain OPEN / DRAFT / NOT MERGED. No merge to main, deployment or Terminal template enablement is authorized.


## 2026-11-14 — WP-18D exact-head evidence refinement accepted

- PR #119 code/test head `a497117adfcdb68f9e6a52b385f28fbec21ec621`: all exact-head workflows PASS.
- Cross-platform Recovery Acceptance #171: PASS (Ubuntu and Windows).
- Local-first Minimal Emulator #535: PASS (Linux and Windows).
- Validate Control Plane #749: PASS.
- Linux host acceptance harness on the ephemeral Ubuntu CI host: PASS, 5/5, 0 skipped, 0 failures, 0 errors. Exact evidence: Bubblewrap 0.11.1; Linux 7.0.0-1016-aws; x86_64; UID/GID 1001; harness Python 3.12.16; Terminal runtime Python 3.14.4; sandbox test Python 3.14.4.
- Windows runner acceptance matrix: SKIPPED; no eligible self-hosted host acceptance Runner. No target Windows or Linux host acceptance is claimed.
- PR #119 remains OPEN / DRAFT / NOT MERGED; PR #118 remains OPEN / DRAFT / NOT MERGED; PR #117 and #116 remain OPEN / DRAFT / NOT MERGED. These are stacked dependencies; do not merge a child before its base.
- WP-18D is PARTIAL pending the target Linux host run. WP-18B Windows native process isolation and LPAC remain BLOCKED pending implementation and host acceptance. Terminal templates remain disabled.
- This checkpoint follows code/test head `a497117adfcdb68f9e6a52b385f28fbec21ec621`; re-check exact-head CI on the resulting checkpoint commit before treating it as current.


---

## 2026-11-23 — WP-00 live repository audit checkpoint

- Canonical repository: `phakphum12345/development_control_platform`.
- Canonical branch baseline: `main` at `eaa9ceb91088c39b90d9b11b3817dc793e40005a`.
- Audit branch: `docs/wp00-live-audit-20261123`.
- Live audit document: `docs/DCP-LIVE-REPOSITORY-AUDIT-2026-11-23.md`.
- Live metadata snapshot before opening this audit's delivery PR: 5 open PRs (#149, #150, #151, #152, #138); 0 open issues; 162 branches (100 + 62, final cursor empty). After opening PR #153, the live open-PR count is 6.
- Same-repository PR heads and workflow evidence were refreshed. PR #149's hosted PSEC probe workflow is green only because the expected BLOCKED result is informational; the job log explicitly reports PSEC state BLOCKED and missing filesystem/network-ingress capabilities. Its optional Windows runner acceptance is SKIPPED.
- PR #150's 2026-11-19 audit set is still a candidate PR, not current-main documentation. Its named baseline `985a78d5fba459c8a0cbcf47e5d00a858c6e6228` predates current main `eaa9ceb91088c39b90d9b11b3817dc793e40005a`.
- PR #151 and #152 exact-head hosted workflows passed; optional Windows runner acceptance is SKIPPED. Static Dashboard mapping and passing CI are not full operational acceptance.
- WP-00 live metadata refresh is recorded. Full recursive-tree inventory, current-main source/API/Dashboard/test traceability, review-thread audit and platform host acceptance remain IN_PROGRESS / UNKNOWN.
- No main branch changes, merges, deployment, release, Terminal template enablement, cloud provisioning or destructive cleanup were performed.
- Next exact action: complete current-main WP-00A recursive tree and file inventory, then reconcile WP-00B/00C/00D evidence on this branch. Keep PRs Draft/HOLD until review and required acceptance gates are satisfied.


## 2026-11-23 — Master Command crosswalk and WP-00D checkpoint

- Canonical repository: phakphum12345/development_control_platform; canonical branch: main.
- Exact main audit baseline: eaa9ceb91088c39b90d9b11b3817dc793e40005a.
- Audit PR: #153, branch docs/wp00-live-audit-20261123, Draft/HOLD.
- Latest audit commit: fa853c2340ef13aa7044a69d699766f74c0ab947.
- Re-read the user's complete Master Engineering Command. Required lifecycle remains READ → ANALYZE → MODIFY → TEST → AUDIT → MERGE → VERIFY → FOLLOW-UP. This authorization does not include merge, deployment, Terminal enablement or release.
- Appended a 24-requirement-to-WP/source/test/acceptance crosswalk and dependency sequence to docs/DCP-LIVE-REPOSITORY-AUDIT-2026-11-23.md.
- Clarified that WP-01–17 are not yet atomically decomposed into independently verified exit criteria in the existing inventory; do not infer PASS for individual WPs from grouped subsystem evidence.
- Reconciled stale audit baseline labels: docs/IMPLEMENTATION-STATUS.md, docs/REQUIREMENTS-TRACEABILITY.md and docs/DCP-REMAINING-WORK-INVENTORY.md still identify 62d72bddd028399d0b96cd9c2f6e3b16a704b758 / 2026-11-14. Their counts remain historical and must not be silently relabelled as current-main.
- PR #153 exact-head CI before the latest documentation update (head 22c34056cf65fcc7db670deac3a8a5a576bb9ec5): Recovery Ubuntu PASS; Validate Control Plane validate and Windows dynamic-port jobs IN PROGRESS; Recovery Windows and both Emulator jobs QUEUED; self-hosted Windows acceptance SKIPPED. This evidence is stale for the new head fa853c2340ef13aa7044a69d699766f74c0ab947; recheck exact-head workflows.
- WP-00 state: 00A PASS for recursive path enumeration; 00B PARTIAL; 00C PARTIAL; 00D PARTIAL/IN PROGRESS; WP-31 NOT STARTED.
- No source code, runtime configuration, workflow, branch settings or production resources changed. No PR was merged, no deployment/release occurred, and all seven Terminal templates remain disabled.
- Next: poll CI for exact head fa853c...; continue atomic WP-01–17 decomposition and full route/test/workflow trace; then address documented high-risk PR review findings in isolated PR scope only after full READ/ANALYZE.


## 2026-11-23 — PR lineage and exact-head refresh

- Audit branch latest source commit before this ledger update: bba5b2ff5254fc1441f5d72e3f1c0e51e00224c9.
- PR #153 remains OPEN / DRAFT / HOLD, base main at eaa9ceb91088c39b90d9b11b3817dc793e40005a.
- Refreshed live metadata for PRs #138, #144, #149, #150, #151, #152 and #153.
- PR #144 is CLOSED/MERGED into feature base work/wp18b1-windows-psec-filesystem-authorization, not main. PR #138 remains OPEN and mergeable=false with a 140-file diff; do not merge wholesale.
- PRs #149–#152 remain OPEN/DRAFT. PR #152 remains HOLD for parent-directory DACL, two-file transaction/recovery, atomic replacement proof and failure-injection test gaps.
- Appended PR lineage clarification and exact-head workflow status to the live audit.
- CI evidence recorded for then-current audit head c51d46b... was all queued at observation, except the optional self-hosted Windows runner acceptance job, which was skipped. This evidence is now stale because the audit document and this ledger create new commits; poll the exact latest head.
- No source/runtime/workflow changes, no merge, deployment, release, Terminal enablement or destructive cleanup.


## 2026-11-23 — WP-00D append-only reconciliation of operating documents

- Preserved the 2026-11-14 historical baseline and appended current-main reconciliation sections on the audit branch:
  - docs/IMPLEMENTATION-STATUS.md — commit 301e8bab873e16476783c594db7530ebe91c3714
  - docs/REQUIREMENTS-TRACEABILITY.md — commit 243b5fff5a34e70cc54d5eb9969facda5876052b
  - docs/DCP-REMAINING-WORK-INVENTORY.md — commit dac150b188daef88bb545a3f5e68c445373989d5
- Added section 21 to docs/DCP-LIVE-REPOSITORY-AUDIT-2026-11-23.md (commit fd2e8c76c480f04611ca89a2a63bd5894fcc0c2d) to record those exact file updates.
- docs/INDEX.md on the audit branch already links the live audit.
- No old historical counts were deleted or relabelled. Current 340-file tree and 117 test-path count are tied to main SHA eaa9ceb... and their explicit counting rules.
- WP-00D advances to PARTIAL: three operating docs now carry an append-only current-main reconciliation. Atomic WP-01–17 exit criteria and complete API/test/handler trace remain open.
- Current audit branch head is fd2e8c76c480f04611ca89a2a63bd5894fcc0c2d before this ledger update. Recheck exact-head CI after the next commit.


## 2026-11-23 — branch protection visibility limitation

- Live audit appended section 22 on branch protection visibility (audit commit 3083e8d94b8b264c51dfd85329edc667591529c9).
- Repository rulesets API returned an empty list. Classic branch protection API returned HTTP 403 Resource not accessible by integration.
- Branch protection and required-status-check enforcement therefore remain UNKNOWN / NOT VERIFIED. An authorized repository administrator must inspect repository Settings → Branches / Rulesets before any merge decision.
- This check does not authorize merge; PR #153 remains Draft/HOLD.


## 2026-11-23 — WP-01 API security acceptance decomposition

- Created docs/DCP-WP01-API-SECURITY-ACCEPTANCE.md (commit 9415dde8fcb560d526c3c09775b6f475ce86441b).
- Added an index entry to docs/INDEX.md (commit 0d216dcd50d4f7ecec0e4048f75e7922951308af).
- Decomposed WP-01 into 16 atomic API security acceptance items covering signed Proxy identity, CSRF/same-origin, body parsing, role checks, Proxy GET/POST/DELETE allowlists, unsupported verbs, idempotency, response headers, Gateway/Proxy parity, query/path canonicalization and Runner credentials.
- Inspected Gateway source and Local Auth Proxy source at main SHA eaa9ceb91088c39b90d9b11b3817dc793e40005a, plus three representative authorization/route test files.
- Explicit gaps recorded: exhaustive method/path/query/body/role/CSRF/idempotency matrix; unsupported PUT/PATCH/OPTIONS semantics; encoded path and duplicate-query edge cases; full response status/header matrix; runner credential replay/rotation coverage.
- No runtime source or test code changed. WP-01 remains IN_PROGRESS; this is a source/test trace and test plan, not acceptance.
- Exact-head CI must be refreshed after these commits. Previous CI observations on c0bcf213... are not transferable.

## 2026-11-23 — WP-01A source dispatch inventory

- Added `WP-01A` to `docs/DCP-WP01-API-SECURITY-ACCEPTANCE.md` in commit `15298ffc67648050a9ee217f22468c713f823ac7`.
- Static source review pinned the main-branch Gateway and Proxy source blobs and enumerated explicit HTTP handler methods and dispatch families.
- Gateway explicitly implements GET/POST/DELETE; Proxy explicitly implements GET/POST/DELETE/OPTIONS. Absence of custom PUT/PATCH handlers is not treated as proof of externally observed status behavior.
- WP-01 remains IN PROGRESS: route/method matrix, authorization/CSRF/body/idempotency contracts, negative tests, and direct-vs-proxy boundary tests remain open.
- Exact previous-head CI observation: Validate Control Plane completed SUCCESS (validate and Windows dynamic-port launcher integration PASS; optional self-hosted Windows runner acceptance SKIPPED); Windows Local Auth Proxy + Gateway E2E PASS; Ubuntu Recovery Acceptance PASS. Windows Recovery Acceptance and Linux Minimal Emulator were still running at observation time.
- The documentation update changes the PR head; all CI evidence must be re-polled for the new exact head before any acceptance decision. No merge, deploy, or runtime activation authorized.


## 2026-11-23 — WP-01B Gateway/Proxy route-surface crosswalk

- Added `docs/DCP-WP01B-GATEWAY-PROXY-ROUTE-CROSSWALK.md` in commit `4848ff640df29b55577a1b8c3659911fe8913b1b`.
- Crosswalk records Gateway GET/POST/DELETE dispatch families and Local Auth Proxy GET/POST/DELETE/OPTIONS families against source blobs `9a55bccf216cff1b934bebd643e68364305449aa` and `2d8708216f85c28e70f358c0672152353c6b59bc` from main baseline `eaa9ceb91088c39b90d9b11b3817dc793e40005a`.
- Explicitly distinguishes the narrower Proxy allowlist from Gateway route families; route differences must be classified as intentionally not proxied or required/missing, not blindly widened.
- Added ten prioritized positive/negative test groups covering unsupported verbs, OPTIONS/CORS, Origin/CSRF, allowlists, direct Gateway access, Runner identity, idempotency, parser bounds and response contracts.
- This is static source analysis only. WP-01 remains IN_PROGRESS; no runtime source/tests changed and no acceptance, merge, deployment, Terminal activation or cloud provisioning is claimed.
- Re-poll all CI against the resulting exact branch head before making any status claim.
