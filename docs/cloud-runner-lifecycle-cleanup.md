# Cloud Runner lifecycle cleanup

## Terminal-state contract

A runner record is not `terminated` merely because a DELETE request was accepted.
The Gateway must confirm each resource boundary in order:

1. Request provider VM deletion.
2. Poll provider status until the VM is confirmed absent.
3. For Azure, confirm the NIC is also absent. A 202/accepted NIC delete is still
   `terminating`; the record remains retryable until a later GET returns 404.
4. Query GitHub Actions for the exact runner name in the allowlisted repository.
5. Refuse deregistration while the runner is online.
6. Remove an offline runner using a separately scoped Administration: write
   installation token.
7. Query GitHub again and confirm that the runner is absent.
8. Only then transition the durable Gateway record to `terminated`.

If any step fails, the row remains `terminating`, the error detail is not copied
to audit logs, and the next TTL/reconciliation sweep retries. A failed row with
a provider ID remains counted against concurrency until cleanup completes.

## Gateway wiring

- `GitHubRunnerCleanup` is injected into `GatewayService`; it uses the exact
  persisted repository and provider/runner name.
- Providers marked `requires_runner_cleanup` cannot provision unless the
  cleanup callback is configured.
- Providers exposing `readiness(target_os)` must return `{"ready": true}`
  before the Gateway calls `provision`. Exceptions and UNKNOWN readiness deny
  provisioning.
- The Azure provider does not report terminal until both VM and NIC are absent.
- A provider failure triggers deletion and enters `terminating`; it does not
  deregister a runner while the VM may still be alive.
- Cleanup audit events contain only enumerated outcomes such as `removed`,
  `already_absent`, or `pending`. No tokens, provider error strings, or
  untrusted response bodies are stored.

## Orka status

MacStadium announced VM User Data in Orka 4.0, allowing a script to run on first
boot. However, the current DCP Orka adapter only implements the existing
`vmConfig` / `customMetadata` request shape and has not verified the exact
Orka 4.0 User Data API field, cluster version contract, or protection of the
script from metadata/API/log exposure. A GitHub registration token must never
be placed in `customMetadata`. The Orka provider therefore reports
`ready=false` and the Gateway refuses provisioning until the 4.0 User Data
contract is implemented and tested against the target cluster's own
`/api/v1/swagger` or OpenAPI schema.

## Validation

All tests use mocked provider and GitHub responses. They verify:
- Azure VM deletion is not terminal while its NIC still exists.
- Runner deregistration is refused while GitHub reports the runner online.
- A DELETE response is not treated as proof of GitHub deregistration.
- Cleanup failures remain retryable and are audited without secret/error text.
- Providers without explicit readiness or cleanup capability cannot be
  provisioned when their adapter declares those requirements.

No live Azure, Orka, Key Vault, GitHub App, or cloud resource is contacted.
