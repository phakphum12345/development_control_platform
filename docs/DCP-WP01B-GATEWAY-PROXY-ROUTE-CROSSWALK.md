# WP-01B — Gateway / Local Auth Proxy Route-Surface Crosswalk

**Repository:** `phakphum12345/development_control_platform`  
**Branch:** `docs/wp00-live-audit-20261123`  
**Source baseline:** `main` at `eaa9ceb91088c39b90d9b11b3817dc793e40005a`  
**Source blobs:** Gateway `9a55bccf216cff1b934bebd643e68364305449aa`; Proxy `2d8708216f85c28e70f358c0672152353c6b59bc`  
**Status:** IN_PROGRESS — static dispatch crosswalk only; no runtime acceptance claim.

## 1. Purpose and method

This document advances WP-01A by grouping the concrete path predicates observed in each HTTP handler into a reviewable crosswalk. It is deliberately not a claim that the API contract is complete. The review used the source lines listed below on the stated `main` baseline. Dynamic behavior, helper-level authorization, complete request schemas, response headers, and actual unsupported-method behavior still require executable tests.

## 2. Gateway GET dispatch crosswalk

| Source lines | Path predicate / family | Observed boundary or validation | Follow-up evidence |
|---|---|---|---|
| 331–343 | `/api/recon/…` prefix | Session and dashboard-role checks appear before response; service failures mapped | Exact subpaths, query schema, role matrix |
| 344–347 | `/healthz` exact | Returns bounded health payload | Assert no secrets and intended unauthenticated exposure |
| 349–373 | Document Workflow grants, target, proposal UUID | Owner role and configured-service checks; proposal matcher | UUID canonical form, query rejection, owner tests |
| 376–410 | Local Projects collection, roots, UUID descendant | Owner role; descendant UUID validation | Exact accepted descendant shape and path traversal tests |
| 411–424 | Terminal events matcher | Dashboard role and store availability | Exact regex, query schema, response data exposure |
| 426–436 | Terminal templates exact | Dashboard role and store availability | Role and cache/header tests |
| 442–537 | Jobs collection, UUID detail, logs, previews, artifacts, events | Dashboard role; UUID and pagination checks in branches | Exhaustive path/query matrix and owner-only preview tests |
| 538–545 | `/api/runners` exact | Authenticated dashboard session | Role visibility and credential redaction |
| 546–555 | Infrastructure gates exact | Dashboard role | Role matrix and gate-state disclosure |
| 556–587 | Infrastructure collection/descendants | Dashboard role; UUID checks on resource/event branches | Exact descendants and unsupported suffixes |
| 588–616 | Artifact download and related job artifact/event/log dispatch | Authenticated dashboard session; artifact storage checks | Identifier grammar, query rules, content disposition |
| 618–655 | `/v1/runner/…` GET protocol | Runner credentials and worker/job checks | Worker binding, cross-worker denial, token expiry/replay |
| 657–715 | Auth session, GitHub repositories/refs/project/commit | Authenticated session; repository and commit syntax validation | Per-route role and query matrix; repository authorization |
| 716–744 | Cloud Runner status/list/detail and provider status | Status/list and descendant dispatch | Owner/operator visibility, identifier grammar, provider data bounds |

## 3. Gateway POST dispatch crosswalk

| Source lines | Path predicate / family | Observed boundary or validation | Follow-up evidence |
|---|---|---|---|
| 871–968 | `/api/terminal/jobs` | Authenticated owner, same-origin, CSRF, idempotency key, disabled-template guard | Body size/schema, key grammar/replay/concurrency, no side effects on denial |
| 969–991 | Terminal grant revoke UUID matcher | Owner, origin, CSRF; consumed/revoked conflict handling | Exact matcher and replay tests |
| 992–1016 | `/api/terminal/authorize` | Owner, origin, CSRF | Body schema and grant lifecycle tests |
| 1017–1085 | Document Workflow grants/revoke/proposals/approve | Owner, origin, CSRF; field validation | Per-action schema, idempotency, audit trail |
| 1086–1111 | Infrastructure gate UUID/name matcher | Owner, origin, CSRF | Gate-name allowlist and state transition tests |
| 1112–1147 | Terminal template review matcher | Owner, origin, CSRF | Template ID grammar and review state tests |
| 1148–1168 | Terminal template import exact | Owner, origin, CSRF | Import body limits, content validation, no activation |
| 1169–1208 | Terminal command preview exact | Dashboard role, origin, CSRF | Command policy, preview-only guarantee, no execution side effect |
| 1209–1256 | Infrastructure collection/lifecycle descendants | Dashboard role, origin, CSRF; owner check for create; UUID/action checks | Full role/action matrix, idempotency, provider failure rollback |
| 1257–1406 | Jobs collection, previews, resume, cancel | Dashboard role, origin, CSRF; owner checks for sensitive operations; UUID and payload validation | Route-by-route schema, key behavior, state transition race tests |
| 1407–1546 | `/v1/runner/…` enrollment, heartbeat, claim, lease, logs, artifacts, finish | Runner credentials, worker registration/lease checks, content length/type/size checks for artifact upload | Token rotation/revocation, wrong-worker tests, request body boundaries |
| 1547–1606 | Dashboard Runner controls and Cloud Runner create | Authenticated session, origin, CSRF, owner role; provisioning readiness gates | Exact route grammar, approval/gate negative tests, no cloud side effects |
| 1607–1621 | `/v1/runners` create | Runner authentication and provisioning checks | Principal separation and registration replay tests |

## 4. Gateway DELETE dispatch crosswalk

| Source lines | Path predicate / family | Observed boundary or validation | Follow-up evidence |
|---|---|---|---|
| 1625–1643 | Exact job-preview UUID pair | Authenticated owner; combined same-origin/CSRF validation | Malformed UUID/query tests and idempotent stop behavior |
| 1644–1666 | Infrastructure descendant | Authenticated owner, origin, CSRF; resource UUID | Exact descendant allowlist and state-conflict tests |
| 1667–1684 | Cloud Runner descendant | Authenticated owner, origin, CSRF; runner identifier validation | Exact path/query grammar and termination failure behavior |
| 1688–1697 | Provider Runner prefix descendant | Runner authentication and identifier validation | Worker identity binding and unauthorized no-side-effect tests |

## 5. Local Auth Proxy GET crosswalk

| Source lines | Path predicate / family | Observed boundary or validation | Gateway relationship |
|---|---|---|---|
| 520–523 | `/healthz`, `/api/auth/session` | Explicit health/session handlers | Proxy-local endpoints |
| 535–568 | Job preview list/status UUID patterns | Authenticated session; query rejected; preview response size bounded | Forwards preview read to Gateway |
| 584–593 | Artifact download UUID pattern | Authenticated session; query rejected | Forwards artifact read |
| 595–657 | Explicit API GET allowlist | Session required; explicit predicates for GitHub, jobs, logs, artifacts, Terminal events, Infrastructure, Cloud Runner, and related bounded queries | Only approved subset is forwarded |
| 666–675 | Dashboard/static asset serving | Static path decoding and file resolution | Not a Gateway API route; audit traversal/symlink behavior separately |

### Proxy GET query constraints observed

- Preview list/status routes reject any query string.
- Artifact download rejects any query string.
- Infrastructure collection accepts only a bounded `limit=N` query form.
- Job list/log queries are parsed by explicit regular expressions in the allowlist block.
- Duplicate query keys, reordered parameters, blank values, percent-encoded separators, dot segments, and Unicode normalization still need explicit tests; do not infer behavior from a regex-only source read.

## 6. Local Auth Proxy POST crosswalk

| Source lines | Path predicate / family | Observed boundary or validation | Gateway relationship |
|---|---|---|---|
| 685–714 | Login exact | Same-origin; pre-auth CSRF; JSON validation; rate limit | Proxy-local auth then session creation |
| 715–724 | Logout exact | Authenticated session and CSRF | Proxy-local session termination |
| 726–764 | Jobs create/resume/cancel | Session + CSRF; JSON body; cancellation requires empty object | Forwards approved job mutations |
| 765–792 | Preview start UUID matcher | Session + CSRF; JSON body; response validation | Forwards preview creation |
| 793–806 | Infrastructure gate matcher | Session + CSRF; JSON body | Forwards approved gate mutation |
| 807–820 | Cloud Runner collection exact | Session + CSRF; exact collection path; JSON body | Forwards Cloud Runner create only |
| 821–837 | Terminal import/command preview/template review | Session + CSRF; JSON body | Forwards approved Terminal operations |
| 838–855 | Infrastructure create/lifecycle | Session + CSRF; lifecycle requires empty object; create forwards idempotency key | Forwards selected Infrastructure operations |
| 856–870 | Runner control matcher | Session + CSRF; empty object required | Forwards selected Runner controls |

## 7. Local Auth Proxy DELETE and OPTIONS crosswalk

| Source lines | Path predicate / family | Observed boundary or validation | Gateway relationship |
|---|---|---|---|
| 878–883 | All DELETE requests | Same-origin; query rejected; session + CSRF required | Shared preconditions |
| 884–895 | Job preview stop UUID pair | Exact matcher | Forwards preview stop |
| 896–905 | Infrastructure resource UUID | Exact matcher | Forwards Infrastructure delete |
| 906–910 | Cloud Runner descendant | Prefix plus segment-count check | Forwards Cloud Runner delete; stricter exact grammar needs test |
| 911–912 | OPTIONS | Explicit 405 response | Assert headers and no permissive CORS behavior |

## 8. Proxy-to-Gateway exposure differences requiring explicit intent

The Proxy GET allowlist is intentionally narrower than Gateway GET dispatch. The inspected Gateway has GET families for Recon, Document Workflow, Local Projects, Terminal templates, Runners, and runner protocol reads that are not represented as equivalent Proxy GET allowlist entries in the inspected Proxy dispatch block. This is not automatically a defect: some routes may be intentionally owner-only, service-only, or not Dashboard-exposed. Each must be marked **intentionally not proxied** or **required and missing**, with an owner and a test.

The Proxy POST surface similarly exposes only a subset of Gateway operations. Gateway runner protocol and some Document Workflow operations are not exposed by Proxy POST. Record the intended trust boundary; do not widen the Proxy allowlist merely to make the lists match.

## 9. Priority test matrix to close WP-01

| Test ID | Boundary | Positive assertion | Negative assertion |
|---|---|---|---|
| WP01-T01 | Unsupported methods | Document actual supported method response | PUT/PATCH/unknown verb has no mutation side effect |
| WP01-T02 | Proxy OPTIONS | Exact documented 405 and security headers | No wildcard CORS or credentialed cross-origin allowance |
| WP01-T03 | Origin/CSRF | Valid session, origin and CSRF succeeds on harmless test fixture | Missing, wrong-origin, missing-CSRF and invalid-CSRF requests do not reach service |
| WP01-T04 | Proxy GET allowlist | Every allowlisted route succeeds with valid session | Near-match path, extra segment, query duplicate and traversal variant denied |
| WP01-T05 | Proxy POST/DELETE allowlist | Every intended route forwards once | Unapproved path, query string, malformed ID and empty/nonempty body mismatch denied |
| WP01-T06 | Gateway direct access | Direct authenticated route enforces its own principal/role checks | Proxy-only assumptions cannot bypass Gateway authorization |
| WP01-T07 | Runner identity | Registered worker accesses only its own valid lease | Expired/revoked/replayed token and wrong-worker access denied |
| WP01-T08 | Idempotency | Same key and same request returns stable outcome | Conflicting payload, concurrent replay and cross-route key reuse handled safely |
| WP01-T09 | Parser bounds | Valid bounded JSON/object accepted | Missing/negative/oversized Content-Length, invalid UTF-8, malformed JSON and non-object body rejected |
| WP01-T10 | Response contract | Expected status, content type and security headers | Errors disclose no token, cookie, secret, stack trace or internal path |

## 10. Required disposition before acceptance

1. Review every route row with the Gateway and Proxy owners; classify each Proxy/Gateway difference as intentional or missing.
2. Convert this crosswalk into a machine-readable table or test parameter set only after the route inventory is independently reviewed.
3. Add focused tests in a separate code PR; do not mix runtime or test-code changes into this documentation-only PR.
4. Run targeted tests, complete Python test discovery, browser tests where applicable, and exact-head CI. Record skipped jobs separately.
5. Keep WP-01 **IN_PROGRESS** until every required route has positive and negative evidence and the direct Gateway boundary has been tested.
6. Do not merge, deploy, enable Terminal templates, or provision cloud resources as part of this inventory.

## 11. Non-claims

- This is a static route-surface crosswalk, not a penetration test.
- It does not prove all URL paths, request schemas, authorization predicates, or status/header behavior.
- It does not assert that the Proxy must expose every Gateway route.
- It does not prove Windows host acceptance or native isolation.
