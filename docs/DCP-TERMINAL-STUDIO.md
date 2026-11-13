# DCP Terminal Studio

## Purpose
Provide a project-aware command workspace that makes common development tasks discoverable and repeatable without requiring users to memorize PowerShell, CMD, Git, Node, Python, Flutter or test commands.

## User experience
- Project-scoped terminal workspace and tabs.
- Shell/toolchain readiness display (PowerShell, CMD, Git Bash when installed).
- Command Library with categories, search, tags, descriptions and examples.
- Import commands from clipboard, JSON command packs and script files as inert templates.
- Export/share versioned command packs.
- Visual Command Builder for project, framework, task, environment and mode.
- Exact command preview, working directory and risk label before execution.
- Output, exit code, duration, logs, history, copy and stop controls.
- Session restore metadata without silently restarting processes.

## Initial command categories
Git: status, diff, branch list, log.
Node/web: detect version, install (approval), dev, build, test.
Python: version, venv creation, dependency install (approval), test.
Flutter: doctor, pub get (approval), test/build through existing fixed-target adapter.
DCP: local doctor, health check, start/stop guidance and bounded log inspection.
Browser tests: Playwright test and report tasks after preview readiness.

Templates must declare platform, prerequisites, task ID, executable, argv schema, working-directory policy, environment allowlist, network requirement, mutation class, timeout, output cap and expected evidence. Templates do not embed credentials.

## Execution contract
The browser sends a typed task request to the authenticated DCP API. The server authorizes project/job scope, resolves the approved template and applies policy. Local Agent executes approved executable/argv in the assigned workspace and reports bounded logs and outcome. No direct browser-to-shell execution.

## Import rules
Imported scripts and command packs never run on import. Validate schema, file size, encoding, paths, provenance and unsupported fields. Show a human-readable preview and require explicit approval before registering a runnable template. Execution approval is separate from import approval.

## Release boundary
MVP begins with read-only diagnostics and curated task templates. Arbitrary interactive shell/PTY is not part of the initial release; it requires a separate threat model, platform-specific isolation and explicit owner policy.


## Implementation checkpoint — read-only catalog

The first Terminal Studio API slice is implemented:
- Authenticated owner/operator catalog endpoint for curated Git and toolchain diagnostics.
- Exact argv preview endpoint with same-origin and CSRF enforcement.
- Request schema accepts only a known template ID; arbitrary executable/command fields are rejected.
- All templates are read-only, network-denied, bounded, and explicitly marked preview-only.
- No command is executed by catalog or preview requests.

Import, project binding, approved execution, cancellation, logs and history remain outstanding. Do not present this slice as an interactive shell or an execution-capable Terminal Studio.


## Dashboard integration checkpoint

The Dashboard now exposes a Terminal Studio view that loads the authenticated catalog and requests exact argv previews through the same-origin Gateway API. The view uses the existing owner session and server-issued CSRF token. It displays preview metadata as text and explicitly does not start processes. The Dashboard slice does not add command execution, project workspace selection or terminal sessions.


## Inert command-pack import checkpoint

Owner-only JSON command-pack import is now implemented. Schema v1 packs are strictly validated, bounded to 32 KiB and 1–50 templates, restricted to known executable identifiers, network denied, and stored atomically in a private SQLite database with audit events. Imported templates are always disabled and pending owner review. Previewing an imported template does not execute it. Script-file parsing, template approval/editing, workspace binding and execution remain unimplemented.


## Dashboard command-pack import

The Terminal Studio view now includes a JSON command-pack import form. It sends the pack through the authenticated same-origin API with the server-issued CSRF token, then refreshes the catalog and selects an imported template for metadata preview. The UI labels imported templates as pending Owner review. Script-file uploads and command execution remain unavailable.


## Owner review lifecycle checkpoint

Imported templates can now be explicitly approved or rejected by the Owner. Review requests bind to the immutable source SHA-256 and require an exact typed confirmation phrase. The API records the actor and decision in audit history. Approval is only a review decision: templates remain disabled and non-executable until a separate, future execution authorization system exists.


## Dashboard Owner review controls

For imported templates, Terminal Studio displays the stored source hash and review history, and exposes Approve/Reject actions while the item is pending review. The action requires an exact typed confirmation phrase. After a successful decision the catalog and preview are refreshed. Approved templates remain disabled and labelled APPROVED_NOT_EXECUTABLE.


## Visual Command Builder checkpoint — typed preview only

A bounded, schema-driven Visual Command Builder is now implemented for the curated read-only catalog:

- Git history accepts a numeric commit limit from 1 to 50 (default 5).
- Inspect Commit and Compare Working Tree to Commit require an exact 40-character hexadecimal SHA.
- The Gateway accepts only `template_id` and an optional typed `parameters` object; unknown fields, unknown parameters, wrong types, out-of-range values and malformed SHAs are rejected.
- The Dashboard renders fields from the trusted catalog schema using DOM APIs, then displays normalized parameter values and exact argv.
- Imported command packs do not accept builder parameters and remain disabled regardless of Owner review status.
- All built-in commands remain read-only, network-denied and preview-only. No shell, PTY or process execution is introduced.


## App-authorized backend execution checkpoint — 2026-11-13

The feature branch now implements the backend path for a future Dashboard Run action:

- Owner-only POST /api/terminal/authorize issues a short-lived, one-time grant bound to the authenticated subject/session, project, workspace, current snapshot, trusted template version and normalized parameter digest. Same-origin and CSRF checks are mandatory.
- Owner-only POST /api/terminal/jobs accepts only typed project/workspace identifiers, snapshot digest, trusted template ID, typed parameters and the opaque grant reference. It reserves the grant to a deterministic Job ID before the Job becomes visible to Runner polling and scopes idempotency to the authenticated session.
- The existing durable Job Store and capability-aware Runner Scheduler carry the terminal_script target. Only a registered Runner that explicitly advertises the terminal capability can claim it.
- The Runner verifies the active Job lease through its credential-authenticated Gateway endpoint. The grant is bound to that Runner and atomically consumed once.
- The Runner resolves the registered Project Workspace from its own Local Project Registry and checks the project/workspace pairing and current snapshot. It invokes only the fixed catalog template with a trusted native executable, server-derived argv and shell=false.
- Terminal output is bounded and redacted before being appended to existing durable Job logs. Timeout, cancellation polling, process-tree termination and scratch-workspace cleanup use the existing Runner/Job primitives.

### Current release gate

- Every built-in template remains execution_enabled=false. The new backend API therefore fails closed by default; Runner opt-in does not override catalog policy.
- Imported templates remain inert even after Owner review. No imported script is runnable.
- The Dashboard still has only catalog, preview, import and review controls. The Run button, Project/Workspace selector, grant confirmation view and Terminal job output panel are not implemented yet.
- The Runner appends complete redacted output lines incrementally to durable Job logs within the byte ceiling. The Dashboard does not yet display those logs live; the Run panel and live log view remain outstanding. Interactive PTY is out of scope.
- Project discovery and authorization remain Owner-only. There is no per-user Project ACL model yet.
- The Runner executes the read-only fixed templates in the actual registered project directory, but this is not an OS sandbox and does not provide kernel-enforced network isolation. Processes retain the Runner service account's OS permissions.
- The implementation and acceptance tests are on a draft PR. Do not mark the work complete until all required workflows pass for the exact latest PR head and the Dashboard Run workflow is implemented and verified.
