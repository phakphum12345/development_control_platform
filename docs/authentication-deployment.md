# Password authentication deployment contract

## Current repository boundary

The dashboard is a static GitHub Pages site. GitHub Pages does not run server-side password verification or issue authenticated session cookies. The browser integration in `dashboard/index.html` is deliberately fail-closed: it never accepts a client-side/demo password and never stores credentials or session tokens in browser storage.

**Password login is not production-ready until a real backend is deployed and these checks pass.** The UI expects same-origin endpoints under `/api/auth/`; the current static site does not provide those endpoints. Configure a same-origin reverse proxy/API or deploy the dashboard and API behind one HTTPS origin before enabling sign-in.

## Required endpoints

- `GET /api/auth/session` → `{ "authenticated": true, "csrfToken": "...", "user": { "displayName": "..." } }` or `{ "authenticated": false, "csrfToken": "..." }`. Issue a session-bound CSRF token even for an unauthenticated session, and rotate it when appropriate.
- `POST /api/auth/login` with JSON `{ "username": "...", "password": "..." }` → `{ "authenticated": true, "user": { "displayName": "..." } }`
- `POST /api/auth/logout` → `{ "authenticated": false }`

The server must set and clear the session cookie; do not return a session token to JavaScript. The UI sends the separate server-issued CSRF token in `X-CSRF-Token` for login/logout POST requests and keeps it in tab memory only. Use HTTPS and a cookie with `Secure; HttpOnly; SameSite=Lax` (or stricter compatible policy), server-side expiry and revocation. Rotate session IDs after login and privilege changes. Apply CSRF protection to state-changing requests, rate limiting and progressive throttling to login, generic authentication errors, password hashing with a modern password-hashing algorithm (Argon2id preferred), and server-side authorization on every protected operation. Never log passwords, cookies, or session identifiers.

The API must return `Cache-Control: no-store` for authentication responses. Configure CORS narrowly (ideally same-origin); do not use wildcard origins with credentials. Add account recovery, password reset, audit events, and an explicit account lifecycle before real users depend on this.

## PWA security and offline behavior

The service worker caches only the static application shell. Requests under `/api/` are network-only and never cached. Offline mode does not imply authenticated access and must not allow protected operations. On shared devices, sign out and close the installed app when finished.

## Mapping and verification checklist

- [ ] Confirm the deployed API origin and hosting/reverse-proxy configuration.
- [ ] Verify session cookie flags and rotation in a real HTTPS browser.
- [ ] Verify invalid credentials, throttling, CSRF, expiry, logout and revoked sessions.
- [ ] Verify unauthorized users cannot call protected APIs directly.
- [ ] Verify service-worker cache contains no API responses, credentials or private data.
- [ ] Run iPhone Safari and Android Chrome install/offline smoke tests.
- [ ] Inspect results for the exact tested commit SHA; skipped jobs are not passes.


## Multiple applications and login systems (recommended deployment shape)

Use one standards-based OpenID Connect (OIDC) identity provider as the identity broker, with a **separate registered client for each application**. Password sign-in and Google sign-in are provider-managed identity methods; they must not be implemented as competing client-side sessions. Each app keeps its own callback/redirect allowlist, client ID, audience/API permissions, logout redirect and authorization policy. Map provider subject IDs to local app roles server-side; do not use an email address alone as a durable account key.

For the DCP dashboard and any future apps:
- Keep the Research OS owner Google OAuth handoff separate from end-user sign-in. It grants a different capability and must not silently create a DCP session or confer owner privileges.
- Prefer serving the dashboard and auth callback/API behind one HTTPS origin (custom domain plus reverse proxy, or a host that serves both). GitHub Pages alone cannot host the session API. Do not point the dashboard at an unrelated Render origin and assume same-origin cookies will work.
- Use Authorization Code flow with PKCE for browser-based clients; validate issuer, audience, signature, state, nonce and exact redirect URI. Keep client secrets only on the server. Use Secure, HttpOnly, appropriately scoped cookies for server-managed sessions, and CSRF protection on state-changing requests.
- Isolate apps by client ID, redirect URI, API audience and role/permission policy. A shared identity provider can provide SSO without sharing application sessions or permissions.
- Before production enablement, configure the identity-provider tenant, verified domain/redirect URLs, persistent user/account lifecycle and recovery, server secrets, rate limiting, session revocation, audit events and deployment monitoring. Never seed a default password or pretend a missing backend is available.

This repository currently has no configured identity-provider tenant or deployed /api/auth/* service. The recommendations above are the target architecture, not evidence that login is live.
