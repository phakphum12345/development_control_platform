# Azure Linux and Windows ephemeral VM provisioner

This adapter can create an ephemeral Linux or Windows VM and a private NIC in an already-provisioned resource group. It requires a pre-existing subnet and Network Security Group (NSG), attaches the NSG to the NIC, assigns no public IP, does **not** attach a VM Managed Identity, uses Trusted Launch, and requests a Local ephemeral OS disk. The Gateway's own Managed Identity must remain on the Gateway host only.

## Mandatory deployment inputs
- Subscription and resource group.
- Pre-created subnet and NSG resource IDs in the same subscription.
- Reviewed VM sizes and exact Marketplace image references for both OS profiles.
- A protected bootstrap factory that obtains ephemeral runner registration material server-side and supplies it only through VM extension protectedSettings.
- A GitHub runner-online checker. VM power state alone never proves runner registration.

Marketplace image versions must be explicitly pinned; the adapter rejects latest. Discover available publisher/offer/SKU/version values in the intended subscription and region before configuration. Canonical's Ubuntu 24.04 documentation lists the AMD64 Gen2 image family as Canonical:ubuntu-24_04-lts:server:latest; use a specific version returned by the subscription image listing rather than latest. Windows Server 2025 publisher/offer/SKU availability must likewise be confirmed for the target region and subscription.

## Guest login profile

The production bootstrap factory must use `AzureGuestProfileFactory` from
`tools/cloud_gateway/azure_guest_profile.py` (or an independently reviewed
equivalent) rather than inventing credentials inside a request handler.

- Linux requires `DCP_AZURE_GUEST_ADMIN_USERNAME` and a single-line
  `DCP_AZURE_LINUX_SSH_PUBLIC_KEY` containing an OpenSSH Ed25519 public key.
  Password authentication is disabled. Keep the matching private key outside
  the VM and never put it in the repository or bootstrap payload.
- Windows receives a fresh high-entropy local administrator password in the
  one-time ARM create request. The factory does not return or persist it.
  The runner service must remain a non-administrator service identity.
- Neither guest profile attaches a VM Managed Identity. The Gateway's own
  Managed Identity and Key Vault permissions must remain on the Gateway host.
- These profiles are configuration building blocks, not proof of secure
  network egress or a live deployment. Provider readiness must remain false
  until the network-policy verifier and live acceptance checks also pass.

The read-only deployment preflight validates the guest username and public-key
shape without echoing the configured key. It does not prove that the key is
usable on the deployed VM.

## Security and lifecycle
- No public IP is created or attached.
- VM extension public settings must be empty; bootstrap secrets belong only in protectedSettings.
- Do not place runner tokens in customData, tags, VM metadata, or logs.
- Runner-online requires independent GitHub runner evidence.
- DELETE is only terminating. The NIC is removed after a later status read confirms the VM is absent.

## Prerequisites still requiring live review
The referenced subnet and NSG must be checked for deny-by-default inbound and restricted outbound rules. Region support for the selected VM sizes, image versions, Trusted Launch, and ephemeral OS disks must be confirmed. The bootstrap factory must be connected to a reviewed GitHub App token service and Key Vault. These checks have not been performed against a live subscription.

Tests use a fake ARM client only. No ARM request, VM, NIC, disk, or other billable resource was created.
