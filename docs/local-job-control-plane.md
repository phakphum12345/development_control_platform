# Local Job Control Plane — milestones 1–2

The local-first job API adds a durable SQLite queue and authenticated HTTP lifecycle endpoints. It does not execute repository code, launch a runner process, create VMs, or enable cloud provisioning.

## Dashboard API

Dashboard routes use the existing trusted-proxy HMAC session. Reads require an owner/operator session. Mutations require same-origin plus CSRF validation. Job cancellation is owner-only.

- `POST /api/jobs` — create with `Idempotency-Key`; payload allows only `repository`, immutable lowercase `commit_sha`, and `target` in `test|build|package`.
- `GET /api/jobs?limit=50` — list recent jobs.
- `GET /api/jobs/{id}` — inspect a job.
- `GET /api/jobs/{id}/events` — lifecycle events.
- `GET /api/jobs/{id}/logs?after_id=0&limit=500` — paginated logs.
- `POST /api/jobs/{id}/cancel` — owner-only cancellation.

## Runner API

Runner routes use credentials separate from the gateway's internal API token and browser session. Configure `DCP_RUNNER_TOKENS` as a JSON object mapping worker IDs to unique tokens of at least 32 characters. Do not commit tokens or put them in dashboard configuration.

- `POST /v1/runner/claim` — optional `lease_seconds` (5–300); worker identity comes from its credential, never the request body.
- `POST /v1/runner/{id}/heartbeat` — renew the authenticated worker's active lease.
- `POST /v1/runner/{id}/logs` — append a bounded stdout/stderr/system log message.
- `POST /v1/runner/{id}/finish` — report `succeeded|failed|cancelled`; only the current lease owner can finish.

The jobs database defaults to `DCP_GATEWAY_DATABASE + ".jobs"`; override with `DCP_GATEWAY_JOBS_DATABASE`.

## Safety boundary

Expired leases are recovered before a claim. Old workers are fenced by the lease checks in the store. The API accepts no shell command, arbitrary environment, filesystem path, or provider selection. The local agent, workspace isolation, command policy, process-tree termination, resource limits, build execution, artifacts, VM creation, and Cloud Provisioning are not enabled in this milestone.
