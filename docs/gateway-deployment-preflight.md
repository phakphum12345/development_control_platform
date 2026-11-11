# DCP Gateway deployment preflight

Run a redacted, read-only configuration check before deploying the Gateway:

```powershell
python -m tools.cloud_gateway.preflight
```

The command reports configuration presence and explicit UNKNOWN/SKIPPED boundaries. It does not print configured values, read Key Vault secrets, contact GitHub/Azure/Orka, start a server, or provision resources.

A PASS from an individual check proves only that the corresponding configuration field is present and syntactically acceptable. It does not prove cloud identity, network policy, budget freshness, runner registration, VM readiness, or successful cleanup.

## Current hard gates

- Azure subnet/NSG egress must be independently inspected against the approved restricted-egress policy.
- Azure guest login and protected runner bootstrap must be verified in the target deployment.
- Orka needs an authoritative provider-specific budget source with freshness checks.
- Orka macOS User Data must install/register an ephemeral runner without persisting registration credentials.
- Each provider needs live runner-online, job execution, teardown, and post-delete verification evidence.

The preflight deliberately leaves these checks UNKNOWN or SKIPPED. Do not enable `DCP_GATEWAY_PROVISIONING_ENABLED` to bypass them. Keep provisioning disabled until a separately approved environment passes live acceptance.
