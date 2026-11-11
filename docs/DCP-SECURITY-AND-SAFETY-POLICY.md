# DCP Security and Safety Policy

## Non-negotiable defaults
- Local-first; loopback-only local services unless a separately reviewed deployment mode exists.
- Cloud Provisioning OFF; VM Creation OFF; Cloud Deployment OFF.
- No paid resource creation, automatic provider fallback or background provisioning.
- No execution on import. Source archives, command templates and scripts are data until reviewed and approved.
- Preserve local owner account, secrets, data and backups. No destructive reset or broad cleanup.
- Never merge or alter main without explicit approval.

## Trust and execution
- Treat all imported repositories, local folders, package scripts, plugins and command packs as untrusted by default.
- Workspace isolation is not an OS sandbox. Until a verified local sandbox boundary exists, execute only explicitly trusted and approved source on a controlled host.
- Use typed task identifiers and executable/argv arrays; do not accept arbitrary shell strings from browser requests.
- Enforce allowlists for executable, arguments, working directory, environment variables, network destinations, ports, runtime, output bytes and duration.
- Dependency installation and package lifecycle scripts require explicit policy and approval.
- Stop must terminate descendants, not just the parent process. Cleanup failure is a failed job state, never silently reported as success.

## Secrets and data
- Never pass Gateway credentials, GitHub App keys, installation tokens or owner passwords into project build environments.
- Use short-lived scoped credentials only where required; redact secrets from stdout/stderr, errors and artifacts.
- Separate project environments and test data. Production credentials/data are denied by default.
- Audit records store command identity/hash and policy outcome; avoid storing secret values or unnecessary sensitive payloads.

## Terminal Studio safeguards
- Imported .ps1/.bat/.cmd/.sh files are inert until user review and approval.
- Display exact executable, argv, working directory, environment profile, network policy and risk classification before execution.
- Read-only templates are default. Mutating, install, network and destructive templates require explicit confirmation; privileged/system-level operations are blocked by default.
- Enforce owner authorization, CSRF, project scoping, timeout, output cap, resource quota and process-tree cancellation.
- Detect and block dangerous patterns as defense-in-depth, but do not rely on string scanning alone; enforce a typed allowlist and OS boundary.

## Infrastructure gates
- Cloud Provisioning and VM Creation are separate controls and both default OFF.
- Backend rejects provisioning requests unless all independent gates, owner approval, budget and provider-specific safeguards pass.
- Dashboard displays backend-confirmed state only; unknown/unreachable state is UNKNOWN and fail-closed, never optimistic ON.
- Turning a gate OFF blocks new creation requests. It does not delete existing resources.
- Tests must assert provider create methods are not called while gates are OFF.

## Change governance
All source edits require a reviewable diff, tests and audit evidence. AI-assisted edits require explicit approval before apply. Backups and local user data must never be removed as part of routine development.
