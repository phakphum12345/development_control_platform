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

## Proposed, not implemented

The following remain design targets and must not be treated as available endpoints:
- POST /api/terminal/jobs — typed job submission through an approved Local Agent adapter.
- GET /api/terminal/jobs/{id} — status and bounded output metadata.
- POST /api/terminal/jobs/{id}/cancel — owner-authorized process-tree cancellation.
- GET /api/terminal/jobs/{id}/logs — paginated redacted logs.
- GET /api/terminal/history — project-scoped execution history.

Before any execution feature is enabled, enforce owner authorization, project/workspace scope, CSRF, server-side template resolution, policy approval, idempotency, request limits, bounded logs, secret redaction, audit and verified process-tree cleanup. Arbitrary browser-supplied shell commands remain prohibited.


## Dashboard integration

The Dashboard Terminal Studio view calls the implemented catalog and preview endpoints through same-origin requests with the authenticated session cookie and server-issued CSRF token. It renders returned preview metadata as text. It does not execute commands or expose a shell.


The Dashboard integration also includes an owner-session JSON import form for `POST /api/terminal/templates/import`. It sends the parsed JSON object through a same-origin request with the server-issued CSRF token, displays the returned source SHA-256, reloads the catalog and selects the first imported template. Imported templates remain pending review and cannot be executed.
