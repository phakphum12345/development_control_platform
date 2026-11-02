# Legacy DCP macOS Cloud Runner Design Note

**Status:** Historical design note retained for traceability. The current provider adapter contract is documented in [docs/cloud-runner-control-plane.md](cloud-runner-control-plane.md). Where this note differs from that document, the current gateway contract takes precedence.

This document records the earlier webhook-oriented proposal. It is not the active API specification and must not be used to configure a provider gateway.

## Historical proposal

The original design considered a provider endpoint returning:

```json
{"accepted":true,"request_id":"provider-request-id","state":"provisioning"}
```

The implemented adapter instead expects the normalized gateway response documented in the current specification:

```json
{"id":"provider-request-id","state":"provisioning","labels":[]}
```

The current gateway owns vendor-specific VM provisioning, GitHub App authentication, short-lived ephemeral runner registration, runner-online confirmation, and teardown. DCP never accepts runner registration tokens, SSH private keys, or cloud credentials in request payloads.

## Safety and evidence boundary

No provider is selected or activated automatically. No cloud VM, GitHub runner, or macOS build is created by this design note. Provider acceptance is not evidence that a runner is online or that a target build passed. Require exact-SHA-bound CI evidence before treating a macOS gate as passed.
