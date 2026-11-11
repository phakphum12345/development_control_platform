# DCP Terminal Studio — API Contract (Proposed)

This is a proposed contract; do not treat endpoints as implemented until source and tests confirm them.

- GET /api/terminal/templates — list templates allowed for the current owner/project.
- POST /api/terminal/templates/import — validate and store an inert command pack; never execute.
- POST /api/terminal/commands/preview — resolve template and arguments; return exact executable, argv, cwd policy, environment names, risk, network policy and approval requirement.
- POST /api/terminal/jobs — create an approved typed job; require idempotency key and CSRF/session checks.
- GET /api/terminal/jobs/{id} — status and bounded output metadata.
- POST /api/terminal/jobs/{id}/cancel — owner-authorized process-tree cancellation.
- GET /api/terminal/jobs/{id}/logs — paginated redacted logs.
- GET /api/terminal/history — project-scoped execution history.

Every mutation must enforce owner authorization, project scope, CSRF, policy decision, request limits and audit. Do not expose arbitrary command execution endpoints or secrets in responses.
