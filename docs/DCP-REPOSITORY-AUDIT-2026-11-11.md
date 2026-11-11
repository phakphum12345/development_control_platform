# DCP Repository Audit — 2026-11-11

## Scope and evidence

Repository: `phakphum12345/development_control_platform`  
Working branch: `feature/dcp-master-platform-plan`  
Review baseline: current branch contents, README, implementation roadmap, Gateway, job queue, local runner, workspace, auth proxy, CI workflow and focused tests.

This is a source-level audit. It does not claim that the user's Windows machine, running processes, credentials, local data, external GitHub App installation, or any deployed service have been inspected.

## Executive result

DCP already has substantial local-first foundations. The immediate engineering gap is not a missing generic control plane: it is the absence of a unified, policy-enforced project import/build/runtime/preview/test pipeline for general application types.

Existing components should be extended rather than replaced:
- SQLite Job Control Plane, lifecycle events/logs, leases and cancellation.
- Runner registry/scheduler and authenticated Runner Agent protocol.
- Per-job workspace allocation and cleanup.
- Immutable GitHub commit checkout and source SHA verification.
- Flutter-only fixed-command build executor with execution disabled by default.
- Artifact storage/package handling.
- Loopback Local Auth Proxy and signed Gateway identity boundary.
- Disabled cloud provider composition and mock-only provider contract tests.
- Dashboard static contract tests and Playwright browser smoke tests.

## Capability classification

| Capability | Status | Source evidence / limitation |
|---|---|---|
| Local-first Gateway | EXISTING | `tools/cloud_gateway/server.py`; local Gateway and loopback stack are documented. |
| Local owner password authentication | EXISTING | `tools/local_auth_proxy.py`; local auth tests cover login/session/CSRF/proxy boundary. Machine runtime state remains unverified. |
| Durable Job Control Plane | EXISTING | `tools/cloud_gateway/job_control.py`; SQLite jobs, events, logs, leases and lifecycle transitions. |
| Runner registry and scheduling | EXISTING | Gateway imports `RunnerRegistry` and `RunnerScheduler`; verify complete policy coverage in focused tests before extending. |
| Per-job workspace allocation | EXISTING | `tools/local_runner_agent/workspace.py`; bounded active count/size, private root and ownership marker. This is directory isolation, NOT an OS sandbox. |
| GitHub immutable commit checkout | EXISTING | `tools/local_runner_agent/checkout.py` and checkout tests; verify private GitHub App path separately from public/static Dashboard API. |
| Flutter build execution | EXISTING | `tools/local_runner_agent/execution.py`; fixed Flutter target allowlist, timeout/output bounds, opt-in execution. |
| Generic HTML/JS, React/Vite, Vue build adapters | MISSING | Existing executor is Flutter-specific; no verified generic web build adapter found in inspected source. |
| Runtime supervision and preview proxy | MISSING | No verified generic application runtime/session/preview proxy found in inspected source. |
| Playwright against imported application preview | MISSING | `tests/browser_smoke.mjs` exercises DCP Dashboard, not an imported application preview. |
| Dashboard static/browser tests | EXISTING | `tests/test_dashboard_contract.py`, `tests/browser_smoke.mjs`, CI workflow. |
| Artifact storage and Flutter packaging | EXISTING | Gateway imports `ArtifactStore`; runner has Flutter artifact packager. Generic web artifact provenance/UI remains PARTIAL. |
| GitHub App runtime | PARTIAL | `build_github_app_runtime` exists and is mock-tested; deployment/live private-repository authorization is not proven by source tests. |
| Local Folder import/enrollment | MISSING | No verified approved-root Local Agent enrollment/import flow found in the inspected source/search. |
| Framework/toolchain detection | PARTIAL | Existing repository inspection has Flutter/macOS manifest detection; broad framework/build/test detection remains missing. |
| Terminal Studio | MISSING | Existing local runner executes fixed Flutter targets; no safe general-purpose Terminal Studio UI/API or command library verified. |
| Cloud provisioning fail-closed boundary | EXISTING | `DisabledProvider` in `tools/cloud_gateway/server.py`; runtime tests assert lifecycle operations reject. |
| Independent Cloud Provisioning and VM Creation UI/backend controls | PARTIAL | Existing provisioning policy and Infrastructure Manager/Fake Provider are separate concepts, but independent owner-controlled persistent OFF switches are not yet proven. |
| Database/API/Debug/Workflow/AI/Release studios | MISSING or PARTIAL | Dashboard contains read-only planning/inspection prototypes; no complete integrated production workflows verified. |

## Important security findings

1. The production Gateway source composes a `DisabledProvider`; do not replace it with Azure/Orka providers during this program.
2. Infrastructure Manager uses a fake provider for simulation; its UI is not evidence of real VM creation capability.
3. Workspace directory isolation does not provide OS-level process or network sandboxing.
4. Flutter executor is an explicit opt-in execution boundary. Do not generalize it into arbitrary shell execution.
5. The Local Auth Proxy is the browser-facing authentication boundary; do not expose Gateway bearer credentials to Dashboard JavaScript.
6. Public GitHub repository browsing in the static Dashboard is not private-repository authorization.
7. Existing Dashboard UI Simulator is a sandboxed prototype editor, not a real imported application runtime preview.
8. CI's Playwright smoke test validates Dashboard behavior only. It does not validate application import/build/runtime/E2E.
9. Do not claim live machine or cloud state from repository source. Runtime and deployment facts remain UNKNOWN until independently checked.

## CI and test commands verified from repository configuration

Python contract and backend suite:
```powershell
python -m unittest discover -s tests -v
```

Dashboard browser smoke test (requires Node.js, Playwright and Chromium):
```powershell
npm install --no-save --no-package-lock playwright
npx playwright install chromium
node tests/browser_smoke.mjs
```

The repository workflow `.github/workflows/validate-control-plane.yml` additionally validates embedded Dashboard JavaScript, registry YAML/JSON Schema and runs the same Python/browser tests. These are source-configured commands, not results executed during this audit.

## Dependency map for implementation

1. **Project identity and source import** must precede analysis, workspace creation and build jobs.
2. **Framework detection and adapter contracts** must precede selecting a build command.
3. **Approved execution policy and isolated job workspace** must precede dependency installation or source execution.
4. **Generic build adapter** must produce a bounded, provenance-linked artifact before runtime launch.
5. **Runtime supervisor and preview proxy** must issue an authenticated, expiring preview session before Playwright can test the application.
6. **Test runner and artifact store** must bind screenshots, reports and logs to the exact project, source commit and job.
7. **Quality gates** must consume verified test/security evidence; missing evidence remains UNKNOWN.
8. **Terminal Studio** must use typed tasks and the same Local Agent policy broker; it must not become a general arbitrary-shell API.
9. **Infrastructure controls** remain independent, persistent, backend-enforced OFF gates and must not be prerequisites for local builds.

## Recommended implementation order

### Workstream A — Import and project identity
- Define a unified project/source snapshot model.
- Harden/verify GitHub App repository authorization and immutable SHA selection.
- Add Local Agent enrollment with explicit approved roots, symlink/path traversal protections and folder fingerprinting.
- Add tests for private/public authorization and Local Folder boundary behavior.

### Workstream B — Framework detection and safe adapter contract
- Add deterministic, read-only detection for static HTML/JS, React/Vite and Vue/Vite.
- Detect package manager, scripts and toolchain requirements without executing imported scripts.
- Use adapter IDs and typed arguments, not user-provided shell strings.
- Unknown frameworks remain UNKNOWN.

### Workstream C — Generic build MVP
- Add bounded static/Node web build adapters behind explicit trusted-project approval.
- Enforce time/output/resource limits and process-tree cancellation.
- Keep Flutter adapter behavior intact.
- Store build logs and artifacts with source SHA and provenance.

### Workstream D — Runtime and preview
- Add supervised runtime lifecycle, port allocation, health checks, expiring preview sessions and authenticated proxy.
- Ensure stop/cancel cleans up only processes owned by the job.
- Do not treat the existing UI Simulator as application preview.

### Workstream E — Real application testing and evidence
- Run Playwright only against the actual preview URL.
- Capture screenshots, traces, console/network errors and reports.
- Bind all evidence to immutable source SHA and job ID.
- Add quality gate rules with PASS/FAIL/UNKNOWN semantics.

### Workstream F — Terminal Studio and remaining workspaces
- Add typed command catalog, inert import, exact argv preview, approval and audit.
- Extend API/DB/debug/workflow/release/AI features only after their authorization, data contracts and evidence model are defined.

## Phase acceptance rules

- Every workstream gets a focused Draft PR and tests.
- No direct changes to `main`.
- No destructive Git operations or broad cleanup.
- Preserve existing local owner account, credentials, data and backups.
- No automatic source execution on import.
- No arbitrary browser-to-shell endpoint.
- Cloud Provisioning, VM Creation and Cloud Deployment remain OFF.
- Do not enable or compose Azure/Orka live providers.
- Never report PASS without a reproducible test result and exact commit reference.
