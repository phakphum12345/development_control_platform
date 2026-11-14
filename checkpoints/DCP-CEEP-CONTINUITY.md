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
