# DCP Target Architecture

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
Runtime Manager supervises actual application processes in job workspaces. Preview Proxy maps a random, expiring session to a single job runtime and checks owner/session authorization. Playwright targets that preview URL, not DCP's prototype iframe. Screenshots, traces, console/network events and reports become job artifacts.

## Terminal Studio
Terminal UI is a client for the execution broker, not a privileged shell endpoint. Interactive PTY support, if implemented, must be local-agent mediated, owner-authorized, project-scoped, resource-limited and auditable. A constrained task-template mode is the initial release; arbitrary interactive shell is a separate high-risk capability requiring a threat-model review.

## Infrastructure boundary
Local adapters are the default. Cloud Provisioning, VM Creation and Cloud Deployment are independent server-side gates, default OFF. Provider adapters may be mocked/tested without composing an active provider. There is no implicit fallback from local failure to cloud.
