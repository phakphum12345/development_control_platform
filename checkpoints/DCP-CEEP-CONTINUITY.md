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


## 2026-11-14 — WP-18B.1-K disposable DACL defaulted-state experiment

- Protocol: DCP-CEEP v1.0; protocol file was read before implementation.
- PR #130 remains OPEN / DRAFT / NOT MERGED at head `a2e336eb034fdb2afc4340fe8228e87164afca9d`.
- Separate stacked experiment PR: #131, OPEN / DRAFT / NOT MERGED; base is PR #130 head branch `work/wp18b1j-preserve-dacl-defaulted-state`.
- Experiment branch: `work/wp18b1k-dacl-native-api-experiment-stack`; current implementation head at checkpoint creation: `638be7b55bc8d08247faca247a60b47d40045a5d`.
- Added `tools/local_runner_agent/windows_psec_dacl_experiment.py`: Windows-only ctypes harness; unique temp directory, NTFS volume check, CREATE_NEW disposable file, explicit empty DACL with caller-selected DACL_DEFAULTED TRUE/FALSE, retained-handle SetSecurityInfo, same-handle read-back, unconditional rollback attempt after write/read-back errors, and handle identity rechecks.
- Added `tests/test_windows_psec_dacl_experiment.py`: off-Windows fail-closed contract test; Windows TRUE/FALSE disposable NTFS cases; ambiguous post-write error injection that asserts rollback and cleanup.
- Updated `.github/workflows/cross-platform-recovery.yml` to invoke the test module on Ubuntu and Windows; non-Windows native cases are expected to report SKIPPED, not PASS.
- Updated `docs/DCP-WINDOWS-PSEC-DACL-DEFAULTED-NATIVE-API-EXPERIMENT.md` and `docs/INDEX.md`.
- No code was executed in this authoring environment. No native experiment result or test pass is claimed.
- Exact-head CI for PR #131: UNKNOWN at checkpoint; workflow-run query returned no runs and combined status returned no statuses for the then-current head. Recheck after branch updates.
- Potential risk to resolve during CI/review: Windows behavior for opening a newly created file with an explicit empty DACL and owner READ_CONTROL/WRITE_DAC rights; cleanup uses the exact random file path inside the harness-created temporary root after closing the retained handle.
- User-host Windows acceptance, TRUE-state round-trip semantics, Native Writer, Terminal and all seven built-in templates remain BLOCKED.
- No merge authorization exists. Next action: inspect current PR #131 exact head and CI; fix all failures, then run the same test on the designated Windows host and retain complete logs.


### WP-18B.1-K follow-up reconciliation

- Latest PR #131 head after the harness safety/error-reporting revisions: `83d8dfbd8b3517225c0b9868726a720fa2af46f5`.
- The TRUE-state setup now raises a dedicated `DaclDefaultedNotExercised`; the Windows test classifies this condition as SKIPPED / NOT EXERCISED rather than treating it as a writer pass.
- On write/read-back/rollback failure, diagnostics retain the observed post-write `DaclDefaulted`, DACL byte-equality, control flags, rollback result and error stages.
- Rollback is attempted unconditionally after a write attempt, even if the post-write read-back fails.
- The test records volume serial and 128-bit file ID from the retained handle and rechecks handle identity after write and rollback.
- Latest exact-head CI query for `83d8dfbd8b3517225c0b9868726a720fa2af46f5`: no workflow runs and no combined status entries returned. CI remains UNKNOWN; this is not a pass.
- PR #131 connector reports `mergeable=false`; investigate the GitHub mergeability state before any merge consideration. PR remains Draft / OPEN / NOT MERGED.


## 2026-11-14 — WP-18B.1-K Windows evidence and inheritance-boundary correction

- PR #131 remains OPEN / DRAFT / NOT MERGED; PR #130 remains OPEN / DRAFT / NOT MERGED. PR #131 is mergeable according to GitHub; no merge was performed.
- GitHub-hosted Windows run #43609971342 completed with all jobs green on PR head `4c11a6bdb4c91faf51cd7e17081ee9596d3e07bb` (merge checkout `36554d3f995a741ecac023b99e39da935b287d12`). This was the previous test implementation; do not use it as validation of later corrections.
- Windows host: Windows Server 2025 Datacenter build 10.0.26100; CPython 3.12.10 x64; NTFS; volume serial 9823700658284110452; probe File ID 8cb7040000006f000000000000000000.
- DACL TRUE setup was NOT EXERCISED: NTFS did not retain DaclDefaulted=TRUE at object creation.
- DACL FALSE experiment reported DaclDefaulted=false before, after write and after rollback; no API errors; cleanup verified. However, DACL bytes changed from 8-byte empty ACL `0200080000000000` to 72-byte ACL `020048000300000000101400ff011f0001010000000000051200000000101800ff011f000102000000000005200000002002000000101400ff011f00010100000000000304000000` and remained changed after rollback.
- Descriptor control flags changed from 0x9004 to 0x8404; evidence shows protected-DACL state was lost and auto-inherited state appeared. This is consistent with inherited ACEs being applied during SetSecurityInfo, but the exact mechanism remains a hypothesis until re-tested.
- Corrective change in subsequent code: set SE_DACL_PROTECTED on the creation descriptor and pass PROTECTED_DACL_SECURITY_INFORMATION with DACL_SECURITY_INFORMATION on write/rollback. This is intended to keep the test object's inheritance boundary stable.
- Closed a prior acceptance gap: TRUE and FALSE native cases now require outcome PASS; an observed FAIL can no longer leave the unittest green. Added GetProcessHandleCount before/after and require zero delta. This only verifies process handles; native heap/memory leak acceptance remains PARTIAL.
- Reader's GetSecurityInfo descriptor allocation is released with LocalFree in finally, and LocalFree failure is surfaced. Repeated-run memory stability remains unverified.
- Latest code/test head at this checkpoint before the documentation/ledger-only commits: `f3694994e844302a9ca03ef27065cccc701d378b`. GitHub checks then running: Validate Control Plane and Local-first Minimal Emulator; Windows dynamic-port launcher integration still in progress. The dedicated Cross-platform Recovery Acceptance workflow was not yet visible on this exact SHA; exact-head DACL validation remains UNKNOWN.
- GitHub-hosted Windows CI is not the designated user's Windows-host acceptance. User-host run remains PENDING; no remote execution on the user's PC was performed.
- Native Writer remains BLOCKED; Terminal remains BLOCKED; all seven built-in templates remain DISABLED. No merge or deployment authorized.


## 2026-11-14 — WP-18B.1-K corrective instrumentation checkpoint

- PR #131 only; branch `work/wp18b1k-dacl-native-api-experiment-stack`. PR #130 is unchanged. PR #131 remains OPEN / DRAFT / NOT MERGED; no merge or deployment performed.
- Fixed evidence ordering: TRUE/FALSE/ambiguous-error/write-only tests emit flushed `DACL_EXPERIMENT_EVIDENCE` immediately after harness return and before assertions.
- Split native observation from rollback: a `rollback=False` run records the immediate post-`SetSecurityInfo` state and reports `OBSERVED`; a separate default run uses a fresh disposable object and attempts rollback. The write-only test does not assert that the write preserved bytes; it records the actual result.
- Added bounded ACE-header parsing to report `INHERITED_ACE` counts after creation, after write, and after rollback where available. SID payloads are not parsed.
- Added harness-owned handle lifecycle evidence (`owned_handle_opened`, `owned_handle_closed`, `close_handle_succeeded`) and direct assertions. Process-wide handle counts are best-effort diagnostics only and are no longer acceptance gates.
- Added a distinct Windows write-only observation test. Existing FALSE round-trip and ambiguous-write-error tests remain separate disposable runs.
- Source-level review completed; Windows native execution has NOT been performed by this authoring session. No test or CI pass is claimed here.
- Next: run local syntax/portable tests and exact-head CI; inspect all workflow results against the final head SHA. Then provide the designated Windows-host PowerShell command and require the full pre-assertion evidence output. TRUE-state semantics remain UNKNOWN / NOT EXERCISED until the host actually retains TRUE at creation.
- Native Writer remains BLOCKED; Terminal remains BLOCKED; all seven built-in templates remain DISABLED. No merge authorized.


## 2026-11-14 — WP-18B.1-K evidence instrumentation revision

- Code/test/docs state reviewed on code/test head `ffaf16868bbb593dcc98dd6e89dc7b8baa4e1f2a`; the following continuity-only commit records that state.
- PR #131 remains OPEN / DRAFT / NOT MERGED; PR #130 remains unchanged. No merge, deployment, Native Writer, or Terminal enablement.
- Test evidence is now emitted with flush before assertions. TRUE setup failure carries the post-create DACL snapshot and emits it before the test is classified SKIPPED / NOT EXERCISED.
- Separate write-only observation mode (`rollback=False`) reports OBSERVED and records immediate post-write state. Round-trip mode uses a distinct fresh disposable file and unconditionally attempts rollback after write/read-back, including ambiguous error paths.
- Harness-owned handle open/close success is directly tracked and asserted. Process-wide handle counts are best-effort diagnostics only.
- Bounded ACE-header parsing records inherited ACE counts at create/write/rollback stages without parsing SID payloads.
- Current code/test suite has one portable contract test and four Windows-native tests (TRUE, FALSE write-only, FALSE round-trip, ambiguous-write rollback). Windows-native tests have not yet been executed on the user's host.
- GitHub Actions were queued on the preceding code/test head; this continuity-only commit changes the exact SHA, so all CI gates must be rechecked on the new final PR head. The self-hosted Windows runner acceptance matrix remains SKIPPED when no eligible runner is online; SKIPPED is not PASS.
- Next: wait for exact-head CI, inspect Windows recovery job logs including `DACL_EXPERIMENT_EVIDENCE`, fix any issues, then run the same command on the designated user Windows host. A TRUE-state skip is not a TRUE acceptance pass.
- Native Writer remains BLOCKED; Terminal remains BLOCKED; all seven built-in templates remain DISABLED.


## 2026-11-15 — WP-18B.1-K SetSecurityInfo flag-isolation matrix

- PR #131 only; branch `work/wp18b1k-dacl-native-api-experiment-stack`; based on PR #130. PR #130 remains unchanged.
- Latest preceding evidence from Windows Server 2025 / NTFS: FALSE write-only and round-trip preserved the 8-byte empty DACL and `DaclDefaulted=FALSE`, but descriptor control flags changed from `0x9004` to `0x9404`. The delta is `SE_DACL_AUTO_INHERITED (0x0400)`; inherited ACE count remained zero.
- Added an isolated write-only flag matrix using separate disposable files: `DACL_SECURITY_INFORMATION (0x4)` versus `DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION (0x80000004)`.
- Evidence records the exact native `SecurityInfo` mask in decimal and hex. The existing round-trip and ambiguous-write rollback cases retain the combined protected-DACL mask and their strict assertions.
- The matrix is diagnostic: neither write-only observation can pass the round-trip acceptance gate. It does not relax exact control-state comparison.
- No native execution or CI result is claimed by this checkpoint. Next: run portable tests, inspect exact-head CI logs, and then run the native matrix on Windows Server/Windows host. Keep Native Writer, Terminal, and all built-in templates BLOCKED; no merge or deployment.
