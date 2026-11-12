# DCP Architecture — Current Slices and Target State

## Architectural rule
Extend the existing local Gateway, authentication, Job Control Plane, Runner Agent, workspace and artifact contracts. Avoid a second queue, command executor or project registry.

## Logical layers
1. Dashboard: Project Manager, Terminal Studio, Editor, Build/Runtime, Preview, Testing, Quality, Artifact, Infrastructure Control.
2. Authenticated API: owner/session auth, CSRF for mutations, project/job authorization, schema validation and rate limits.
3. Core services: Project Registry, Job Control Plane, Policy Engine, Audit/Event service, Artifact Manager, Configuration and Recovery.
4. Local Agent: approved folder enrollment, toolchain doctor, workspace operations and supervised process execution.
5. Adapters: GitHub App source, local-folder source, framework build adapters, runtime adapters, Playwright/browser adapters, database test adapters.
6. Local storage: SQLite metadata, job workspaces, logs and artifacts under configured local data root.

## Source intake
GitHub: use the existing GitHub App installation catalog, repository authorization, ref discovery and immutable commit SHA verification. Do not send installation credentials to the browser.
Local Folder: Local Agent must enroll explicit allowed roots. Dashboard selects an Agent-managed project ID, not an arbitrary filesystem path. Resolve symlinks and revalidate path containment on every operation. Fingerprint relevant files and record the source snapshot identity.

## Job contract
Every job has job_id, project_id, source_type, immutable source identity (commit SHA or local snapshot fingerprint), requested task, adapter/version, policy decision, approval reference, workspace_id, timestamps, status, exit code, logs, artifacts and cleanup result.
State transitions are explicit and idempotent. Cancellation must terminate the complete process tree and reconcile workspace cleanup.

## Execution model
The browser never invokes a shell directly. It submits a typed job/command request to the authenticated API. The Policy Engine validates project scope, task template, argv, working directory, environment allowlist, network policy, resource bounds and approval. Local Agent executes only an approved request and reports bounded output and evidence.
Imported shell scripts and command packs are inert until reviewed and explicitly approved. Avoid shell=True and arbitrary command strings; prefer executable + argv arrays and fixed adapters.

## Preview and test

### Implemented slices
- Runtime Manager currently supervises generated static output through a loopback-only Python static server. It does not launch arbitrary project server scripts.
- Authenticated Preview Proxy primitives retain runtime capabilities server-side and enforce owner/job/session checks for supported static preview content.
- The `test_static_web` Runner target starts RuntimeManager directly and runs DCP-owned Playwright checks against generated static output. It records viewport screenshots and a JSON report in a bounded ZIP artifact.
- A separate authenticated Preview Proxy E2E starts a completed job preview through the Local Auth Proxy and navigates a real browser to the same-origin preview URL. CI exercises Chromium with sandboxing enabled and adds Firefox/WebKit checks against a synthetic fixture. These checks verify the preview session contract, not general app compatibility.

### Target integration and explicit gaps
- The authenticated Preview Proxy path is now covered by a separate browser E2E; the static `test_static_web` build/test target still uses RuntimeManager directly.
- Browser traces, full interaction coverage, visual baselines and full accessibility audits remain future work. Firefox/WebKit fixture checks do not imply full cross-browser certification.
- Preview Proxy support is static-output focused; arbitrary server runtimes, HMR and WebSocket proxying are not implied.
- Screenshots and reports are evidence of only the implemented checks, not WCAG, security or production-readiness certification.

## Terminal Studio
Terminal UI is a client for the execution broker, not a privileged shell endpoint. Interactive PTY support, if implemented, must be local-agent mediated, owner-authorized, project-scoped, resource-limited and auditable. A constrained task-template mode is the initial release; arbitrary interactive shell is a separate high-risk capability requiring a threat-model review.

## Infrastructure boundary
Local adapters are the default. Cloud Provisioning, VM Creation and Cloud Deployment are independent server-side gates, default OFF. Provider adapters may be mocked/tested without composing an active provider. There is no implicit fallback from local failure to cloud.


## Status discipline

This document contains both implemented slices and target architecture. A target-layer
or future integration statement is not evidence that the feature is available today.
Use the dated Repository Audit and Master Feature Backlog for exact branch/commit
status, and require source plus same-commit tests before marking a capability PASS.