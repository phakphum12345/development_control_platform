# Development Control Platform

An independent control plane for development phases, quality gates, commit-bound evidence, and resumable checkpoints.

## Interactive dashboard toolkit

Open dashboard/index.html in a modern browser. Current tools:

- **Repository Explorer** — inspect public repository metadata, up to 100 branches and the first 20 open pull requests.
- **Pull Request Review** — inspect public PR metadata, up to 100 changed files and reviews, and check runs for the exact PR head SHA.
- **User Explorer** — inspect public GitHub profile information. Public profile data is not proof of organization membership or permissions.
- **SHA & Evidence Validator** — validate evidence record structure, full SHA format, timestamp and HTTPS URL.
- **Quality Gate Planner** — evaluate selected required gates with fail-closed local checklist rules.
- **Checkpoint Builder** — create a Markdown handoff note and copy or download it.
- **Audit & Safety Checklist** — export a local safety checklist as JSON.
- **Shared Route Color Manager** — one centralized palette for READ, ANALYZE, WRITE/MODIFY, TEST, AUDIT, BLOCKED and UNKNOWN plus PASS/FAIL/PENDING/UNKNOWN status colors. Customize, preview, save in the current browser, reset, or export JSON; colors are presentation only and never prove gate status.
- **UI Route Manager** — discovers actual Dashboard view IDs dynamically, with add/edit/delete controls, a drag-and-drop visual connection builder, and JSON export. Automatic validation detects duplicate IDs/connections, missing targets/parents, parent cycles, self-connections, and connections to disabled routes (warnings). Registry and visual connections use the same browser-local data model; access labels remain metadata only.
- **UI Simulator** — a split code-editor/live-preview page for HTML/CSS/JavaScript prototypes, plus a registry-route preview that simulates navigation over the same registered connections. Both previews run in a sandboxed iframe and can be downloaded as an HTML file; neither modifies production routing or deploys the preview.

The dashboard calls the unauthenticated public GitHub REST API directly from the browser. Network errors, inaccessible resources, and rate limits are shown as errors. This is not private-repository integration and uses no credentials.

## Security limitations

This static dashboard does **not** implement server-side authentication, GitHub App/OAuth installation, private repository access, organization tenant isolation, role-based authorization, durable audit logs, evidence freshness enforcement, production route integration, or Git write actions. UI Route Manager access labels are planning metadata only; browser-local registry edits do not alter the actual router. The UI Simulator runs user-authored preview code inside a sandboxed iframe and is not a production deployment tool. It cannot create branches or PRs, approve reviews, merge, push, or deploy. Browser controls are not an authorization boundary.

The evidence validator checks structure only. A structurally valid record is not proof that a gate actually passed. Independently verify the source, freshness, run result, and exact full commit SHA. Missing, stale, mismatched, or unverifiable evidence is unknown. Do not merge while a required gate is failing, pending, or unknown.

## Editions and safe defaults

- **Personal Edition** — individual project tracking.
- **Organization Edition** — future server-side roles, tenant isolation, membership controls, and audit retention.
- The project registry starts empty; no repository is registered automatically.
- Integrations are opt-in. Never commit tokens, OAuth secrets, private keys, or credentials.
- Read-only is the default. Force-push and history rewrite are prohibited by policy.
- New write scopes require explicit approval and server-side enforcement before implementation.

## Operating cycle

**READ → ANALYZE → WRITE/MODIFY → TEST → AUDIT**

## Validation

Run the dashboard contract tests using Python 3.12 or newer:

    python -m unittest discover -s tests -v

These static contract tests do not replace browser automation, authenticated integration tests, or a production security review.

## Repository components

- config/projects.yml — opt-in project registry and safety policy.
- schemas/project-state.schema.json — project state and gate evidence contract.
- checkpoints/TEMPLATE.md — resumable checkpoint template.
- dashboard/index.html — interactive read-only toolkit.
- tests/test_dashboard_contract.py — static dashboard contract tests.
- .github/workflows/validate-control-plane.yml — registry/schema checks, dashboard contract tests, credential-pattern scanning, and optional self-hosted Windows smoke tests.
