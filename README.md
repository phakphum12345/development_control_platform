# Development Control Platform

An independent control plane for development phases, quality gates, commit-bound evidence, and resumable checkpoints.

## Interactive dashboard toolkit

Open dashboard/index.html in a modern browser. Current tools:

- **Repository Explorer** — inspect public repository metadata, up to 100 branches and the first 20 open pull requests.
- **Research OS API** — staged, read-only connector using Research OS Google sign-in and a one-time OAuth handoff. **Sync Google OAuth** restarts the existing `/v1/auth/google/start` flow and updates the in-tab connection status after `/v1/auth/google/handoff`; it accepts only HTTPS API origins and HTTPS authorization URLs on `accounts.google.com`. The session token remains in tab memory only; no GitHub token is sent to the browser. This reconnect/status action does not sync Google Drive files.
- **Pull Request Review** — inspect public PR metadata, up to 100 changed files and reviews, and check runs for the exact PR head SHA.
- **User Explorer** — inspect public GitHub profile information. Public profile data is not proof of organization membership or permissions.
- **SHA & Evidence Validator** — validate evidence record structure, full SHA format, timestamp and HTTPS URL.
- **Quality Gate Planner** — evaluate selected required gates with fail-closed local checklist rules.
- **Checkpoint Builder** — create a Markdown handoff note and copy or download it.
- **Audit & Safety Checklist** — export a local safety checklist as JSON.
- **Shared Route Color Manager** — one centralized palette for READ, ANALYZE, WRITE/MODIFY, TEST, AUDIT, BLOCKED and UNKNOWN plus PASS/FAIL/PENDING/UNKNOWN status colors. Customize, preview, save in the current browser, reset, or export JSON; colors are presentation only and never prove gate status.
- **UI Route Manager** — discovers actual Dashboard view IDs dynamically, with add/edit/delete controls, a drag-and-drop visual connection builder, and JSON export. Automatic validation detects duplicate IDs/connections, missing targets/parents, parent cycles, self-connections, and connections to disabled routes (warnings). Registry and visual connections use the same browser-local data model; access labels remain metadata only.
- **Code Navigator** — route-aware, three-panel mapping from the current Dashboard view to DOM elements, declared handlers, API/service boundaries, browser state, tests, and evidence limits. Colored route bars reuse the existing route-color CSS palette; Trace UI, Trace Calls, Show UI, Compare, DOM-only Run Checks, and Checkpoint actions are wired. Unknown call edges and live CI/deployment evidence remain explicitly UNKNOWN; the navigator does not execute inspected code.
- **UI Simulator** — a split code-editor/live-preview page for HTML/CSS/JavaScript prototypes, plus a registry-route preview that simulates navigation over the same registered connections. Both previews run in a sandboxed iframe and can be downloaded as an HTML file; neither modifies production routing or deploys the preview.

The dashboard calls the unauthenticated public GitHub REST API directly from the browser. Network errors, inaccessible resources, and rate limits are shown as errors. This is not private-repository integration and uses no credentials.

## Security limitations

The static public-GitHub tools do not provide private-repository access or authenticated GitHub permissions. The Research OS API connector is staged and is **not production-ready** until the matching backend changes are deployed to the canonical Render source repository and end-to-end tests prove session validation, owner authorization, repository allowlisting, CORS, and OAuth handoff. Until then, do not treat the connector as an available production capability. The dashboard does not implement organization tenant isolation, durable audit logs, evidence freshness enforcement, production route integration, or Git write actions. UI Route Manager access labels are planning metadata only; browser-local registry edits do not alter the actual router. The UI Simulator runs user-authored preview code inside a sandboxed iframe and is not a production deployment tool. It cannot create branches or PRs, approve reviews, merge, push, or deploy. Browser controls are not an authorization boundary.

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

Run the static dashboard contract tests using Python 3.12 or newer:

    python -m unittest discover -s tests -v

Run the real-browser smoke tests with Node.js and Playwright Chromium:

    npm install --no-save --no-package-lock playwright
    npx playwright install --with-deps chromium
    node tests/browser_smoke.mjs

The CI workflow runs both static contract tests and browser smoke tests. Browser coverage exercises route-color persistence, route registry add/edit/delete, connection editing, the sandboxed simulator, and registry-route preview. These checks do not replace authenticated integration tests or a production security review.

## Run the dashboard locally

On Windows, open the repository folder and run `Open-DCP-Dashboard.cmd`. It starts the static dashboard on `127.0.0.1`, chooses an available port automatically, and opens the browser. It does not kill an unrelated process if a port is occupied. You can also start it from PowerShell:

    .\\Start-DCP-Dashboard.ps1 -OpenBrowser

The dashboard UI and the Research OS API are separate processes. By default, the Research OS API field still points to the configured HTTPS Render backend. To use a locally running API, start that backend separately and enter its loopback URL (for example, `http://127.0.0.1:8788`) while the dashboard itself is served from `localhost` or `127.0.0.1`. The backend must implement the same API contract and explicitly allow the local dashboard origin through CORS; this repository does not contain or start that API server. HTTP API URLs on non-loopback hosts remain blocked, OAuth authorization must remain HTTPS on Google's authorization host, and a session is kept in tab memory only. Local UI availability is not evidence that API authentication succeeded.

## Local emulators and VS Code

Open this repository root in VS Code. Recommended extensions and workspace tasks are declared in `.vscode/extensions.json`, `.vscode/tasks.json`, and `.vscode/launch.json`.

- Run **DCP: Check local development environment** to inspect available Python, Node/npm, VS Code CLI, Flutter, Android SDK tools, and macOS simulator tooling.
- Run **DCP: List connected devices** to query Flutter and Android Debug Bridge when installed.
- Run **DCP: List Android AVDs** to discover existing Android Virtual Devices.
- Run **DCP: Launch Android AVD** only with an exact name returned by the AVD list.
- Run **DCP: Python contract tests** and **DCP: Dashboard browser smoke tests** for local validation.

The helper is read-only except for the explicit `launch-avd` command. It does not install SDKs, change environment variables, create AVDs, read credentials, or install an application. Missing tools return UNKNOWN; starting an emulator does not prove that an app booted or passed tests. iOS Simulator discovery is reported only on macOS, and this repository does not itself contain a native Flutter application to install on an emulator.

## Mobile app and authentication boundary

- **PWA shell** — installable dashboard manifest, app icon, mobile-friendly navigation, and a service worker that caches only the static shell. Authentication/API requests are network-only.
- **Password Login** — frontend integration contract only. GitHub Pages is static hosting; the server-side authentication API is not present in this repository. The login stays disabled until `/api/auth/session` confirms a backend is available. Do not treat this UI as working authentication until the API is deployed and security tests pass. See `docs/authentication-deployment.md`.

## Repository components

- config/projects.yml — opt-in project registry and safety policy.
- schemas/project-state.schema.json — project state and gate evidence contract.
- checkpoints/TEMPLATE.md — resumable checkpoint template.
- dashboard/index.html — interactive read-only toolkit.
- tests/test_dashboard_contract.py — static dashboard contract tests.
- tests/browser_smoke.mjs — Playwright browser smoke tests.
- .github/workflows/validate-control-plane.yml — JavaScript syntax, static and browser tests, registry/schema checks, credential-pattern scanning, and optional self-hosted Windows smoke tests.
