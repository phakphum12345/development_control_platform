# DCP Terminal Studio — API Contract

## Implemented read-only catalog slice

The following authenticated endpoints are implemented:

- `GET /api/terminal/templates` — owner/operator catalog of curated built-in templates.
- `POST /api/terminal/commands/preview` — owner/operator exact argv preview for one known template ID; requires same-origin and CSRF validation.

The preview request accepts exactly one field, `template_id`. It rejects arbitrary command strings, extra fields and unknown template IDs. Responses contain executable/argv metadata and policy limits, but no host path, environment values, credentials or runtime tokens.

The initial catalog contains read-only Git status/diff/log and Python/Node version checks. Every entry is marked `PREVIEW_ONLY`, network denied and `execution_enabled=false`. These endpoints do not launch processes and are not an execution API.

## Implemented inert command-pack import

- `POST /api/terminal/templates/import` — owner-only JSON command-pack import. Requires same-origin and CSRF validation.
- Schema version 1 accepts 1–50 templates, a 32 KiB request cap, allowlisted executable identifiers (`git`, `python`, `node`), bounded argv/platform/time/output metadata, and network policy `denied`.
- Unknown fields, shell metacharacters, code-evaluation flags, unsupported executables/platforms and duplicate IDs are rejected.
- Imported templates are stored in a separate private SQLite database (default Gateway database path plus `.terminal`; override with `DCP_GATEWAY_TERMINAL_DATABASE`). Import is atomic and audited.
- Imported templates are always `enabled=false`, `execution_enabled=false`, and `approval_status=pending_review`. They can be listed and previewed, but cannot be executed or enabled by this API.
- Imported template previews are labelled `PENDING_REVIEW`; after review they are `APPROVED_NOT_EXECUTABLE` or `REJECTED`. Built-in templates remain `PREVIEW_ONLY`.
- `POST /api/terminal/templates/{custom-id}/review` — owner-only approve/reject decision, same-origin and CSRF protected. Requires exact typed confirmation and the source SHA-256 displayed for the reviewed version.
- `GET /api/terminal/templates/{custom-id}/events` — owner/operator audit history.
- Approval changes only the review status. The template remains disabled and non-executable; this API does not grant execution permission.

## App-authorized execution API (implemented, fail-closed by default)

- `POST /api/terminal/authorize` — owner-only grant issuance. Requires same-origin and CSRF validation. The Gateway resolves the registered Project Workspace and current snapshot, resolves the trusted built-in template, and issues a short-lived one-time grant bound to the authenticated subject/session, project, workspace, snapshot, template digest and normalized parameter digest.
- `POST /api/terminal/jobs` — owner-only typed Job submission. Requires same-origin, CSRF and an `Idempotency-Key`. The request contains only project/workspace identifiers, snapshot digest, trusted template ID, typed parameters and the opaque authorization ID. The Gateway reserves the grant to a deterministic Job ID before making the durable Job visible to Runner polling. Idempotency is scoped to the authenticated subject/session.
- `POST /v1/runner/{job-id}/terminal-grant` — Runner-credential-only grant verification. The Gateway verifies the active Job lease and Runner identity, binds the reserved grant to that Runner, and atomically consumes it once before the Runner resolves or executes the registered Project Workspace.
- Terminal Jobs are routed only to explicitly registered Runners advertising the `terminal` capability. The Runner independently checks the local trusted-project allowlist, workspace identity and snapshot, template digest, read-only/network-denied policy, process timeout, output ceiling, cancellation and process-tree cleanup.
- Runner capability is opt-in via `DCP_RUNNER_TERMINAL_ENABLED=1` and requires a non-empty trusted Local Project allowlist. `DCP_RUNNER_TERMINAL_TIMEOUT_SECONDS` and `DCP_RUNNER_TERMINAL_OUTPUT_BYTES` set bounded ceilings; the catalog may impose lower limits.
- Executable lookup uses a sanitized host PATH that excludes the selected Project Workspace, preventing a repository-local `git`, `python` or `node` binary from shadowing the trusted native tool. The executor uses a temporary HOME outside the Project Workspace and `shell=false`.
- The fixed-template executor uses a trusted executable registry and argv arrays with `shell=false`. Browser-supplied executable, argv, cwd, environment, shell, runner, role, approval or permission fields are rejected. Imported templates remain inert and cannot be selected for execution.
- **Current default state:** every built-in catalog entry remains `execution_enabled=false`; authorization and Job submission therefore return a fail-closed response until an explicit reviewed catalog opt-in and the corresponding acceptance gates are completed. Runner-side opt-in alone does not enable execution.

The Dashboard currently displays catalog and preview metadata and supports inert template import/review. A Dashboard Run control and end-to-end UI flow are not yet implemented; the API does not imply that the user-facing feature is complete.

## Proposed, not implemented

The following remain design targets and must not be treated as available endpoints:
- GET /api/terminal/jobs/{id} — status and bounded output metadata.
- POST /api/terminal/jobs/{id}/cancel — owner-authorized process-tree cancellation.
- GET /api/terminal/jobs/{id}/logs — paginated redacted logs.
- GET /api/terminal/history — project-scoped execution history.

Before any execution feature is enabled, enforce owner authorization, project/workspace scope, CSRF, server-side template resolution, policy approval, idempotency, request limits, bounded logs, secret redaction, audit and verified process-tree cleanup. Arbitrary browser-supplied shell commands remain prohibited.


## Dashboard integration

The Dashboard Terminal Studio view calls the implemented catalog and preview endpoints through same-origin requests with the authenticated session cookie and server-issued CSRF token. It renders returned preview metadata as text. It does not execute commands or expose a shell.


The Dashboard integration also includes an owner-session JSON import form for `POST /api/terminal/templates/import`. It sends the parsed JSON object through a same-origin request with the server-issued CSRF token, displays the returned source SHA-256, reloads the catalog and selects the first imported template. Imported templates remain pending review and cannot be executed.


The Dashboard also reads the template audit endpoint and provides Owner review actions for imported templates. Review controls are shown only while the preview is pending review. The browser sends the stored source hash and exact typed confirmation; the Gateway revalidates the Owner role and review state.
