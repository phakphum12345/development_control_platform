# Cloud Runner completion audit — 2026-11-12

**Repository:** `phakphum12345/development_control_platform`  
**Audited revision:** `43cfdcc78a5f6994684685017c52aae606f1eecb` (`main`)  
**Status:** NOT COMPLETE — production runner provisioning remains fail-closed.  
**Scope:** Azure Linux/Windows and Orka macOS Cloud Runner, including dashboard, Gateway, identity, provider adapters, budgets, lifecycle and live acceptance.

## Executive finding

The repository contains a substantial Cloud Runner control-plane foundation, but it cannot create a real runner in its current production composition. The production Gateway constructs `ProviderRouter(DisabledProvider(), DisabledProvider())`. The dashboard and authenticated browser API are present, but provider readiness remains false and server-side create requests are denied.

Do not replace the disabled providers with live adapters as a blanket change. The adapters have explicit deployment-time dependencies and acceptance gates that are not satisfied by mock tests.

## What is already implemented

| Area | Evidence on audited main | Actual boundary |
|---|---|---|
| Dashboard controls | Cloud Runner Control UI and same-origin API contract | UI does not provision by itself |
| Gateway identity | HMAC-signed trusted-proxy assertions, durable nonce replay protection, role, Origin and CSRF checks | No production OIDC callback/session service or trusted edge deployment is supplied |
| Lifecycle API | Create/list/status/terminate, idempotency, TTL and reconciliation | Production provider is disabled |
| Independent safety gates | Persistent Cloud Provisioning and VM Creation switches | Both remain OFF; provider readiness is separately required |
| GitHub App | Key Vault-backed App runtime, installation repository access, registration-token and runner-online adapters | Requires real App installation, permissions, Key Vault and managed identity |
| Azure VM adapter | Linux/Windows VM and NIC create/status/delete, pinned images, ephemeral OS disk, private NIC, protected extension settings | Needs verified network policy, guest profile, real subscription and runtime composition |
| Azure budget | Read-only Azure Consumption budget reader and guard | Needs real budget, forecast, projected run cost and live identity access |
| Azure bootstrap | Ephemeral Linux/Windows runner scripts with pinned release/checksum and protected registration token | Guest login profile and production runner-online/cleanup acceptance remain unverified |
| Orka adapter | macOS VM create/status/delete API client | Readiness is deliberately always false pending protected User Data bootstrap and Orka-specific budget |
| Test coverage | Unit, contract and mock-backed E2E tests | No test currently proves live Azure/Orka VM creation, runner-online job execution or paid-resource cleanup |

## Blocking findings

### B1 — Production provider composition is disabled

`tools/cloud_gateway/server.py` explicitly constructs `ProviderRouter(DisabledProvider(), DisabledProvider())`. This is the primary hard stop. The provider adapters are not composed into the running Gateway.

**Required:** implement a separate, explicit, fail-closed production composition factory. It must require complete validated configuration and live readiness dependencies, and must retain DisabledProvider for any provider that is not fully configured. Never infer readiness from the presence of environment variables alone.

### B2 — OIDC ingress is a deployment prerequisite, not a deployed component

The Gateway verifies signed proxy assertions, but `docs/oidc-ingress.md` confirms the repository does not register an identity-provider client or deploy an OIDC callback/session service and trusted reverse proxy.

**Required:** choose the actual identity provider and deploy a same-origin HTTPS edge that performs Authorization Code + PKCE, validates issuer/audience/signature/state/nonce/redirect URI and account status, maps verified groups to roles, strips all inbound `X-DCP-*` headers and signs fresh per-request assertions. Test login/logout, session revocation/expiry, spoofing and replay against the deployed edge.

### B3 — Azure network egress verification is missing

`AzureVMProvider` accepts an injected `network_policy_checker`; readiness fails unless that callback exists and returns true. No production checker is currently composed. The subnet/NSG resource IDs alone do not prove effective egress restrictions.

**Required:** implement an independently testable Azure network-policy verifier for the selected subnet, NSG and effective routes/rules. Verify deny-by-default inbound, no public IP, and only approved runner egress. Fail closed on unknown, stale or incomplete results.

### B4 — Azure guest login profile is not production-defined

The bootstrap factory requires an injected OS profile factory. A deployment-specific secure Linux/Windows guest profile is not composed. Verify access method, credential handling, local privilege boundaries, disk behavior and absence of a guest Managed Identity. The VM adapter and its tests currently omit the VM `identity` property; documentation must not claim a system-assigned identity is attached.

**Required:** implement and review the guest profile factory for both supported OS profiles, and prove workflow code cannot obtain the Gateway's managed identity or Key Vault credentials.

### B5 — Orka macOS path is incomplete

`OrkaProvider.readiness("macos")` deliberately returns false. The adapter sends only `vmConfig` and non-secret `customMetadata`; it does not yet implement protected Orka 4.0 User Data bootstrap. No authoritative Orka/MacStadium budget reader, forecast semantics or freshness policy is implemented.

**Required:** verify the exact deployed Orka API/User Data contract and secret protection; implement the protected macOS runner bootstrap; implement a separate Orka budget source and stale/unknown denial; verify online/job/teardown against the actual cluster.

### B6 — Live acceptance evidence does not exist

Current provider, bootstrap, budget and end-to-end tests use mocks. The read-only live Gateway smoke test is not a provisioning test.

**Required:** use a dedicated owner-approved staging subscription/cluster and one exact allowlisted repository. Capture evidence for create, runner online, one controlled job, offline confirmation, GitHub deregistration, VM deletion, NIC/VM absence and reconciliation after failure/timeout/cancellation. Confirm actual spend against the approved ceiling.

### B7 — Owner deployment inputs and cost approval are not present in repository evidence

Azure deployment requires subscription/tenant, resource group, region, DNS, OIDC issuer/client/role mapping, budget ceiling, GitHub App installation, VM SKU/image, network policy, guest login and retention decisions. Orka additionally requires cluster endpoint, namespace, VM config, secret reference and provider-specific cost authority.

**Required:** obtain these values through the owner's secure deployment process. Never request or commit passwords, tokens, private keys or raw secrets in Git or chat.

## Corrected documentation fact

`docs/azure-vm-provisioner.md` previously stated that the adapter assigns a system-assigned Managed Identity. The current `AzureVMProvider` VM payload does not include an `identity` property, and `tests/test_cloud_gateway_azure_vm.py` explicitly asserts that the property is absent. The deployment documentation must reflect the implemented no-identity guest boundary.

## Completion sequence and acceptance gates

1. **Identity and ingress:** deploy OIDC edge and same-origin HTTPS dashboard/API; pass login, logout, role, CSRF, Origin, spoofing, nonce replay and session expiry tests.
2. **Azure Linux/Windows composition:** implement guest profile and effective egress verifier; wire Azure VM adapter, GitHub App, online checker, Azure budget guard and cleanup only when all required dependencies are present.
3. **Azure staging acceptance:** create one Linux and one Windows ephemeral runner in an approved isolated environment; run a controlled job; prove GitHub deregistration and VM/NIC deletion; test failure injection and orphan reconciliation.
4. **Orka macOS composition:** implement protected User Data bootstrap and independent Orka budget; wire only after the target cluster contract is verified.
5. **Orka staging acceptance:** create one macOS runner, confirm online, run one controlled job, confirm offline, deregister, delete and verify absence.
6. **Security and regression:** run full unit/contract suite, provider-specific tests, live identity/browser tests, cleanup/failure tests and deployment preflight. Keep all unrelated deployment gates OFF.
7. **Release:** publish runbook, exact config contract, cost/rollback evidence and final acceptance report. Enable provisioning only after separate explicit approval of the exact provider, repository, region/cluster, spend ceiling and concurrency.

## Definition of done

- [ ] Same-origin HTTPS dashboard and deployed OIDC ingress pass live browser acceptance.
- [ ] Gateway production composition uses only explicitly configured and independently ready providers; all others remain disabled.
- [ ] Azure Linux and Windows each pass real runner-online, controlled-job, deregistration, VM/NIC deletion and orphan-reconciliation tests.
- [ ] Orka macOS passes equivalent live acceptance with protected bootstrap and independent budget.
- [ ] Provider-specific budget and global safety ceiling fail closed on unavailable, stale or over-limit data.
- [ ] Cloud Provisioning and VM Creation gates remain OFF until owner approval and all release gates pass.
- [ ] CI, regression, security and deployment preflight evidence is attached to the release.
- [ ] No secrets are committed or exposed; no resources remain after cleanup.
- [ ] Final report identifies exactly which OS/provider combinations are supported.

## Safety boundary

This audit is source inspection only. It does not deploy OIDC, access a cloud subscription/Orka cluster, change deployment secrets, enable Cloud Provisioning or VM Creation, or create billable resources. No live provider readiness is claimed.
