# DCP Own Infrastructure Platform

## Status

Architecture baseline for the DCP-owned control plane. This document does not enable live provisioning, create cloud resources, or authorize a production deployment.

## Product goal

DCP owns the user experience, API, authorization, job lifecycle, runner lifecycle, provider abstraction, and artifact workflow. Infrastructure providers are replaceable adapters. Orka may remain an optional adapter, but it is not the control plane and is not required by the dashboard.

The first supported workflow is selecting any repository that the DCP GitHub App installation can access, selecting a ref, detecting the project/build target, and dispatching a controlled build job.

## Target architecture

```text
Flutter / Web Dashboard
        |
        v
DCP API + Authentication + Authorization
        |
        +---- Repository Catalog (GitHub App installation scope)
        |
        +---- Job API / Scheduler ---- Redis Queue
        |                                  |
        |                                  v
        |                            DCP Runner Agent
        |                                  |
        |                            Build / Test / Package
        |                                  |
        |                                  v
        +---- Provider Manager         Artifact Center
                  |
           Provider Adapter Interface
             /       |        \
       Local Lab   Hyper-V   Cloud / Apple-hosted
                              (opt-in only)
```

## Ownership boundaries

### DCP-owned components

- Control Plane API and identity/role enforcement.
- Repository catalog and server-side repository authorization.
- Job model, queueing, scheduling, cancellation, timeout, and audit events.
- Runner registration, health, job execution contract, and deregistration verification.
- Provider interface, provider policy, resource lifecycle, and cleanup reconciliation.
- Artifact metadata, access policy, retention, and download API.
- Dashboard and operational visibility.

### External adapters

- GitHub App API for repository discovery and short-lived runner registration credentials.
- Local virtualization or emulator backend for development.
- Optional VM/cloud providers for actual compute.
- Object-storage backend for artifact bytes.

DCP must not expose provider credentials, GitHub App private keys, installation tokens, or runner registration tokens to the browser.

## Repository access model

"All repositories" means all repositories selected for, or included in, the GitHub App installation. It does not mean every repository in a user's GitHub account automatically.

- Repository discovery must come from the DCP GitHub App installation, not public unauthenticated GitHub API results.
- The backend must refresh or revalidate installation membership before accepting a build request.
- Each runner registration token must remain scoped to the selected repository.
- The UI must display only safe metadata: full name, visibility, default branch, and relevant permission indicators.
- A repository outside the installation must be denied even if a client submits its name manually.
- Empty, stale, malformed, or unavailable repository catalogs fail closed.

## Repository catalog API contract

The first implementation exposes `GET /api/github/repositories` on the authenticated same-origin DCP API.

- Requires the existing trusted-proxy authenticated session.
- Returns only the DCP GitHub App installation catalog.
- Response shape: `{ "repositories": [{ "full_name", "private", "default_branch", "permissions" }] }`.
- The backend keeps the installation token server-side and returns only normalized metadata.
- The catalog is cached for at most 60 seconds; build/provision requests revalidate installation membership through the backend.
- Catalog failures return a generic `503` response and the UI remains disabled/UNKNOWN.
- In GitHub App mode, the installation catalog is authoritative; a legacy static allowlist must not silently hide other repositories installed for DCP.
- Without a configured GitHub App, the endpoint is unavailable and the existing static allowlist path remains a legacy compatibility mode.

## Provider contract

Every provider adapter should implement the same lifecycle contract:

- `capabilities()`: report supported operating systems and features.
- `readiness(target)`: return explicit readiness evidence without creating resources.
- `provision(request)`: create one bounded, ephemeral worker only when all policy gates pass.
- `status(provider_id)`: report observed provider state and runner identity separately.
- `terminate(provider_id)`: request shutdown/deletion and return observed state.

Provider VM state is not equivalent to GitHub runner readiness. A runner is online only after DCP independently confirms the exact runner identity and expected labels through GitHub.

## Safety defaults

- Cloud provisioning remains disabled by default.
- No provider may create a billable resource during tests or local development.
- Local/emulator mode must not silently fall back to cloud.
- Live provisioning requires explicit owner approval, an enabled feature gate, a positive budget ceiling, a provider-specific budget guard where required, concurrency limits, and a bounded runtime.
- Workers are ephemeral and use restricted egress.
- Registration credentials are short-lived, repository-scoped, provider-side only, and never logged.
- Cleanup must verify provider termination and GitHub runner deregistration before reporting completion.
- Failed cleanup remains visible and retryable; it must not be marked successful optimistically.
- Secrets are never returned by API responses or written to build logs.

## Initial build-target strategy

DCP is language-agnostic at the repository boundary. Build adapters detect project type from repository contents and report supported targets.

For Flutter:
- Detect `pubspec.yaml`.
- Detect macOS support through `macos/Runner.xcodeproj` or the corresponding Flutter macOS runner files.
- A Flutter project without macOS platform files must be reported as requiring platform setup; DCP must not claim it can build macOS yet.
- A successful Linux or Windows build does not prove macOS build capability.

## Delivery phases and exit criteria

### Phase 1 — Core contracts and repository catalog
- Document API contracts and data model.
- Implement GitHub App installation repository discovery with safe pagination and short cache.
- Add authenticated repository catalog endpoint.
- Revalidate installation membership server-side for every build/provision request.
- Preserve repository-scoped installation tokens for runner administration.
- Tests: pagination, malformed responses, inaccessible repository denial, private repository metadata, and no token leakage.

Exit: dashboard can retrieve the installation's repository catalog and the backend denies repositories outside it.

### Phase 2 — Job control plane
- Define durable job states, idempotency, cancellation, retry rules, event history, and timeout.
- Add queue abstraction with a deterministic in-process/local test adapter first.
- Add Redis adapter after contract tests pass.

Exit: a local job can be queued, claimed, reported, cancelled, and recovered without any VM/cloud provider.

### Phase 3 — Runner agent
- Define authenticated runner-to-control-plane protocol.
- Implement local runner agent and isolated workspace handling.
- Add log streaming, heartbeat, lease expiry, and cleanup.
- Keep GitHub runner registration optional for local-only tests.

Exit: local runner completes a test build and reports logs/status/artifacts to DCP.

### Phase 4 — Provider manager
- Implement provider-neutral lifecycle interface and a no-op/local emulator provider.
- Add Hyper-V/QEMU adapters only where host capabilities are available.
- Keep macOS provider readiness explicitly unsupported until the Apple-hosted environment, bootstrap, user-data exposure controls, and cleanup are verified.

Exit: provider contract tests pass; no live resources are created by default.

### Phase 5 — Artifact Center
- Store artifact metadata and checksums in DCP.
- Add local filesystem storage adapter, then optional S3-compatible storage.
- Enforce per-job access and retention policies.

Exit: build outputs can be uploaded, listed, downloaded, and verified by checksum.

### Phase 6 — Flutter dashboard
- Preserve the current dashboard until Flutter screens reach feature parity.
- Build repository picker, job monitor, runner center, provider center, and artifact browser against stable APIs.
- Do not couple Flutter UI to provider-specific APIs.

Exit: primary workflows are usable from the DCP-owned Flutter dashboard.

### Phase 7 — End-to-end acceptance
- Run local repository-selection, build, failure, cancellation, timeout, artifact, and cleanup scenarios.
- Verify logs and API payloads contain no secrets.
- Verify cloud gate remains disabled throughout local acceptance.

Exit: all local acceptance checks pass and a separate owner decision is recorded before any live provider test.

## Out of scope until separately approved

- Enabling cloud provisioning.
- Creating/deleting real cloud VMs or Orka VMs.
- Running paid macOS GitHub-hosted workflows.
- Merging pull requests.
- Changing production identity, networking, or secret-store configuration.
