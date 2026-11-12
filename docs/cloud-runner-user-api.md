# Cloud Runner browser control API

## Deployment boundary

The browser control API is part of the Cloud Runner Gateway. It must be deployed behind a trusted HTTPS reverse proxy on the **same public origin** as the dashboard. GitHub Pages alone cannot execute these endpoints, issue sessions, or protect server credentials. A static-only Pages deployment will correctly show UNKNOWN and keep Start disabled.

Required environment:
- `DCP_GATEWAY_API_TOKEN`: private service-to-service bearer credential for the existing `/v1/runners` API.
- `DCP_TRUSTED_PROXY_HMAC_SECRET`: random secret of at least 32 characters, shared only between the trusted ingress and Gateway.
- `DCP_PUBLIC_ORIGIN`: exact public HTTPS origin, e.g. `https://dcp.example.com`; no path or trailing slash.
- Existing Azure budget configuration is required before provisioning can ever be authorized.

The Gateway should bind to loopback/private networking. Never expose its listener directly to the public internet. The reverse proxy must authenticate users with a real OIDC provider, strip **all** incoming `X-DCP-*` headers, then inject a fresh signed identity assertion on every request. Do not trust browser-supplied identity headers. The proxy must validate issuer, audience, signature, state, nonce, exact redirect URI, account status, and the user's DCP role before signing.

## Signed identity assertion

The proxy injects these headers:
- `X-DCP-User`: immutable OIDC subject identifier (not a user-editable display name).
- `X-DCP-Role`: exactly `owner` or `operator`.
- `X-DCP-Session`: opaque session identifier, 16–128 URL-safe characters.
- `X-DCP-Auth-Timestamp`: current Unix timestamp in seconds.
- `X-DCP-Auth-Nonce`: fresh random 16–128 URL-safe characters for every request.
- `X-DCP-Auth-Signature`: lowercase hex HMAC-SHA256 using the shared secret.

The signature is calculated over UTF-8 bytes of the following fields joined with one newline, in this exact order:

```text
HTTP_METHOD
URL_PATH_WITHOUT_QUERY
OIDC_SUBJECT
DCP_ROLE
SESSION_ID
UNIX_TIMESTAMP
NONCE
```

The Gateway checks the signature, role, timestamp window (±60 seconds), and one-time nonce. Replayed nonces are rejected. Use a single Gateway instance unless the nonce replay cache is moved to a shared atomic store. The reverse proxy must prevent direct public access to the Gateway listener and must overwrite, not append, the identity headers.

## Browser API

All responses use `Cache-Control: no-store`. CORS is not enabled. Mutating requests require an exact `Origin` match with `DCP_PUBLIC_ORIGIN` and a session-bound CSRF token.

- `GET /api/auth/session`: verifies the signed assertion and returns a CSRF token held in tab memory only. No session cookie or secret is returned by Gateway; the OIDC proxy owns the browser session.
- `GET /api/cloud-runners/status`: returns Gateway, owner-approval, provisioning, live budget, bootstrap, and per-platform readiness. Missing budget data is UNKNOWN, never PASS. The top-level `budget_gate` is the legacy Azure summary; `provider_budget_gates[linux|windows|macos]` is authoritative for the selected platform.
- `GET /api/cloud-runners`: lists recent runner metadata only; never returns request payloads or credentials.
- `GET /api/cloud-runners/{id}`: reads a runner lifecycle state.
- `POST /api/cloud-runners`: requires signed identity, exact Origin, CSRF token, and idempotency key.
- `DELETE /api/cloud-runners/{id}`: requires signed identity, exact Origin, and CSRF token.

The current browser API role gate permits owner/operator. Runner creation checks the selected platform's own budget gate (Azure for Linux/Windows, Orka for macOS); an Azure budget PASS is never used as Orka budget evidence. The Gateway also independently enforces repository allowlist, owner approval, provisioning flag, the global safety ceiling, provider-specific budget authorization, concurrency, runtime, idempotency and provider readiness. A browser role is not a substitute for those policy checks.

## Readiness and current limits

The default API runtime remains fail-closed. Azure provider composition is available only through explicit opt-in and requires live ARM/Firewall verification, pinned images, guest profile, GitHub App identity, live budget and runner-online/cleanup acceptance. Orka now has a protected User Data bootstrap contract, but remains disabled pending authoritative provider-specific budget, live cluster/VM Tools, namespace RBAC and egress verification. Live runner-online, job execution, teardown and post-delete evidence are required. Create requests remain blocked until all provider-specific and global gates pass.

This PR does not configure an OIDC tenant, deploy a reverse proxy, set production secrets, activate Azure/Orka, or create cloud resources. Those require explicit operator setup and a separately reviewed deployment. Never put the proxy HMAC secret, Gateway bearer token, Azure credential, Orka token, GitHub App private key, or runner registration token in the dashboard, query string, browser storage, logs, or Git history.

## Required production acceptance checks

- [ ] OIDC login/logout, account disable/revocation, role changes, MFA policy and session expiry tested at the ingress.
- [ ] Direct public Gateway access is blocked; spoofed and appended `X-DCP-*` headers fail.
- [ ] Invalid signature, expired timestamp, nonce replay, viewer role, wrong Origin, missing CSRF and expired session fail closed.
- [ ] Authenticated owner/operator can read status and runner inventory; other roles cannot.
- [ ] Budget API unavailable or forecast over cap prevents all provisioning.
- [ ] Provider readiness remains false until bootstrap and runner-online checks pass.
- [ ] Browser and service-worker caches contain no private API responses or credentials.
- [ ] iPhone Safari and desktop browser tests pass against the exact deployed commit.
