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
