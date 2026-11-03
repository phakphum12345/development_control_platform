# Orka macOS runner adapter

The Orka adapter uses the documented Orka API Server VM endpoints and BearerTokenAuth. The VM configuration is supplied by trusted deployment configuration, not by the caller. It adds DCP ownership metadata and accepts only the approved macOS 15 ARM64 profile.

## Lifecycle evidence
- A successful VM create response means provisioning was accepted, not that the runner is online.
- An Orka VM in Running state remains provisioning until an injected GitHub runner-online checker independently confirms registration.
- A successful DELETE response means terminating, not terminated. A subsequent status lookup returning 404 confirms the VM is gone.
- VM identifiers are constrained to the DCP-generated name format before status or delete requests.

## Secret handling
The Orka bearer token is read through an injected Key Vault secret reader at request time. It is never included in VM metadata, request payloads, provider errors, or audit data. Do not put Orka credentials in GitHub Actions secrets or repository files.

## Not enabled by this adapter
This adapter does not create an Orka namespace, VM config, image, node, or cluster. The approved VM config must already exist and be reviewed to map to macOS 15 ARM64. Runner registration/bootstrap, GitHub App credentials, network egress policy, and live Orka account validation remain separate acceptance gates.\n\nThe Gateway now reports Orka readiness as false until the target cluster's Orka 4.0 User Data contract is verified and implemented. MacStadium documents first-boot User Data for Orka 4.0, but this adapter currently sends only `vmConfig` and non-secret `customMetadata`. A registration token must never be placed in `customMetadata`. Verify the exact User Data request field and how the target cluster protects the script from API, metadata, and log exposure before enabling it. The adapter also deletes failed VMs and waits for a later 404 before allowing runner deregistration. No Orka capacity was allocated by tests.
