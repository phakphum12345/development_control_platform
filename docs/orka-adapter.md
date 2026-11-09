# Orka macOS runner adapter

The Orka adapter uses the documented Orka API Server VM endpoints and BearerTokenAuth. The VM configuration is supplied by trusted deployment configuration, not by the caller. It adds DCP ownership metadata and accepts only the approved macOS 15 ARM64 profile.

## Lifecycle evidence
- A successful VM create response means provisioning was accepted, not that the runner is online.
- An Orka VM in Running state remains provisioning until an injected GitHub runner-online checker independently confirms registration.
- A successful DELETE response means terminating, not terminated. A subsequent status lookup returning 404 confirms the VM is gone.
- VM identifiers are constrained to the DCP-generated name format before status or delete requests.

## Secret handling
The Orka bearer token is read through an injected Key Vault secret reader at request time. It is never included in VM metadata, request payloads, provider errors, or audit data. Do not put Orka credentials in GitHub Actions secrets or repository files. GitHub runner registration credentials must also remain out of VM custom metadata and ordinary API settings.

## Not enabled by this adapter
This adapter does not create an Orka namespace, VM config, image, node, or cluster. The approved VM config must already exist and be reviewed to map to macOS 15 ARM64. Runner registration/bootstrap, GitHub App credentials, network egress policy, and live Orka account validation remain separate acceptance gates.

The supplied Orka API Server OpenAPI 4.x specification explicitly documents `userdata` on `OrkaVMDeployRequestModel`: a Base64-encoded shell script executed as root on first boot (Apple Silicon only), write-only and never returned by endpoints. The VM response exposes `userdataPhase` (`pending`, `success`, `failed`, `skipped`, or `timeout`). The adapter now accepts an injected, trusted `runner_userdata_factory` and sends its bounded Base64 output only in the documented `userdata` request field; it never places bootstrap material in `customMetadata`. The factory is intentionally not implemented as an automatic secret-delivery mechanism here: before enabling live provisioning, verify with MacStadium the API/audit/proxy logging and retention behavior for request bodies, the guest's handling of the script, and the exact cluster-version schema. A write-only response does not by itself prove that request bodies cannot appear in logs. macOS readiness therefore remains fail-closed pending those exposure controls and an authoritative Orka-specific cost guard. See the [Orka API Server specification](https://macstadium.github.io/orka-api-docs/).

The Gateway selects budget guards by provider. Orka requests require a separate guard keyed to `orka`; an Azure Consumption budget is never accepted as evidence for Orka spend. A generic provider-budget guard contract is available, but no Orka billing reader or provider budget source is configured or verified. Therefore Orka readiness remains false until an authoritative Orka/MacStadium cost source, forecast semantics, currency, and freshness policy are implemented and tested. No Orka capacity was allocated by tests.
