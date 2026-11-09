# Orka API-first provisioning

This project can discover Orka resources and prepare VM configurations without using Orka Dashboard.

## Read-only discovery

- `GET /api/v1/namespaces/{namespace}/images` lists images.
- `GET /api/v1/namespaces/{namespace}/vmconfigs` lists VM configurations.

Use `OrkaProvider.list_images()` and `OrkaProvider.list_vm_configs()`. These calls do not allocate compute capacity.

## VM configuration creation

`OrkaProvider.create_vm_config(config, approved=True)` submits the documented VM-config JSON schema. The caller must explicitly set `approved=True`; the adapter rejects unknown fields and duplicate names. This creates a VM configuration only, not a running VM.

## VM creation status

`OrkaProvider.provision()` is a separate operation that creates a VM and may incur charges. It remains gated by Gateway readiness, runner bootstrap, independent GitHub runner-online verification, and a provider-specific authoritative budget reader. Do not enable live provisioning until those gates are implemented and validated against the target Orka cluster.

All automated tests mock the HTTP layer. No test provisions Orka resources or contacts a live cluster. Never store Orka bearer tokens or GitHub runner registration tokens in VM metadata, image contents, source control, or logs.
