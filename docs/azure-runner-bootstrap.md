# Azure ephemeral GitHub runner bootstrap

## Contract

`AzureRunnerBootstrapFactory` creates the protected extension payload consumed
by `AzureVMProvider`'s existing `bootstrap_factory` callback. It supports only
the approved Linux x64 and Windows x64 profiles. It does not call Azure Resource
Manager or activate the Gateway provider.

Before constructing the factory, the server must:
- Load the GitHub App private key from the server-side secret store.
- Construct `GitHubAppRunnerBootstrap` with an exact repository allowlist.
- Pin an explicit Actions runner version and the official release archive's
  SHA-256 checksum separately for Linux and Windows.
- Supply an OS profile factory that provides the required guest login settings.

The factory obtains a short-lived repository registration token, validates its
expiry, and embeds it only in the Azure VM extension's `protectedSettings`.
The public `settings` object remains empty. Linux uses the Azure Linux Custom
Script extension and Windows uses the Azure Windows Custom Script Extension.
Both scripts verify the downloaded runner archive against the pinned checksum,
configure the runner with `--ephemeral`, and install/start the runner service.

## Runner VM identity boundary

Cloud Runner guest VMs must not receive a system-assigned Managed Identity.
Repository workflow code runs on the guest and must not be able to query IMDS
for the Gateway's Key Vault or Azure management identity. The Gateway's own
Managed Identity remains on the Gateway host only and is used to read server
secrets and the read-only budget data. Registration credentials are delivered
through Azure protected extension settings; the guest does not need an Azure
identity.

## Security and operating limits

- Never use a `latest` runner release or an unverified checksum.
- Never put a registration token in public extension `settings`, VM tags,
  runner metadata, logs, or the SQLite audit ledger.
- Restrict runner egress to the GitHub endpoints required for runner operation
  and approved workflow dependencies; the attached subnet/NSG must be reviewed
  independently before provider readiness can become true.
- The runner is ephemeral and single-job. The Gateway lifecycle controller
  must still enforce a hard TTL and verify provider deletion after a job,
  cancellation, or timeout.
- Azure protected settings protect the extension configuration in transit and
  at rest in the control plane; they do not make an untrusted workflow safe.
  Treat workflow code on the runner as privileged code within the guest.

## Validation status

Tests decode the protected payloads locally and verify checksum pinning,
ephemeral flags, OS-specific extension contracts, and secret placement. Tests
use a fake GitHub App and do not contact GitHub, Key Vault, Azure, or create VMs.

The Gateway startup still uses `DisabledProvider`. This factory alone does not
make any platform READY and does not enable provisioning. Live Azure acceptance
requires a separately approved deployment and budget.
