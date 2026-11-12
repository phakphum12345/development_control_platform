# Azure Linux and Windows ephemeral VM provisioner

This adapter can create an ephemeral Linux or Windows VM and a private NIC in an already-provisioned resource group. It requires a pre-existing subnet and Network Security Group (NSG), attaches the NSG to the NIC, assigns no public IP, does **not** attach a VM Managed Identity, uses Trusted Launch, and requests a Local ephemeral OS disk. The Gateway's own Managed Identity must remain on the Gateway host only.

## Mandatory deployment inputs
- Subscription and resource group.
- Pre-created subnet, NSG, route table, Azure Firewall and Firewall Policy resource IDs in the same subscription.
- A dedicated network resource group separate from the ephemeral runner resource group.
- Reviewed VM sizes and exact Marketplace image references for both OS profiles.
- A protected bootstrap factory that obtains ephemeral runner registration material server-side and supplies it only through VM extension protectedSettings.
- A GitHub runner-online checker. VM power state alone never proves runner registration.

Marketplace image versions must be explicitly pinned; the adapter rejects latest. Discover available publisher/offer/SKU/version values in the intended subscription and region before configuration. Canonical's Ubuntu 24.04 documentation lists the AMD64 Gen2 image family as Canonical:ubuntu-24_04-lts:server:latest; use a specific version returned by the subscription image listing rather than latest. Windows Server 2025 publisher/offer/SKU availability must likewise be confirmed for the target region and subscription.

## Runtime composition and activation

`tools/cloud_gateway/azure_provider_runtime.py` composes the real Azure
adapter only when `DCP_AZURE_PROVIDER_ENABLED=true`. The default is false.
The composition requires all of the following to be present:

- Azure subscription, runner resource group, location, subnet, NSG, route
  table, firewall and firewall policy resource IDs.
- Linux and Windows VM sizes and four pinned Marketplace image fields per OS:
  `DCP_AZURE_LINUX_IMAGE_PUBLISHER/OFFER/SKU/VERSION` and
  `DCP_AZURE_WINDOWS_IMAGE_PUBLISHER/OFFER/SKU/VERSION`.
- `DCP_RUNNER_VERSION` and both runner archive SHA-256 values.
- Guest administrator username and Linux Ed25519 public key.
- GitHub App + Key Vault configuration, a runner-online checker and the live
  Azure budget guard.

The provider uses the Gateway Managed Identity for ARM and Key Vault access.
The runtime does not turn on `DCP_GATEWAY_PROVISIONING_ENABLED` or
`DCP_GATEWAY_OWNER_APPROVED`. Both global gates remain independently
enforced. Keep them disabled until the deployed OIDC ingress, network policy,
budget, permissions and live acceptance tests have been verified. The adapter
rechecks provider readiness immediately before its first ARM write.

The read-only preflight validates the opt-in flag and required configuration
shape, but it does not authenticate to Azure or prove resource permissions.
No provider is composed when the explicit opt-in is false. Enabling the
provider is not permission to create a VM; the Gateway's global policy and
budget checks still apply.

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

## Restricted outbound network policy

The runner subnet must use a dedicated, pre-existing Azure Firewall and Firewall
Policy. The verifier in `tools/cloud_gateway/azure_egress.py` is read-only; it
does not create a firewall, route table, NSG, subnet, or policy.

Required topology and policy:

- The runner subnet is associated with the configured NSG and route table.
- The route table has exactly one `0.0.0.0/0` route with
  `nextHopType=VirtualAppliance` and the Azure Firewall private IP.
  `disableBgpRoutePropagation` must be true, and no Internet or other bypass
  next hop is accepted.
- The Azure Firewall is attached to the configured Firewall Policy and has one
  verified private IP.
- Firewall Policy DNS proxy is enabled, and the runner VNet DNS server list
  contains only that firewall private IP.
- Inherited Firewall Policies are rejected. The verifier accepts only explicit
  HTTPS/443 Application Rules scoped exactly to the runner subnet prefixes.
- The allowlist must exactly match the current GitHub Actions FQDN catalog from
  `https://api.github.com/meta` (`domains.actions`) plus any explicit
  `DCP_AZURE_EGRESS_EXTRA_FQDNS` values. Broad wildcard rules, web categories,
  FQDN tags, NAT collections and network allow rules are rejected.
- The NSG must not contain custom inbound allow rules. The VM adapter creates
  no public IP.

Configure these additional resource references:
- `DCP_AZURE_ROUTE_TABLE_ID`
- `DCP_AZURE_FIREWALL_ID`
- `DCP_AZURE_FIREWALL_POLICY_ID`
- Optional `DCP_AZURE_EGRESS_EXTRA_FQDNS`: comma-separated exact FQDNs or
  explicit subdomain wildcards needed by approved workflows.

Keep the network resources in a separate resource group from the ephemeral
runner resource group. The Gateway managed identity must not have write access
to the VNet, subnet, NSG, route table, firewall or Firewall Policy. Grant only
the narrowly required read/join permissions for attaching a runner NIC to the
pre-existing network. A broad subscription- or network-resource-group
Contributor role defeats this isolation and is not acceptable.

Azure Firewall is a billable service. Reuse an already-approved firewall or
obtain explicit owner approval for its deployment and ongoing cost; this
repository does not create one. The read-only preflight checks resource-ID
syntax only. The verifier performs live ARM and GitHub catalog reads at
readiness time and fails closed if any source is missing, stale, inherited or
inconsistent.

## Security and lifecycle
- No public IP is created or attached.
- VM extension public settings must be empty; bootstrap secrets belong only in protectedSettings.
- Do not place runner tokens in customData, tags, VM metadata, or logs.
- Runner-online requires independent GitHub runner evidence.
- DELETE is only terminating. The NIC is removed after a later status read confirms the VM is absent.

## Prerequisites still requiring live review
The referenced subnet, NSG, route table and Azure Firewall Policy must pass the restricted-egress verifier. Region support for the selected VM sizes, image versions, Trusted Launch, and ephemeral OS disks must be confirmed. The bootstrap factory must be connected to a reviewed GitHub App token service and Key Vault. These checks have not been performed against a live subscription.

Tests use a fake ARM client only. No ARM request, VM, NIC, disk, or other billable resource was created.
