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

The Dashboard Run workflow is implemented in the merged Terminal Studio view. It supports registered Project Workspace selection, typed template parameters, exact preview, one-time app authorization, a separate confirmation before queueing, idempotent Job submission, Job status/log polling, and cancellation through the existing Job Control Plane APIs.

The workflow is deliberately not available for execution today: every built-in template remains `execution_enabled=false`, so the authorization/queue gates fail closed and no Terminal Job can be started from the current catalog. Imported templates remain inert even after Owner review. The presence of the UI and API path is not proof of an enabled execution capability or an OS sandbox.

## Shared Job lifecycle endpoints used by Terminal Studio

These are the existing generic Job Control Plane routes; Terminal Studio filters and validates the `terminal_script` target rather than introducing separate terminal-only status endpoints:

- `GET /api/jobs?limit=50` — recent Job history, filtered by the Dashboard to Terminal Jobs.
- `GET /api/jobs/{id}` — current state for the selected Job.
- `GET /api/jobs/{id}/logs?after_id={cursor}&limit={n}` — bounded incremental log retrieval.
- `POST /api/jobs/{id}/cancel` — request cancellation through the existing owner-authorized Job lifecycle.

Before enabling any built-in template, require a reviewed OS-isolation design, project/workspace scope, same-origin and CSRF enforcement, server-side template resolution, one-time grant/lease binding, idempotency, bounded output, secret redaction, audit, verified process-tree cleanup, adversarial tests and supported-host acceptance. Arbitrary browser-supplied shell commands remain prohibited.

## Dashboard integration

The Dashboard Terminal Studio view uses same-origin requests with the authenticated session cookie and server-issued CSRF token. The browser sends only project/workspace identifiers, a trusted template ID, typed parameters and the opaque one-time authorization grant; it never supplies an executable, raw argv, cwd, environment, shell text or Runner credentials. The Owner reviews the exact workspace/template/snapshot and confirms separately before the Gateway queues a durable typed Job.

The Dashboard polls the shared Job status and bounded log APIs, retries interrupted polling with bounded backoff, and requests cancellation through the shared Job lifecycle. HTTP status codes are preserved on request errors so the queue handler can distinguish rejected grants (400/403) from uncertain network/server outcomes and safely reuse the same idempotency key.


The Dashboard integration also includes an owner-session JSON import form for `POST /api/terminal/templates/import`. It sends the parsed JSON object through a same-origin request with the server-issued CSRF token, displays the returned source SHA-256, reloads the catalog and selects the first imported template. Imported templates remain pending review and cannot be executed.


The Dashboard also reads the template audit endpoint and provides Owner review actions for imported templates. Review controls are shown only while the preview is pending review. The browser sends the stored source hash and exact typed confirmation; the Gateway revalidates the Owner role and review state.
