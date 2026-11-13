# Document Generator and Owner-Approved Local Write Workflow

**Status:** Dashboard-to-Gateway local document write API implemented on this feature branch; CI and deployment verification are pending. GitHub repository writes remain out of scope.

## Dashboard generator

Open `dashboard/index.html` and select **Document Generator**.

Supported outputs:
- Markdown: `.md`
- Roadmap: `-ROADMAP.md`
- Plain text: `.txt`

The generator builds a structured artifact from project, purpose, verified context, milestones, risks, dependencies, and acceptance criteria. Missing facts remain `TBD` or `UNKNOWN`. It performs basic credential-pattern screening, shows a preview, computes SHA-256, and can request a browser download.

Browser download remains an export action only. It does not prove that a file was saved or read back from disk.

## Enable the Gateway adapter

The adapter is opt-in. Configure absolute paths on the Gateway host:

- `DCP_LOCAL_PROJECT_REGISTRY`: the existing Local Project Registry JSON path.
- `DCP_DOCUMENT_WORKFLOW_DATABASE`: a persistent SQLite path outside every registered project.
- `DCP_DOCUMENT_WORKFLOW_JOURNAL`: optional separate writer-journal path, also outside every registered project. If omitted, the adapter uses the workflow database path plus `.writer`.

If the document database variable is absent, document write routes return `503` and no write capability is exposed. A Local Project must already be explicitly enrolled and registered through the existing local registry. Browser requests identify a project by its registry ID; they never submit an absolute host path.

## Owner-approved workflow

1. Sign in through the same-origin DCP authentication proxy.
2. Refresh the Local Project catalog and select a registered project.
3. Select an existing project-relative directory and explicitly grant it. The grant is stored server-side, scoped to that project, and expires after 30 days. No grant exists by default.
4. Generate the document and review the preview.
5. Select the exact relative `.md` or `.txt` target. The Gateway target preflight returns whether an active server-side grant covers it, whether it exists, and its current SHA-256.
6. Create a proposal. The server stores the exact content, content SHA-256, expected base SHA-256, project ID, relative path, grant ID, owner, expiry, and idempotency key. Proposals expire after 30 minutes.
7. Review the proposal's project, path, base SHA, and content SHA. A separate explicit approval action is required before the server writes.
8. The server rechecks the grant and target, calls the local writer, and only reports `PASS` when post-write read-back SHA-256 matches the proposed content. The result and lifecycle event are persisted.

The Dashboard uses owner-authenticated same-origin requests with a server-issued CSRF token. The Gateway independently enforces the signed proxy identity, owner role, Origin, CSRF, persisted grant, project identity, path containment, expected base SHA, exact proposal digest, and explicit confirmation.

## API contract

All routes are same-origin through the authenticated DCP proxy:

- `GET /api/document-workflow/grants?project_id={uuid}`: list grants and their ACTIVE / EXPIRED / REVOKED state.
- `POST /api/document-workflow/grants`: grant an existing project-relative directory. Required fields: `project_id`, `allowed_paths`, `confirmation="GRANT DOCUMENT WRITE SCOPE"`.
- `POST /api/document-workflow/grants/{grant_id}/revoke`: revoke with `confirmation="REVOKE DOCUMENT WRITE SCOPE"`.
- `GET /api/document-workflow/target?project_id={uuid}&path={relative-path}`: inspect the current base digest and scope state without reading file content.
- `POST /api/document-workflow/proposals`: propose exact content with `project_id`, `relative_path`, `content`, and `expected_sha256`; include a unique `Idempotency-Key` header.
- `GET /api/document-workflow/proposals/{proposal_id}`: inspect a proposal after reconnecting.
- `POST /api/document-workflow/proposals/{proposal_id}/approve`: approve only the exact `content_sha256` with `confirmation="WRITE DOCUMENT"`.

Request bodies for document content are capped at 600 KiB including JSON overhead; document UTF-8 content is capped at 512 KiB. Only `.md` and `.txt` files are supported. Hidden directories and protected areas such as `.git`, `.github`, credentials, secrets, tool configuration, dependency, and build directories are denied. Scope prefixes must be existing directories; parent directories are not created implicitly.

## Timeout, retry, and recovery

- Read-only GitHub GET calls use bounded 12-second attempts and retry transient network errors, HTTP 429, and HTTP 5xx.
- Document writes are never blindly retried by the Dashboard. The server uses a stable proposal ID and a separate writer idempotency journal.
- If an approval response is lost, the Dashboard performs a read-only GET of that proposal. If the proposal is `APPLIED` and its stored result includes `read_back_verified=true`, the UI reconciles to PASS. Otherwise the outcome remains UNKNOWN and the user must inspect the proposal before taking further action.
- The workflow database transaction holds the grant lock through the write, preventing a concurrent scope revocation from racing an approved write.
- The writer uses atomic replacement, streamed SHA-256 verification, a durable SQLite journal, and recovery when file replacement succeeded before the journal/proposal status was committed.
- Audit events record scope grant/revoke, proposal creation, and applied writes without storing document contents in the event table.

## Security and capability boundaries

- Scope grants are stored server-side; the Dashboard cannot supply effective `allowed_paths` to the writer.
- Scope defaults to empty. Owner role, same-origin, CSRF, signed proxy identity, and explicit confirmation are required.
- Project roots are refreshed through the Local Project Registry before operations; project and path checks fail closed.
- The Gateway writes only to the selected registered local project. It does not commit, push, or change GitHub files, and it does not open, close, or merge PRs.
- No shell, repository code execution, deployment, or remote write API is introduced.
- The workflow database and writer journal must be protected as local application state and backed up according to the host's data-retention policy.

## Verification boundary and remaining work

A `PASS` write result means the local target was read back and its bytes matched the approved content digest. It does not prove GitHub persistence, a Git commit, CI, PR review, merge, or deployment. The feature still requires exact-head CI, browser integration tests through the real local auth proxy, Windows/Linux filesystem validation, and deployment configuration verification before being called fully E2E complete.
