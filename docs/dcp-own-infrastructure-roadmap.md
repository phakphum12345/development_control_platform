# DCP Own Infrastructure — Execution Roadmap

The canonical architecture, API boundaries, repository trust model, provider contract, and safety rules live in [dcp-own-platform-architecture.md](dcp-own-platform-architecture.md). This document tracks delivery order and acceptance evidence so the two documents do not duplicate each other.

## Delivery order

| Phase | Work package | Exit evidence | Status |
|---|---|---|---|
| 0 | Baseline and safety | Work on feature branch; main untouched; Cloud Provisioning disabled; existing workflows and tests inventoried | In progress |
| 1 | Repository Manager hardening | Installation catalog pagination, private/public metadata, authenticated API, server-side membership revalidation, branch/tag/SHA resolution, project detection | Implemented and CI-verified on head `ab8c558`; installation catalog, branch/tag/commit APIs, bounded Flutter/macOS detection, and 273 Python tests pass |
| 2 | DCP Core and Job Control Plane | Stable Job API, durable state transitions, idempotency, cancellation, lease recovery, bounded retries, audit events and capability-aware scheduling | Core API/SQLite queue/scheduler implemented; bounded retry and concurrent-claim acceptance being added |
| 3 | DCP Runner Engine | Local runner agent, authenticated claim/heartbeat/report protocol, isolated workspace, logs, cancellation and cleanup reconciliation | Agent, registry, workspace and artifact handoff implemented in slices; crash workspace reconciliation and long-running supervisor acceptance remain |
| 4 | DCP Provisioning Engine | Provider-neutral capabilities/readiness/create/inspect/stop/delete; local no-cost simulation; host-specific adapters only after validation | Fake Provider lifecycle and independent Cloud/VM safety gates implemented; live provider remains disabled |
| 5 | DCP Artifact Center | Upload/list/download, checksum verification, job/commit association, retention and access control | Authenticated upload/download and SHA-256 checks implemented; scheduled retention and broader provenance acceptance remain |
| 6 | Flutter Dashboard | Flutter screens use stable DCP APIs; existing HTML dashboard retained until parity | Pending |
| 7 | Optional live provider acceptance | Explicit owner approval, bounded run, cost evidence, runner deregistration and VM teardown proof | Disabled; approval required |

## Current implementation slice

Branch: `feature/selectable-github-repositories`

Changes made in this slice:
- Added an authenticated GitHub App installation repository catalog API and Dashboard selector.
- Raised the GitHub App API response limit from 64 KiB to a strict 2 MiB, allowing normal installation repository pages with up to 100 repository records.
- Added authenticated branch/tag discovery using a short-lived token scoped to the selected repository with Contents: read.
- Added full commit SHA verification against the selected repository, including a second server-side check before accepting a runner request.
- Added Dashboard Branch/Tag selection, explicit verification for manually entered commit SHAs, and project/build-target detection display.
- Added read-only recursive Git tree and bounded pubspec manifest inspection at the selected immutable commit; Flutter macOS target presence is reported only when the Runner Xcode project and Info.plist are present. Truncated inventories return UNKNOWN.
- Added regression tests for large response limits, ref pagination, token scope, repository authorization, commit verification, Flutter-vs-Dart classification, and Flutter/macOS detection.
- Latest CI evidence: 273 Python tests, Local-first Minimal Emulator, Validate Control Plane, Dashboard browser smoke test, Windows local auth-proxy integration, and Windows dynamic-port launcher integration passed on head `ab8c558`.
- Added the architecture/API contract and this execution tracker.

## Verification still required

The latest tested head is **CI-passing**. Local execution on a developer workstation has not been performed from this chat. The following commands remain available for local reproduction:

```sh
python -m unittest tests.test_cloud_gateway_github_app -v
python -m unittest tests.test_cloud_runner_user_api -v
python -m unittest discover -s tests -v
```

Also verify the exact branch head in CI before opening a draft PR. Do not treat existing CI results from another commit as evidence for this branch head.

## CI findings and corrective work

The first PR validation attempt exposed three stale expectations in runtime/OpenAPI tests after moving from a static repository allowlist to the GitHub App installation catalog. Those expectations were updated to assert installation membership and the new empty legacy allowlist in App mode. The same run also exposed an incomplete OpenAPI path insertion; the repository refs and commit-verification paths were rewritten as a complete YAML block and documented with focused contract tests.

The corrected implementation passed both PR workflows on head `ab8c558ee4d82f940064fa4cc6597f9969d18740`. Earlier failed runs were superseded by this passing head. Re-run both workflows after any subsequent code change; do not merge until the exact current head is green.

## Safety and merge gates

- Keep `DCP_GATEWAY_PROVISIONING_ENABLED=false`.
- Do not create cloud, Orka, or paid GitHub-hosted runner resources during local development.
- Use mock/fake provider clients for tests.
- Do not read, print, or request secrets in chat or commit them to the repository.
- Do not merge this branch or any other open PR without explicit user approval.
- Do not claim macOS runner readiness until Apple-hosted bootstrap, runner online verification, restricted egress, and cleanup are proven end-to-end.

## Next engineering tasks

1. Run the focused GitHub App and authenticated repository API tests on this branch head.
2. Review the complete diff against the branch base and resolve any stale or duplicate repository-selection paths in the Dashboard.
3. Define and test the DCP Job API/queue contract before introducing Redis or PostgreSQL migrations.
4. Implement a local-only Runner Agent with authenticated claim, heartbeat, log, cancel, and result reporting.
5. Add isolated workspace handling and artifact handoff for local jobs.


## Phase 4 progress — independent infrastructure gates (merged on main)

- Added persistent SQLite switches for Cloud Provisioning and VM Creation, independent from each other and defaulting OFF.
- Added owner-only, same-origin, CSRF-protected gate mutation API and owner/operator read API.
- Enabling requires an exact confirmation phrase and provider capability readiness; unavailable providers fail closed.
- Cloud runner creation now requires the effective Cloud Provisioning gate in addition to existing budget, approval, repository and circuit-breaker controls.
- Non-fake Infrastructure Manager creation requires the effective VM Creation gate; the current composition remains fake-only with provisioning disabled.
- Added persistence, audit, authorization, confirmation, readiness and independent-state tests. No live cloud or VM resources are created.


## Phase 4 Dashboard progress — independent safety gates (merged on main)

- Added separate Cloud Provisioning and VM Creation status cards to Infrastructure Manager.
- Dashboard shows saved state, provider readiness and effective state independently; API failure is UNKNOWN and controls stay disabled.
- Only Owner can mutate a gate. Enabling requires typing the exact confirmation phrase; disabling is available to Owner.
- Cloud Runner creation UI now also requires the effective Cloud Provisioning gate.
- Local Auth Proxy GET/POST allowlist and CSRF forwarding cover the gate APIs.
- No provider is activated by this UI; current deployment remains fail-closed.


## Phase 2 progress — bounded job lease recovery (PR in progress)

- Added durable attempt_count/max_attempts metadata; each job is limited to three claimed attempts by server policy.
- Expired running jobs are requeued only while attempts remain; the final expired attempt fails with LEASE_EXPIRED.
- Expired cancellation requests become cancelled, not retried.
- Lease recovery preserves last_worker provenance and records worker/attempt counters in audit events.
- Added concurrent claims across independent JobStore instances to verify only one worker can lease a queued job.
- Exposed attempt counters through authenticated Dashboard job status responses.
- No repository code, VM, cloud provider or paid resource is executed/created by these tests.


## Phase 2 progress — HTTP lease recovery acceptance (PR in progress)

- Added a two-worker Gateway HTTP test covering registration, first claim, forced lease expiry, automatic recovery and second claim.
- Verified attempt_count increments, max_attempts is returned, and last_worker provenance survives requeue.
- Verified the former worker receives HTTP 409 when attempting a stale heartbeat after another worker owns the lease.
- Verified the current worker can finish and that the lease-recovery audit event records the former worker.
- Uses temporary SQLite databases and test-only worker tokens; no real Runner host or repository code is used.
