# Azure production deployment plan

**Status:** deployment preparation only. No Azure resources have been created and live provisioning remains disabled.

This document defines the approved Azure hosting direction for the Development Control Platform (DCP). It is deliberately a gated runbook: do not deploy billable resources, publish a public endpoint, or enable runner provisioning until the required subscription, domain, identity, budget, and live acceptance evidence are supplied and reviewed.

## 1. Current implementation facts

The current Gateway has:
- a Python HTTP API with `/healthz`, `/v1/runners`, and browser-facing `/api/*` routes;
- HMAC-signed reverse-proxy identity assertions, same-origin and CSRF checks;
- a SQLite lifecycle, audit, and replay-nonce store;
- optional Azure Managed Identity access to Key Vault;
- optional GitHub App private-key retrieval from Key Vault;
- Azure VM and Orka provider modules with mock-backed tests.

The default runtime remains fail-closed: the Azure adapter is composed only when
`DCP_AZURE_PROVIDER_ENABLED=true` and every Azure, GitHub App, guest-profile,
budget and network-policy input is present. The default remains disabled, and
the Orka provider remains disabled. The repository now includes a loopback
oauth2-proxy identity signer, a same-origin Nginx ingress template, an explicit
Azure provider composition path, an Azure Firewall egress verifier and
least-privilege Linux/Windows guest profiles. These are deployment building
blocks, not a configured tenant, live firewall, production ingress or proof of
a successful VM lifecycle. The first deployment must remain non-provisioning.
A green `/healthz` check is not evidence that login, runner creation, Azure VM
bootstrap, or cleanup works.

## 2. Target Azure topology

Use one Azure region selected with the owner after checking service availability, data residency, and price.

- **Azure Container Apps Environment:** isolates the DCP services and provides managed HTTPS ingress for the edge service.
- **DCP Gateway Container App:** private/internal ingress only; run one replica while SQLite is used. Do not expose the Gateway listener directly to the public internet.
- **Persistent data volume:** mount an Azure Files share for the SQLite database and backups. Keep one active Gateway replica until the store and nonce replay protection are migrated to a shared transactional database with tested concurrency semantics.
- **OIDC edge/auth service:** public same-origin Nginx entry point for the dashboard and `/api/*`, backed by a loopback-only oauth2-proxy OIDC provider and the repository's DCP identity signer. oauth2-proxy validates the OIDC session; the signer accepts only its verified subject/group response, maps immutable groups to DCP roles, issues a subject-bound edge-session cookie, and signs fresh per-request HMAC assertions. The Nginx template overwrites all six `X-DCP-*` headers and strips browser cookies/authorization before forwarding to the Gateway. The template is not deployed; the owner must register/configure the OIDC client, issuer, callback, group claims, TLS ingress and secrets.
- **Azure Key Vault:** stores the Gateway API bearer token, proxy HMAC key, GitHub App private key, and any OIDC client secret. Access only through managed identities and least-privilege RBAC.
- **Managed identities:** use separate identities for Gateway and edge where practical. Gateway receives only the required Key Vault reads, runner-resource-group permissions and narrowly scoped network read/join permissions. It must not have write access to the VNet, subnet, NSG, route table, Azure Firewall or Firewall Policy. The edge receives only the OIDC client/cookie/HMAC material it needs; never expose these values to Nginx static files or browser code.
- **Log Analytics / Azure Monitor:** central application and platform diagnostics. Configure redaction; never log bearer tokens, private keys, cookies, authorization codes, signed assertions, or raw request bodies.
- **Azure budget:** configure a real subscription budget and alerts. The application budget guard is a separate hard gate; Azure Cost Management budget alerts are not instantaneous authorization signals.

Keep the public dashboard and browser API on one HTTPS origin. Do not use GitHub Pages as the production API host.

## 3. Required owner-provided deployment inputs

Before resource deployment, collect and verify:

1. Azure subscription ID and tenant ID.
2. Target resource group (or explicit approval to create one).
3. Azure region.
4. DNS domain/subdomain controlled by the owner, plus permission to create the required DNS records.
5. OIDC identity provider tenant/issuer, client registration, exact redirect URI, and the approved owner/operator role mapping.
6. Approved monthly Azure spending ceiling and alert recipients.
7. GitHub App ID, installation ID, exact repository allowlist, and confirmation that the App has only the required runner administration permissions.
8. Approved Azure VM image/SKU/region, network egress allowlist, guest login method, and bootstrap method.
9. A decision on persistent data retention, backup, and recovery objectives.

Do not send secrets, private keys, passwords, or access tokens in chat or commit them to Git. Enter them directly into Azure Key Vault or an approved secret manager after the deployment identity is established.

## 4. Secret and configuration contract

Populate secrets in Key Vault, then grant the Gateway managed identity read access only to the named secrets:

- `DCP_GATEWAY_API_TOKEN` — private service-to-service bearer token.
- `DCP_TRUSTED_PROXY_HMAC_SECRET` — random secret of at least 32 characters, shared only with the trusted edge signer.
- GitHub App PEM private key — under the configured secret name referenced by `DCP_GITHUB_APP_PRIVATE_KEY_SECRET_NAME`.
- OIDC client secret — edge service only, if the chosen OIDC provider requires one.

Gateway configuration must be injected from the deployment secret integration, not baked into the image:

- `DCP_GATEWAY_HOST=127.0.0.1` and `DCP_GATEWAY_PORT=8789` when using the supplied same-network-namespace Nginx sidecar template. Only Nginx listens on the externally exposed container port 8080.
- `DCP_GATEWAY_API_TOKEN` from Key Vault.
- `DCP_TRUSTED_PROXY_HMAC_SECRET` from Key Vault.
- `DCP_PUBLIC_ORIGIN` set to the exact public HTTPS origin, with no path or trailing slash.
- `DCP_GATEWAY_DATABASE` set to the persistent mounted database path.
- `DCP_AZURE_KEY_VAULT_URL`, `DCP_GITHUB_APP_ID`, `DCP_GITHUB_APP_INSTALLATION_ID`, and `DCP_GITHUB_APP_PRIVATE_KEY_SECRET_NAME` after the GitHub App is configured.
- `DCP_AZURE_PROVIDER_ENABLED=false` by default; set true only after all provider inputs and live read-only checks are ready.
- `DCP_GATEWAY_PROVISIONING_ENABLED=false` for all staging and initial production deployment.
- `DCP_GATEWAY_OWNER_APPROVED=false` until explicit owner sign-off.
- Azure runner configuration: `DCP_AZURE_SUBSCRIPTION_ID`, `DCP_AZURE_RESOURCE_GROUP`, `DCP_AZURE_LOCATION`, subnet/NSG/route-table/firewall/firewall-policy IDs, Linux/Windows VM sizes and pinned image publisher/offer/SKU/version values.
- Azure guest and bootstrap configuration: `DCP_AZURE_GUEST_ADMIN_USERNAME`, `DCP_AZURE_LINUX_SSH_PUBLIC_KEY`, `DCP_RUNNER_VERSION`, and both pinned runner archive SHA-256 values.
- Azure budget configuration: `DCP_AZURE_BUDGET_NAME` and `DCP_AZURE_PROJECTED_RUN_COST_USD`.
- OIDC edge configuration: `DCP_OIDC_ISSUER`, `DCP_OIDC_AUDIENCE`, `DCP_OIDC_OWNER_GROUPS`, `DCP_OIDC_OPERATOR_GROUPS`, and the shared `DCP_TRUSTED_PROXY_HMAC_SECRET`; oauth2-proxy's OIDC client/cookie secrets must be supplied only through the secret manager.
- `DCP_GATEWAY_ALLOWED_REPOSITORIES` restricted to the reviewed exact allowlist.
- Budget, concurrency, runtime, and circuit-breaker values set to conservative reviewed limits.

Do not set provisioning to true simply because the service starts. The Azure runtime composition is opt-in and the Orka provider remains disabled. Provider readiness still depends on live ARM/Firewall verification, the current GitHub Actions FQDN catalog, live budget data, GitHub App identity and runner-online checks. No VM is created by provider composition or by the read-only preflight.

## 5. Deployment sequence and release gates

### Gate A — account and cost preflight
- Verify subscription/tenant ownership and deployment permissions.
- Check regional availability and estimate Container Apps, storage, Key Vault, monitoring, networking, DNS, and VM costs.
- Create the resource group only after owner approval of the exact subscription, region, names, and budget.
- Configure budget alerts before any runner VM is enabled.

### Gate B — private staging foundation
- Deploy Container Apps Environment, private Gateway app, persistent storage, Key Vault, managed identities, and monitoring.
- Keep public ingress disabled for the Gateway.
- Keep provisioning and owner approval false.
- Verify managed-identity access using non-secret success/failure signals.
- Verify database persistence across a controlled restart and restore from backup.

### Gate C — OIDC edge and same-origin dashboard
- Deploy the supplied Nginx + oauth2-proxy + loopback signer topology on one same-origin HTTPS endpoint.
- Configure and independently review OIDC PKCE, state, nonce, issuer, audience, signature, redirect URI, account status, immutable group claims, logout, session expiry, cookie Secure/HttpOnly/SameSite settings, CSRF, and rate limits.
- Prove the edge strips user-supplied `X-DCP-*` headers and injects valid per-request HMAC assertions.
- Verify replayed assertions are rejected and the durable nonce store is shared/atomic if more than one Gateway replica is ever used.
- Serve the dashboard and API from one HTTPS origin and verify browser flows end-to-end.

### Gate D — Azure runner adapter acceptance
- Configure `DCP_AZURE_PROVIDER_ENABLED=true` only after the complete Azure provider runtime inputs and live budget/network checks are available; keep global provisioning and owner approval false.
- Verify managed identity, separate network/runner resource groups, VM SKU/image, guest login, ephemeral disk/data handling, Azure Firewall DNS proxy and exact GitHub Actions FQDN allowlist, and deletion.
- Verify GitHub App token creation, runner registration, online confirmation, one controlled test job, runner-offline confirmation, GitHub deregistration, VM deletion, and cleanup after cancellation/timeout.
- Test failure injection at each lifecycle stage and prove that orphaned resources are reconciled.
- Verify provider-specific live budget reads and hard denial when the budget source is unavailable or stale.

### Gate E — controlled production enablement
- Review test reports, cost estimates, threat model, backup/restore evidence, and rollback plan.
- Obtain explicit owner approval for the exact repository allowlist, budget, concurrency, runtime, region, and VM SKU.
- Enable provisioning only after all prior gates pass and a separate reviewed change updates the runtime composition.
- Start with one allowlisted repository and one concurrent runner. Monitor actual costs and cleanup before increasing limits.

## 6. Acceptance checklist

- [ ] Azure subscription, tenant, region, resource group, and DNS are verified.
- [ ] Cost estimate and monthly ceiling are approved; Azure budget alerts are active.
- [ ] Gateway is private; only the edge has public HTTPS ingress.
- [ ] OIDC login, role mapping, logout, CSRF, session expiry, and replay protection pass tests.
- [ ] Dashboard and API share one HTTPS origin.
- [ ] Secrets are in Key Vault; managed identity permissions are least-privilege.
- [ ] SQLite persistence and backup/restore are proven, or the store is migrated to a shared transactional database before scaling.
- [ ] Explicit Azure provider composition is reviewed and enabled only for the configured deployment; Orka remains disabled until its own budget/bootstrap gates pass.
- [ ] Guest login, egress restrictions, runner online/job/teardown, GitHub deregistration, and orphan cleanup pass live tests.
- [ ] Live provider budget gate fails closed on missing, stale, or unavailable budget data.
- [ ] Production owner approval and rollback procedure are recorded.

## 7. Rollback

- Immediately set `DCP_GATEWAY_PROVISIONING_ENABLED=false` and `DCP_GATEWAY_OWNER_APPROVED=false`.
- Disable the edge route to mutating API endpoints while preserving the health/diagnostic path.
- Stop new runner requests; reconcile and terminate all active or expired VMs and deregister only runners confirmed offline.
- Preserve the audit database and diagnostic evidence for incident review.
- Rotate affected Key Vault secrets if exposure is suspected.
- Do not delete the persistent database, audit ledger, or Key Vault until cleanup and retention obligations are satisfied.

## 8. Current deployment boundary

This plan and the repository reference components are deployment preparation only. They do not deploy Azure resources or Azure Firewall, configure DNS/OIDC, create Key Vault secrets, enable `DCP_AZURE_PROVIDER_ENABLED`, turn on global cloud provisioning, or claim production readiness. Azure Firewall is billable; reuse an existing approved firewall or obtain explicit owner approval before creating one. Those actions require the owner inputs in section 3 and verified live acceptance evidence.
