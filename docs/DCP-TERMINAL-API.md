# DCP Terminal Studio — API Contract

## Implemented read-only catalog slice

The following authenticated endpoints are implemented:

- `GET /api/terminal/templates` — owner/operator catalog of curated built-in templates.
- `POST /api/terminal/commands/preview` — owner/operator exact argv preview for one known template ID; requires same-origin and CSRF validation.

The preview request accepts exactly one field, `template_id`. It rejects arbitrary command strings, extra fields and unknown template IDs. Responses contain executable/argv metadata and policy limits, but no host path, environment values, credentials or runtime tokens.

The initial catalog contains read-only Git status/diff/log and Python/Node version checks. Every entry is marked `PREVIEW_ONLY`, network denied and `execution_enabled=false`. These endpoints do not launch processes and are not an execution API.

## Proposed, not implemented

The following remain design targets and must not be treated as available endpoints:

- POST /api/terminal/templates/import — inert command-pack validation/storage.
- POST /api/terminal/jobs — typed job submission through an approved Local Agent adapter.
- GET /api/terminal/jobs/{id} — status and bounded output metadata.
- POST /api/terminal/jobs/{id}/cancel — owner-authorized process-tree cancellation.
- GET /api/terminal/jobs/{id}/logs — paginated redacted logs.
- GET /api/terminal/history — project-scoped execution history.

Before any execution feature is enabled, enforce owner authorization, project/workspace scope, CSRF, server-side template resolution, policy approval, idempotency, request limits, bounded logs, secret redaction, audit and verified process-tree cleanup. Arbitrary browser-supplied shell commands remain prohibited.
