# DCP Own Infrastructure Platform

## Purpose

Build a provider-independent infrastructure and build platform owned by DCP. Orka may remain an optional provider adapter, but it must not be the control plane or a required dashboard. The first delivery is local-first and must not create billable cloud resources.

## Product boundary

DCP owns:
- Dashboard and authenticated control API.
- Repository catalog and authorization policy.
- Build job model, queueing, scheduling, and lifecycle.
- Runner identity, registration, health, and cleanup.
- Provider abstraction and VM lifecycle orchestration.
- Build logs, artifacts, retention, and audit evidence.
- Cost, concurrency, runtime, and network safety gates.

External providers supply compute only. GitHub supplies source control and Actions integration; GitHub App credentials remain server-side.

## Target architecture

```text
Flutter / Web Dashboard
        |
        v
DCP API + Authentication + RBAC
        |
        +---- Repository Manager ---- GitHub App installation catalog
        |
        +---- Job Scheduler --------- PostgreSQL (durable state)
        |              |
        |              +------------ Redis (queue / short-lived coordination)
        |
        +---- Provisioning Controller
        |              |
        |              +------------ Provider Adapter Interface
        |                             +-- Local / Emulator (no VM or cost)
        |                             +-- QEMU/KVM (eligible Linux hosts)
        |                             +-- Hyper-V (eligible Windows hosts)
        |                             +-- Apple virtualization provider (eligible Apple hardware)
        |                             +-- Optional Orka / Cloud adapters
        |
        +---- Runner Manager -------- DCP Runner Agent
        |
        +---- Artifact Service ------ S3-compatible object storage (MinIO local first)
        |
        +---- Audit / Cost / Policy
```

The existing Python gateway and same-origin API are the initial control-plane implementation. Flutter is a dashboard migration target, not a reason to discard the working API. PostgreSQL and Redis are planned components; do not claim they are deployed until implementation and tests prove it.

## Core contracts

### Repository

- A repository is selectable only when it is present in the DCP GitHub App installation catalog.
- Public visibility does not imply DCP installation membership or write permission.
- The backend revalidates installation membership when a job is submitted.
- Installation tokens used for runner administration are scoped to the selected repository.
- Never return App private keys, installation tokens, or runner registration tokens to the browser.
- Repository catalog responses expose only safe metadata needed by the selector.

### Job

A job records repository, ref kind/value, resolved commit SHA, target platform, build profile, requested resources, requester, timestamps, state, logs, and artifact references. The resolved SHA is immutable for the execution.

Required states: queued, validating, preparing, running, uploading, succeeded, failed, cancelled, timed_out, cleanup_pending, and cleanup_failed. Terminal success is not reported until artifact handling and required runner cleanup checks are complete.

### Runner and VM lifecycle

- Runner registration is repository-scoped and short-lived.
- Runners are ephemeral by default.
- VM running is not proof that a runner is online.
- Cleanup must verify GitHub runner deregistration; an unconfirmed cleanup remains visible as pending/failed.
- Enforce a configurable maximum runtime (initial target: 30 minutes for the first acceptance profile), concurrency cap, restricted egress, and idempotent create/cancel requests.
- Never place secrets in logs, VM metadata, artifacts, or browser responses.

### Provider interface

Provider adapters implement capability discovery, readiness, create, inspect, stop, delete, and cleanup verification. The control plane must not contain provider-specific VM logic. An unavailable or unverified provider reports NOT_READY and fails closed.

macOS builds require eligible Apple hardware and a compliant virtualization environment. Flutter emulators do not replace native macOS compilation or macOS signing.

## Delivery phases and exit criteria

### Phase 0 — Baseline and safety
- Inventory existing gateway, dashboard, store, provider router, workflows, tests, and deployment boundaries.
- Preserve main and work only on a feature branch.
- Keep cloud provisioning disabled; do not trigger paid runners or create cloud resources.
- Record known gaps and exact test commands.

Exit: baseline and safety constraints documented; no production or cloud side effects.

### Phase 1 — DCP Core contracts
- Stabilize API schemas for repositories, jobs, runners, providers, and artifacts.
- Define persistence interfaces and migrations before introducing PostgreSQL.
- Define audit events, RBAC, idempotency, timeout, and error contracts.
- Keep current working store behind an interface until migration tests pass.

Exit: contract tests cover valid, invalid, unauthorized, duplicate, and unavailable cases.

### Phase 2 — Repository Manager
- List all repositories available to the DCP GitHub App installation, including private repositories when installed.
- Support repository search and safe metadata.
- Add branch/tag/commit selection and resolve the selected ref to a full commit SHA.
- Detect project type and required build targets, including Flutter and native macOS project support.

Exit: selectable installed repositories work end-to-end; repositories outside the installation are rejected server-side.

### Phase 3 — Job and Runner Engine
- Implement durable job scheduling and queue coordination.
- Implement runner agent protocol, heartbeat, logs, cancellation, timeout, and cleanup reconciliation.
- Keep tokens provider-side and repository-scoped.

Exit: local mock runner completes a build/test job and proves lifecycle transitions and cleanup behavior.

### Phase 4 — Local Provisioning
- Implement provider capability interface and a no-cost local/emulator provider first.
- Add eligible-host adapters only after security and capability tests.
- Enforce resource, runtime, concurrency, and network policies.

Exit: create/inspect/stop/delete lifecycle passes locally without external billing.

### Phase 5 — Artifact Center
- Store artifacts with immutable job and commit associations.
- Add authenticated download, retention policy, checksum verification, and quota controls.

Exit: artifact upload/download/checksum/authorization tests pass.

### Phase 6 — Flutter Dashboard
- Build Flutter screens against the stable DCP API: Overview, Repositories, Build Center, Jobs, Runners, Providers, Artifacts, Settings.
- Retain the current web dashboard until feature parity and accessibility checks pass.

Exit: Flutter UI can select a repository, submit a local job, monitor it, and retrieve its artifact.

### Phase 7 — Optional live provider acceptance
- Evaluate each provider independently.
- Require explicit owner approval for any billable resource, paid Actions run, or live provisioning.
- Start with a bounded single-run acceptance and verify teardown before expanding.

Exit: provider-specific evidence, cost evidence, security review, and cleanup proof are recorded. No provider is called production-ready without these.

## Immediate implementation slice

1. Increase the GitHub App response bound so legitimate installation catalog pages are not rejected at 64 KiB, while retaining a strict 2 MiB cap.
2. Add regression tests for responses above 64 KiB and above the hard cap.
3. Verify catalog pagination, cache behavior, server endpoint, and backend reauthorization.
4. Run the complete relevant unit and API test suites in CI or a local test environment.
5. Review the branch diff and open a draft PR only after checks pass. Do not merge without explicit approval.

## Non-goals for the first release

- No cloud VM creation or paid provider activation.
- No automatic enabling of Cloud Provisioning.
- No claim that macOS runner bootstrap is production-ready.
- No forced migration of the existing dashboard before the API contracts are stable.
- No assumption that every repository in a user's GitHub account is installed for the DCP GitHub App.
