# DCP Own Infrastructure — Execution Roadmap

The canonical architecture, API boundaries, repository trust model, provider contract, and safety rules live in [dcp-own-platform-architecture.md](dcp-own-platform-architecture.md). This document tracks delivery order and acceptance evidence so the two documents do not duplicate each other.

## Delivery order

| Phase | Work package | Exit evidence | Status |
|---|---|---|---|
| 0 | Baseline and safety | Work on feature branch; main untouched; Cloud Provisioning disabled; existing workflows and tests inventoried | In progress |
| 1 | Repository Manager hardening | Installation catalog pagination, private/public metadata, authenticated API, server-side membership revalidation, branch/tag/SHA resolution, project detection | Installation catalog, branch/tag API, repository-scoped Contents-read tokens, commit verification, and bounded Flutter/macOS tree detection implemented on feature branch; latest project-detection tests pending |
| 2 | DCP Core and Job Control Plane | Stable Job API, durable state transitions, idempotency, cancellation, timeout, audit events, queue contract | Existing Gateway lifecycle is a starting point; scheduler/queue work pending |
| 3 | DCP Runner Engine | Local runner agent, authenticated claim/heartbeat/report protocol, isolated workspace, logs, cancellation and cleanup reconciliation | Pending |
| 4 | DCP Provisioning Engine | Provider-neutral capabilities/readiness/create/inspect/stop/delete; local no-cost simulation; host-specific adapters only after validation | Existing Azure/Orka routing is legacy adapter work; DCP-owned provider manager pending |
| 5 | DCP Artifact Center | Upload/list/download, checksum verification, job/commit association, retention and access control | Pending |
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
- Added read-only recursive Git tree inspection at the selected immutable commit; Flutter macOS support is reported only when the Runner Xcode project and Info.plist are present. Truncated inventories return UNKNOWN.
- Added regression tests for large response limits, ref pagination, token scope, repository authorization, commit verification, and Flutter/macOS detection.
- Added the architecture/API contract and this execution tracker.

## Verification still required

The code and test changes are committed, but this slice is **not yet marked test-passing**. Run the following from the repository root in the project environment:

```sh
python -m unittest tests.test_cloud_gateway_github_app -v
python -m unittest tests.test_cloud_runner_user_api -v
python -m unittest discover -s tests -v
```

Also verify the exact branch head in CI before opening a draft PR. Do not treat existing CI results from another commit as evidence for this branch head.

## CI findings and corrective work

The first PR validation attempt exposed three stale expectations in runtime/OpenAPI tests after moving from a static repository allowlist to the GitHub App installation catalog. Those expectations were updated to assert installation membership and the new empty legacy allowlist in App mode. The same run also exposed an incomplete OpenAPI path insertion; the repository refs and commit-verification paths were rewritten as a complete YAML block and documented with focused contract tests.

The latest corrected branch head still requires a fresh CI result. Do not treat the earlier failed runs as a pass, and do not merge until both Ubuntu-based PR workflows complete successfully on the exact latest SHA.

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
3. Complete project detection for Flutter and native macOS support, with explicit unsupported/needs-setup results.
4. Add contract tests for project detection and ensure unsupported targets fail before runner provisioning.
5. Define and test the Job API/queue contract before introducing Redis or PostgreSQL migrations.
