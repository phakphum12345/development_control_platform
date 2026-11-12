# Orka macOS runner adapter

The Orka adapter uses the documented Orka API Server VM endpoints and BearerTokenAuth. The VM configuration is supplied by trusted deployment configuration, not by the caller. It adds DCP ownership metadata and accepts only the approved macOS 15 ARM64 profile.

## Lifecycle evidence
- A successful VM create response means provisioning was accepted, not that the runner is online.
- An Orka VM in Running state remains provisioning until an injected GitHub runner-online checker independently confirms registration.
- A successful DELETE response means terminating, not terminated. A subsequent status lookup returning 404 confirms the VM is gone.
- VM identifiers are constrained to the DCP-generated name format before status or delete requests.

## Secret handling
The Orka bearer token is read through an injected Key Vault secret reader at request time. It is never included in VM metadata, request payloads, provider errors, or audit data. Do not put Orka credentials in GitHub Actions secrets or repository files.

## Orka 4.0 User Data bootstrap

`tools/cloud_gateway/orka_bootstrap.py` builds an idempotent macOS ARM64
bootstrap script using a pinned runner release/checksum and a short-lived,
repository-scoped GitHub registration token. `OrkaProvider` sends the
base64-encoded script in the documented lower-case `userdata` field, enforces
the 64 KiB encoded limit, and waits for `userdataPhase=success` before it can
report a runner online. A later `skipped` phase is accepted only when the
independent GitHub runner-online check proves the runner is registered and
online; otherwise the VM is terminated. Failed or timed-out User Data causes
termination. The script retries early-boot network access, never prints the
registration token, and does not put it in `customMetadata`.

Orka 4.0 requirements are strict: Apple silicon nodes, Orka 4.0 VM Tools in the
approved image, a finite `ORKA_USERDATA_TIMEOUT` baked into that image (for
example, 1800 seconds), and a pre-provisioned non-root, non-admin runner
account. The timeout must exceed the bounded download retries, checksum
verification and runner service setup. The namespace
must be dedicated to DCP and Kubernetes RBAC must prevent untrusted users and
service accounts from reading the VM's VirtualMachineInstance resource or pod
spec. Disable Orka API request-body logging and redact User Data from any
reverse-proxy, audit or application logs. The Orka documentation states that
the script is not returned in API responses, but Kubernetes-level readers can
inspect it; therefore the short-lived registration token remains visible to
anyone with that access. The runtime requires separate
`userdata_rbac_reviewed` and `userdata_exposure_reviewed` attestations plus
independent cluster, network and budget readiness checkers. Do not enable
either attestation until the namespace RBAC and request/log exposure controls
have been reviewed.

User Data runs as root in the background and may rerun after an interrupted
first boot. The factory is idempotent and suppresses bootstrap command output;
operators must still inspect the User Data phase, not infer readiness from a
Running VM. See the official [Orka 4.0 User Data documentation](https://docs.macstadium.com/orka/orka-resources/userdata).

## Not enabled by this adapter

This adapter does not create an Orka namespace, VM config, image, node, cluster,
network policy or budget. The approved VM config must already be reviewed to
map to macOS 15 ARM64. The User Data request contract and mocked lifecycle
checks are implemented, but no production Orka runtime composition or
authoritative Orka/MacStadium billing reader exists.

The Gateway selects budget guards by provider. Orka requests require a
separate guard keyed to `orka`; an Azure Consumption budget is never accepted
as evidence for Orka spend. Readiness remains false until an authoritative
Orka/MacStadium cost source, forecast semantics, currency, freshness policy,
live cluster/VM Tools check, namespace RBAC review, restricted egress policy,
and runner-online/job/teardown acceptance are supplied and tested. The
Gateway's global provisioning and owner-approval gates remain independent.
No Orka capacity was allocated by tests.
