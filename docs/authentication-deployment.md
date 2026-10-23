# Password authentication deployment contract

## Current repository boundary

The dashboard is a static GitHub Pages site. GitHub Pages does not run server-side password verification or issue authenticated session cookies. The browser integration in `dashboard/index.html` is deliberately fail-closed: it never accepts a client-side/demo password and never stores credentials or session tokens in browser storage.

**Password login is not production-ready until a real backend is deployed and these checks pass.** The UI expects same-origin endpoints under `/api/auth/`; the current static site does not provide those endpoints. Configure a same-origin reverse proxy/API or deploy the dashboard and API behind one HTTPS origin before enabling sign-in.

## Required endpoints

- `GET /api/auth/session` → `{ "authenticated": true, "user": { "displayName": "..." } }` or `{ "authenticated": false }`
- `POST /api/auth/login` with JSON `{ "username": "...", "password": "..." }` → `{ "authenticated": true, "user": { "displayName": "..." } }`
- `POST /api/auth/logout` → `{ "authenticated": false }`

The server must set and clear the session cookie; do not return a session token to JavaScript. Use HTTPS and a cookie with `Secure; HttpOnly; SameSite=Lax` (or stricter compatible policy), server-side expiry and revocation. Rotate session IDs after login and privilege changes. Apply CSRF protection to state-changing requests, rate limiting and progressive throttling to login, generic authentication errors, password hashing with a modern password-hashing algorithm (Argon2id preferred), and server-side authorization on every protected operation. Never log passwords, cookies, or session identifiers.

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
