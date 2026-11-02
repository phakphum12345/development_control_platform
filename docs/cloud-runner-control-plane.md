# DCP Cloud Runner Control Plane

**Status:** provider-neutral orchestration foundation; live cloud provisioning is not enabled until a provider gateway is deployed and configured.

## Goal

Provide one reusable control plane for projects that need macOS CI without owning a Mac. The first target is `phakphum12345/generated-A4-pdf`; other repositories must be explicitly allowlisted. DCP does not silently register repositories or change their workflow files.

## Architecture

1. A trusted workflow or operator requests an ephemeral macOS runner for an exact repository, workflow run ID, and full commit SHA.
2. DCP validates the repository allowlist, SHA, approved image, and bounded runtime.
3. The provider adapter sends a request to a separately deployed HTTPS Cloud Runner Gateway.
4. The gateway is responsible for vendor-specific cloud VM creation, GitHub App authentication, short-lived runner registration, runner online confirmation, and teardown.
5. The runner is ephemeral, restricted-egress, and labelled `dcp-cloud-macos`. The requesting workflow must use a matching label and still wait for GitHub to confirm the runner is online.

DCP intentionally does not accept GitHub registration tokens, SSH private keys, or cloud credentials in request payloads. The gateway must hold these as server-side secrets and must never return or log them.

## Gateway API contract

Base URL must be HTTPS and is supplied through `DCP_RUNNER_PROVIDER_URL`. Authentication uses `DCP_RUNNER_PROVIDER_TOKEN` in the Authorization header; never commit it.

- `POST /v1/runners` — accepts `repository`, `workflow_run_id`, `commit_sha`, `image`, `labels`, `ephemeral`, `max_runtime_minutes`, `network_policy`, and `registration_token_handling`.
- `GET /v1/runners/{id}` — returns current lifecycle state.
- `DELETE /v1/runners/{id}` — requests teardown.

The adapter accepts JSON objects with non-empty string fields `id` and `state`; optional `runner_name` and `detail` must be strings, and `labels` must be a list of strings. Responses are capped at 65,536 bytes. Provider IDs are URL-escaped when used in status and teardown paths. The configured URL must be an HTTPS origin only (no path, query, fragment, or embedded credentials). Transport errors are reported by exception type only so response text and credentials are not copied into error messages. The gateway must enforce authenticated caller identity, repository allowlisting, rate limits, idempotency, audit logging, VM TTL, cleanup on workflow completion/cancellation, and protection against arbitrary command execution. The gateway implementation is not included in this repository yet; no vendor-specific API is assumed.

## Configuration

- `DCP_RUNNER_PROVIDER_URL`: HTTPS gateway origin.
- `DCP_RUNNER_PROVIDER_TOKEN`: gateway bearer token, stored in deployment secret storage.
- `DCP_RUNNER_ALLOWED_REPOSITORIES`: comma-separated exact owner/repository allowlist.

The first intended allowlist entry is `phakphum12345/generated-A4-pdf`. Configure it only in the backend deployment environment after review.

## Cost and safety

The approved request image is currently `macos-15-arm64`, with a 5–180 minute runtime bound and a default of 60 minutes. These are request policy defaults, not a promise that a provider offers that image or price. A provider must publish pricing, region, machine class, startup latency, retention, and cancellation behavior before production use. Provisioning must be denied when provider health, billing guardrails, or repository authorization are unknown.

## Integration status and truthful CI evidence

This commit adds only the DCP policy/orchestration layer and a provider API contract. It does not create a cloud VM, register a GitHub runner, execute a macOS build, or prove macOS CI. Until a real gateway is deployed and end-to-end tested, keep the existing GitHub-hosted macOS job as the authoritative check and report its queued/cancelled state as pending/unknown—not passed.

## Tests

Run:

```sh
python -m unittest tests.test_cloud_runner_backend -v
python -m unittest discover -s tests -v
```

Tests cover both the policy manager (with a fake provider) and the HTTPS adapter (with mocked HTTP responses). They validate request authentication/serialization, URL validation, response shape and size limits, URL-escaped IDs, and error redaction. The HTTP tests do not contact a real gateway and do not make paid cloud calls.
