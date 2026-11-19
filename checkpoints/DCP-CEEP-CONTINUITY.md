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


---

## 2026-11-20 — WP-06 trusted repository bootstrap implementation checkpoint

- Main baseline: `985a78d5fba459c8a0cbcf47e5d00a858c6e6228`.
- Root cause: `Setup-DCP-Local-Runner.ps1` on main lacks `-TrustedRepository`; `tests/test_local_runner_bootstrap.ps1:28` invokes it. Both `Start-DCP-Gateway-Runner.ps1` and legacy `Start-DCP-Local-Runner.ps1` require the persisted Gateway allowlist before execution.
- Cross-checked consumers: `tools/local_auth_proxy.py::load_gateway_local_settings` validates `allowed_repositories` and `gateway_child_environment` exports `DCP_GATEWAY_ALLOWED_REPOSITORIES`; Gateway `GatewaySettings.from_env` consumes that variable.
- Created independent main-based branch `work/wp06-trusted-repository-bootstrap`; PR #152 is Draft.
- Modified `Setup-DCP-Local-Runner.ps1` to persist and protect bounded allowlist settings; expanded `tests/test_local_runner_bootstrap.ps1` for traversal rejection, duplicate case variants, 20-repository cap, 16-worker cap and no-mutation behavior; updated `docs/local-job-control-plane.md` setup sequence.
- The implementation was written as a scoped WP-06 change; no PSEC launcher/runtime files were copied or changed.
- PR #152 head at checkpoint: `c19d65f48f62fc1fb354bde9c5b9947f814bd7fc` (before this ledger commit). Exact-head CI is not yet complete; Windows runner acceptance is optional/skipped on hosted CI and is not PSEC acceptance.
- No main modification, merge, force-push, branch deletion, cloud provisioning or VM creation.
- Next: run exact-head CI; inspect PowerShell failure logs; repair only verified defects; audit full diff; update PR evidence. Keep PR #140/#149 open and Draft pending WP-06 sequencing.


---

## 2026-11-20 — WP-06 first Windows CI failure and regression-test correction

- Exact head `f4a597fd2e7f911c1cb5a5598636815b834e0c76` ran the native Windows bootstrap test and successfully completed the first setup, idempotent setup, second-worker setup, allowlist persistence and initial ACL setup.
- The job then failed in the existing acceptance test at `tests/test_local_runner_bootstrap.ps1:67`, before the new negative cases: PowerShell's regex engine rejected the pre-existing single-backslash pattern `BUILTIN\Users` as an invalid escape sequence (`\U`).
- This is a latent test assertion defect that was previously masked by the earlier missing-parameter failure. The implementation's ACL writes had completed; the test stopped while parsing the ACL regex.
- Corrected the assertion to use a regex-escaped literal backslash (`BUILTIN\\Users`), consistent with the following credential ACL assertion.
- New exact head after correction: `e16127fd9769ec8cb80ad8077fd9b7bd8d60c622`. All required CI must rerun on this exact head; no PASS is claimed until then.


---

## 2026-11-20 — WP-06 bootstrap hardening exact-head acceptance

- PR #140 merged by Owner into main at `eaa9ceb91088c39b90d9b11b3817dc793e40005a`; its original `-TrustedRepository` bootstrap contract is now mainline.
- PR #152 is a follow-up hardening branch based on that new mainline. It rejects reparse-point/non-regular paths, bounds file sizes and counts, validates allowlist/token schemas, writes protected JSON via exclusive temp files and tests failure-without-mutation.
- On exact head `4270c1379fd67649ecf17448cc0f334586d75724`: Validate PASS; Windows dynamic-port integration PASS; Linux Minimal Emulator PASS; Windows Auth Proxy + Gateway E2E PASS; Ubuntu and Windows Recovery PASS.
- Native Windows bootstrap acceptance output includes `Local Runner credential bootstrap tests passed.`; the symlink test did not emit its capability-based SKIPPED warning.
- Optional Windows runner acceptance is SKIPPED; this does not certify PSEC/AppContainer/LPAC.
- PR #152 remains Draft and unmerged. No cloud resource provisioning or VM creation occurred.
