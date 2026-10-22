# Development Control Platform

An independent, installable control plane for tracking development phases,
quality gates, commit-bound evidence, and resumable checkpoints.

## Editions

- **Personal Edition** — for individuals managing their own projects.
- **Organization Edition** — for teams that require server-side authorization,
  tenant isolation, role-based access, and auditable actions.

These are product scopes, not claims that every feature is already implemented.

## Default isolation

- The project registry starts empty.
- No external repository integration is enabled by default.
- No repository is read or modified automatically.
- External integrations are not implemented or enabled by default.
- Human approval for new write scopes is a required policy intent, not an
  implemented authorization workflow in this bootstrap scaffold.
- Policy validation checks configuration values; it does not enforce runtime
  authorization, human approval, or external permission scopes.
- This product operates independently of Research OS.

## Operating cycle

**READ → ANALYZE → WRITE/MODIFY → TEST → AUDIT**

- Preserve canonical Git history; never force-push or rewrite history.
- Bind evidence to the exact full commit SHA.
- Treat absent, stale, mismatched, or unverified results as `unknown`.
- Do not merge while any required gate is failing, pending, or unknown.
- Use project-specific gates instead of assuming all projects share one pipeline.

## Bootstrap components

- `config/projects.yml` — opt-in project registry and safety policy.
- `schemas/project-state.schema.json` — project state and gate evidence contract.
- `checkpoints/TEMPLATE.md` — resumable work checkpoint.
- `dashboard/index.html` — static bootstrap dashboard.
- `.github/workflows/validate-control-plane.yml` — structural validation and
  heuristic credential-pattern scanning.

The dashboard is static. It does not fetch GitHub data or establish live CI
status. A successful scaffold validation is not evidence that application
tests, deployments, or production readiness gates have passed.

## Registering a project

Add a project to `config/projects.yml` only after explicitly selecting it.
Use a canonical `owner/repository` name and specify its required gates.
The `status_source: github` value is registry metadata only: live GitHub status
ingestion is not implemented by this scaffold.
Do not store tokens, OAuth secrets, private keys, or credentials in the repository.

## Evidence requirements

Each project snapshot identifies its repository, branch, full 40-character
commit SHA, and observation time. Each gate result identifies the same SHA,
its status, and observation time. A passing gate must include an evidence URL.

An evidence URL alone does not prove that the evidence is trustworthy. Verify
the source, freshness, run result, and commit identity before accepting it.

## Security boundaries

Organization tenant isolation, server-side authorization, role enforcement,
and audit logging must be implemented and tested on the server; client-side
controls are not an authorization boundary.

Use least-privilege credentials and approved secret storage. Keep integrations
read-only unless a specific write operation is explicitly authorized.
