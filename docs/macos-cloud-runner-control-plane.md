# DCP macOS Cloud Runner Control Plane

## Status

The provider-neutral backend, request contract, CLI, safety checks, tests, and manual GitHub Actions entry point are implemented. **No cloud provider is connected or provisioned yet.** A successful dispatch means only that a provider accepted a request; it is not evidence that a VM booted, a runner registered, or a macOS build passed.

## Architecture

1. A trusted operator manually starts `.github/workflows/macos-cloud-runner.yml` in this DCP repository.
2. The Ubuntu job validates the target repository against a strict allowlist and validates the full commit SHA.
3. The Python backend sends an authenticated HTTPS request to the configured provider control plane.
4. The provider must provision a macOS VM, register a just-in-time **ephemeral, one-job** GitHub Actions runner scoped only to `phakphum12345/generated-A4-pdf`, and remove the VM after the job.
5. The provider must dispatch or enable the corresponding target-repository workflow after registration. That workflow must run its real macOS build/test steps on labels matching `DCP_MACOS_RUNNER_LABELS`.
6. The target workflow result, exact SHA, runner identity, and artifact/test evidence must be collected independently before a gate can be marked PASS.

The DCP workflow itself does not run on the ephemeral runner because the runner is intentionally scoped to the target repository. This avoids granting a general-purpose runner access to every repository using the DCP control plane.

## Configuration

In **DCP repository → Settings → Secrets and variables → Actions**:

- Secret `DCP_RUNNER_PROVIDER_URL`: provider's HTTPS provisioning endpoint.
- Secret `DCP_RUNNER_PROVIDER_TOKEN`: narrowly scoped bearer credential, rotatable.

The workflow currently allowlists only `phakphum12345/generated-A4-pdf`. Do not widen this without review. Runner labels default to `["self-hosted","macOS","ARM64","dcp-ephemeral"]`.

No tokens, registration credentials, API keys, certificates, or private keys belong in source files, workflow inputs, logs, or artifacts. The provider must obtain short-lived GitHub runner registration credentials server-side (prefer a narrowly scoped GitHub App installation), never return them to DCP, and never expose secrets to untrusted pull-request code. Use a clean ephemeral VM, one job maximum, no persistent workspace/cache between jobs, and destroy the VM after completion.

## Provider HTTP contract

DCP sends a JSON POST with contract `dcp.macos-runner-provision.v1`, repository, full commit SHA, ref, workflow run identifiers, macOS/ARM64 labels, ephemeral=true, max_jobs=1, and safety requirements. Authentication is `Authorization: Bearer ...` over HTTPS.

A provider returns HTTP 2xx and JSON:

```json
{"accepted":true,"request_id":"provider-request-id","state":"provisioning"}
```

The provider must validate the repository against its own allowlist, make duplicate requests idempotent for repository + SHA + run ID + attempt, enforce one-job ephemeral registration, dispatch the target workflow, and expose auditable lifecycle status. Never return runner registration tokens.

## Provider selection / cost

The adapter is deliberately provider-neutral because no cloud vendor or billing account has been selected. Before enabling it, choose a macOS cloud provider that supports GitHub Actions ephemeral runners and ARM64 macOS, confirm region, hourly/minimum billing, concurrency, retention, and teardown behavior, then implement its adapter behind this webhook contract. The DCP repository does not silently create paid infrastructure.

## Validation

Run:

    python -m unittest tests.test_cloud_runner_backend -v

The tests cover allowlisting, SHA/run validation, HTTPS-only endpoint configuration, secret redaction, ephemeral one-job payloads, accepted/rejected provider responses, and dispatch authentication. They do not validate a real provider or macOS VM.
