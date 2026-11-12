# Local Auth Proxy Dashboard Route Contract

## Purpose

The Dashboard uses same-origin `/api` requests through the Local Auth Proxy. The proxy must expose only the exact routes required by the UI and must not become a general-purpose Gateway tunnel.

## Read routes

- Job List: `GET /api/jobs` and `GET /api/jobs?limit=N`, with a bounded limit of 1–200.
- Job detail, artifacts metadata, events and logs: canonical UUID routes under `/api/jobs/{job_id}`; log pagination accepts only `after_id` and `limit`, with limit capped at 500.
- Artifact bytes: `GET /api/artifacts/{artifact_id}/download`, handled by a dedicated binary streaming path.
- Local Runner inventory: `GET /api/runners`.
- Terminal Studio: `GET /api/terminal/templates` and canonical imported-template event routes.
- Infrastructure Manager: inventory, exact `view=catalog`, canonical resource detail/events, and `/api/infrastructure/gates`.
- Existing Local Project, GitHub App catalog/ref/commit, Cloud Runner and Preview Proxy routes retain their exact path/query restrictions.

Unknown, duplicate, malformed or out-of-range query parameters are rejected before Gateway forwarding. JSON Dashboard reads are capped at 1 MiB.

## Mutating routes

- Local Runner controls: exact `POST /api/runners/{worker_id}/drain` and `/enable`; worker IDs are validated and dot-segment identifiers are rejected.
- Terminal Studio: fixed command-preview, template-import and canonical imported-template review routes.
- Infrastructure Manager: create, start, stop, restart and delete routes for canonical resource IDs.
- Existing job creation, preview start/stop, Cloud Runner create/stop and independent infrastructure gate routes remain available through their existing guarded handlers.

Every mutation requires an authenticated local session, same-origin request and CSRF token. The Gateway repeats identity, role, CSRF, provider-readiness and policy checks. The proxy does not bypass Cloud Provisioning or VM Creation gates. Dashboard Infrastructure Manager creation currently selects the Fake provider; non-fake actions remain subject to Gateway readiness and the independent VM Creation gate. Idempotency keys are forwarded for Cloud Runner and Infrastructure Manager creation.

## Artifact download streaming

Artifact downloads do not use the JSON response buffer. The proxy requires an authenticated local Owner session, enforces a 1 GiB maximum response, validates the Gateway's `application/octet-stream` content type and quoted SHA-256 ETag, forwards only a safe attachment filename, and streams bounded chunks without exposing Gateway credentials or accepting a browser-selected upstream URL.

## Regression coverage

`tests/test_local_auth_proxy_project_routes.py` verifies allowed and denied Dashboard routes, bounded query strings, authenticated session and CSRF enforcement, Runner controls, Terminal Studio actions, Infrastructure Manager lifecycle routes, idempotency forwarding, binary artifact streaming and integrity headers.

## Implemented route inventory


The Local Auth Proxy forwards only the Dashboard read routes required by the current UI: bounded job list/detail/events/logs, job artifact metadata, authenticated artifact downloads, Runner Fleet, Terminal Template catalog/audit, and the existing Project/GitHub/Infrastructure/Preview reads. Job and artifact IDs must be canonical UUIDs; terminal audit IDs must match the imported-template ID format. Job list/log pagination accepts only the documented bounded query fields; unknown, duplicate, or out-of-range query parameters are rejected before Gateway forwarding.

Artifact downloads use a dedicated streaming path rather than the JSON response buffer. The proxy requires an authenticated local Owner session, enforces a 1 GiB maximum response, validates the Gateway's `application/octet-stream` content type and quoted SHA-256 ETag, forwards only a safe attachment filename, and streams bounded chunks without exposing Gateway credentials or accepting a browser-selected upstream URL.
Local Runner Fleet controls are forwarded only for exact `/api/runners/{worker_id}/drain` and `/enable` routes with a canonical worker ID, an authenticated local session, same-origin request, CSRF token, and an empty JSON object. Gateway independently repeats Owner/CSRF authorization before changing the Runner registry.
Infrastructure Manager reads are limited to inventory, `view=catalog`, canonical resource detail/events and the existing gate status. Create/start/stop/restart/delete operations are forwarded only through exact routes with same-origin, authenticated-session and CSRF checks; the Gateway still enforces Owner authorization, provider readiness, and the independent VM Creation gate before any non-fake provider action. The Dashboard's current create action explicitly selects the Fake provider.
Terminal Studio writes are restricted to the fixed command-preview route, template-import route and canonical imported-template review route. All require an authenticated session, same-origin request and CSRF token; template schemas, approval confirmation and execution-disabled policy remain enforced by Gateway.
