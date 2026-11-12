# OIDC ingress and trusted identity assertions

## Deployment shape

```text
Browser
  -> HTTPS reverse proxy / OIDC middleware
       -> Authorization Code + PKCE, state, nonce, exact callback URI
       -> server-managed Secure + HttpOnly session cookie
       -> verified OIDC claims (sub + groups)
       -> DCP assertion signer (private network only)
            -> per-request HMAC identity headers
            -> DCP Gateway (same public HTTPS origin)
                 -> CSRF + Origin + role + replay checks
```

GitHub Pages is static hosting and cannot issue server-side session cookies or
run an OIDC callback. Serve the dashboard and `/api/*` behind one HTTPS origin
using a reverse proxy, or use a host that serves both. Do not configure the
browser to send credentials to a different API origin and assume cookies are
same-origin.

## OIDC middleware contract

The upstream OIDC middleware is responsible for validating the provider's JWT
signature against its JWKS, exact issuer, audience, expiry, issue time, state,
nonce, and exact redirect URI. Use Authorization Code flow with PKCE. The
middleware must manage its protected OIDC session cookie and set
`Secure; HttpOnly; SameSite=Lax` (or stricter compatible) attributes. The DCP
edge signer separately creates a random, stateless HMAC-protected session cookie
bound to the verified subject for CSRF session binding. Do not return ID tokens,
access tokens, refresh tokens, client secrets, or the HMAC secret to browser
JavaScript.

Pass only the already-verified claims to
`sign_verified_oidc_assertion`. The helper re-checks issuer, audience, exp,
iat, subject format and group-to-role mapping, then signs a request-bound
assertion. **It does not verify the OIDC JWT signature itself.** It must never
be called with claims supplied directly by the browser or an untrusted header.

Use the stable OIDC `sub` claim as `X-DCP-User`; do not use email as a durable
account identifier. Map explicit verified groups:
- `DCP_OIDC_OWNER_GROUPS` -> `owner`
- `DCP_OIDC_OPERATOR_GROUPS` -> `operator`
- No matching group -> deny
- Owner wins if a user belongs to both groups

The proxy signer generates a fresh nonce for every request and binds the HTTP
method, URL path, subject, role, session ID, timestamp and nonce using
HMAC-SHA256. It emits only these internal headers:
- `X-DCP-User`
- `X-DCP-Role`
- `X-DCP-Session`
- `X-DCP-Auth-Timestamp`
- `X-DCP-Auth-Nonce`
- `X-DCP-Auth-Signature`

The reverse proxy must **strip every inbound `X-DCP-*` header** from the
browser request before it invokes the signer, and must forward only the
freshly generated assertion headers. The signer must be reachable only over a
private local channel (loopback or Unix socket), never directly from the
Internet. The Gateway's internal bearer token is separate and must not be
forwarded to the browser.

## Replay, CSRF and origin controls

`ProxyIdentityVerifier` validates the HMAC, timestamp window, role and nonce.
When created by `make_handler`, it uses the Gateway SQLite store for durable
nonce consumption. Replays across verifier instances are rejected; if the
nonce database is unavailable, authentication fails closed. The current
deployment is a single Gateway using one SQLite database. A horizontally
scaled deployment needs one shared transactional nonce store before it is
supported.

The Gateway separately requires:
- exact configured `Origin` on state-changing operations;
- a session-bound CSRF token in `X-CSRF-Token`;
- server-side owner/operator authorization on every protected endpoint;
- `Cache-Control: no-store` on API responses;
- no wildcard credentialed CORS;
- no logging of cookies, tokens, identity headers, or request bodies.

OIDC logout must revoke the server session and clear the cookie. Password reset,
account recovery, session revocation, user lifecycle and audit retention remain
identity-provider/application deployment responsibilities.

## Required server-side configuration

- `DCP_PUBLIC_ORIGIN`: exact HTTPS origin serving both UI and API.
- `DCP_TRUSTED_PROXY_HMAC_SECRET`: random secret of at least 32 characters,
  stored server-side only (e.g. Key Vault).
- OIDC issuer URL and API audience for the selected identity provider.
- Separate owner and operator group IDs.
- OIDC client ID and client secret stored server-side.
- Exact callback and post-logout redirect URIs registered with the provider.

Never place any of these values in dashboard HTML, JavaScript, query strings,
Git history, browser storage, screenshots, or support logs.

## Loopback oauth2-proxy reference edge

The repository now includes a concrete reference integration:

- `tools/cloud_gateway/oidc_edge_signer.py` is a private auth-request service.
  For each request it calls the loopback-only oauth2-proxy `/oauth2/auth`
  endpoint. Only a successful `202` response with a stable subject and
  verified groups can produce DCP identity headers.
- `deploy/oidc-edge/nginx.conf` serves the dashboard and routes same-origin
  `/api/*` requests to the Gateway. It protects both the dashboard and API,
  keeps `/oauth2/*` as the login/callback path, and returns JSON 401 for API
  requests that lack an authenticated session.
- `tests/test_cloud_gateway_oidc_edge_signer.py` and
  `tests/test_cloud_gateway_oidc_ingress_contract.py` cover the signer and
  ingress header boundary with mocks/static contract assertions.

Configure oauth2-proxy as an OIDC provider with the exact issuer, client ID,
audience, callback and cookie secret for the deployment. Set the exact external
`--redirect-url=https://<host>/oauth2/callback` and
`--whitelist-domain=<host>`; replace the Nginx template's catch-all
`server_name _` with the approved hostname and have the trusted ingress reject
HTTP and unknown hosts. Required behavior:

- Pin a reviewed stable oauth2-proxy release and enable
  `--provider=oidc`, `--reverse-proxy=true`,
  `--set-xauthrequest=true`, `--oidc-groups-claim=groups`, and
  `--upstream=static://202`.
- Keep `--pass-user-headers=false` and `--pass-basic-auth=false`. The
  `/oauth2/auth` response headers are consumed only by the signer; they are
  never forwarded as user headers to the Gateway.
- In oauth2-proxy's OIDC provider, `X-Auth-Request-User` must resolve to the
  immutable OIDC `sub` claim (the normal OIDC user-claim default), not an
  email or mutable display name. Verify the actual header from a test login;
  do not rely on a configuration label alone.
- Ensure `X-Auth-Request-Groups` contains the verified, stable group IDs used
  by the owner/operator mapping. Group overage or a missing groups claim must
  deny access rather than falling back to email.
- Keep `--pass-access-token=false`,
  `--pass-authorization-header=false`, and
  `--set-authorization-header=false`; browser tokens are not forwarded to
  DCP.
- Keep the oauth2-proxy cookie Secure and HttpOnly, use SameSite=Lax for the
  OIDC top-level callback, and bind its HTTP listener to
  `127.0.0.1:4180`. The separate DCP edge-session cookie is stricter
  SameSite=Strict.
- Use a Secure, HttpOnly OIDC cookie named `_oauth2_proxy` (or set
  `DCP_OIDC_PROXY_COOKIE_NAME` to the configured name), and keep oauth2-proxy
  bound to `127.0.0.1:4180`.
- The signer calls only
  `http://127.0.0.1:4180/oauth2/auth`. It rejects non-loopback auth URLs,
  redirects, non-202 responses, missing sessions, malformed subjects and
  identities without an explicitly configured owner/operator group.

The signer requires these server-only settings:

- `DCP_OIDC_ISSUER`: exact OIDC issuer URL.
- `DCP_OIDC_AUDIENCE`: exact client/API audience verified by oauth2-proxy.
- `DCP_OIDC_OWNER_GROUPS` and `DCP_OIDC_OPERATOR_GROUPS`: comma-separated
  immutable group IDs; the sets must be nonempty and disjoint.
- `DCP_TRUSTED_PROXY_HMAC_SECRET`: the same random 32+ byte secret used by
  the Gateway verifier.
- `DCP_OIDC_PROXY_AUTH_URL`: defaults to the loopback oauth2-proxy endpoint.
- `DCP_OIDC_PROXY_COOKIE_NAME`: defaults to `_oauth2_proxy`.
- `DCP_OIDC_EDGE_SESSION_COOKIE_NAME`: defaults to
  `__Host-dcp_edge_session`; it is HttpOnly, Secure, SameSite=Strict, Path=/,
  and has no Domain attribute.
- `DCP_OIDC_EDGE_SESSION_SECONDS`: 300..43200 seconds; default 28800.
- `DCP_OIDC_SIGNER_HOST=127.0.0.1` and `DCP_OIDC_SIGNER_PORT=8790`.

The edge-session cookie is separately HMAC-bound to the OIDC subject and
provides a stable session ID for DCP CSRF binding. It is not an OIDC token and
is never sent to the Gateway. The signer emits a fresh per-request nonce and
HMAC assertion only after oauth2-proxy confirms the session. The Nginx
configuration overwrites all six `X-DCP-*` headers from the signer and strips
browser Cookie and Authorization headers before proxying to the Gateway.

The Nginx template assumes:
- TLS terminates at a trusted ingress that rejects HTTP and preserves the
  external HTTPS origin.
- Nginx, oauth2-proxy, signer and Gateway share a private network namespace.
- Nginx is the only externally exposed container/port (8080).
- oauth2-proxy listens on loopback port 4180, signer on loopback 8790, and
  Gateway on loopback 8789.
- Dashboard files are mounted at `/usr/share/nginx/html`.

Do not expose the signer or Gateway ports directly. Do not place client secrets,
cookie secrets, or HMAC material in the Nginx configuration or dashboard.

## Current status and acceptance gate

The repository includes the assertion-signing helper, durable SQLite replay
protection, loopback oauth2-proxy identity signer, Nginx same-origin ingress
template, and mock/static contract tests. These are deployable building blocks,
not a configured production identity service. They do not register an OIDC
client, configure a tenant/domain, deploy a TLS ingress, provision container
sidecars, or enable live sign-in. GitHub Pages alone is insufficient.

Before enabling OIDC in production, supply the real issuer, audience, owner and
operator group IDs, public HTTPS origin, callback URL and secret-store
references. Then run browser acceptance for login, logout, invalid issuer,
invalid audience, expiry, nonce/state mismatch, CSRF, role denial, direct API
header spoofing, replay across process restarts, and iPhone Safari. Do not
enable provider provisioning as part of OIDC setup.
