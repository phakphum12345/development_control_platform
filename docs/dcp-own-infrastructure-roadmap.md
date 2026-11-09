# DCP Own Infrastructure — Execution Roadmap

The canonical architecture, API boundaries, repository trust model, provider contract, and safety rules live in [dcp-own-platform-architecture.md](dcp-own-platform-architecture.md). This document tracks delivery order and acceptance evidence so the two documents do not duplicate each other.

## Delivery order

| Phase | Work package | Exit evidence | Status |
|---|---|---|---|
| 0 | Baseline and safety | Work on feature branch; main untouched; Cloud Provisioning disabled; existing workflows and tests inventoried | In progress |
| 1 | Repository Manager hardening | Installation catalog pagination, private/public metadata, authenticated API, server-side membership revalidation, branch/tag/SHA resolution, project detection | Existing catalog/API implemented; scale regression fix added; full verification pending |
| 2 | DCP Core and Job Control Plane | Stable Job API, durable state transitions, idempotency, cancellation, timeout, audit events, queue contract | Existing Gateway lifecycle is a starting point; scheduler/queue work pending |
| 3 | DCP Runner Engine | Local runner agent, authenticated claim/heartbeat/report protocol, isolated workspace, logs, cancellation and cleanup reconciliation | Pending |
| 4 | DCP Provisioning Engine | Provider-neutral capabilities/readiness/create/inspect/stop/delete; local no-cost simulation; host-specific adapters only after validation | Existing Azure/Orka routing is legacy adapter work; DCP-owned provider manager pending |
| 5 | DCP Artifact Center | Upload/list/download, checksum verification, job/commit association, retention and access control | Pending |
| 6 | Flutter Dashboard | Flutter screens use stable DCP APIs; existing HTML dashboard retained until parity | Pending |
| 7 | Optional live provider acceptance | Explicit owner approval, bounded run, cost evidence, runner deregistration and VM teardown proof | Disabled; approval required |

## Current implementation slice

Branch: `feature/selectable-github-repositories`

Changes made in this slice:
- Added an authenticated GitHub App repository catalog API contract to the Dashboard documentation.
- Raised the GitHub App API response limit from 64 KiB to a strict 2 MiB, allowing normal installation repository pages with up to 100 repository records.
- Added regression tests for a valid response larger than 64 KiB and rejection above the 2 MiB cap.
- Added this execution tracker.

## Verification still required

The code and test changes are committed, but this slice is **not yet marked test-passing**. Run the following from the repository root in the project environment:

```sh
python -m unittest tests.test_cloud_gateway_github_app -v
python -m unittest tests.test_cloud_runner_user_api -v
python -m unittest discover -s tests -v
```

Also verify the exact branch head in CI before opening a draft PR. Do not treat existing CI results from another commit as evidence for this branch head.

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
3. Add authenticated branch/tag/ref discovery with the minimum GitHub App permissions needed; if the App installation lacks those permissions, report NOT_READY rather than falling back to unauthenticated public metadata.
4. Add repository project detection for Flutter and native macOS support.
5. Define and test the Job API/queue contract before introducing Redis or PostgreSQL migrations.
