# DCP Infrastructure Manager — Phase 1

## Scope

This increment introduces a DCP-owned, provider-neutral infrastructure inventory and lifecycle contract. It is deliberately local-first. The initial `FakeInfrastructureProvider` is a deterministic simulation and does not create VMs, containers, cloud resources, or paid capacity.

## Components

- `InfrastructureManager`: validates image/template compatibility, provider readiness, idempotency, and lifecycle operations.
- `InfrastructureStore`: durable SQLite inventory and credential-free lifecycle audit events.
- `InfrastructureProvider`: provider-neutral readiness/create/inspect/start/stop/delete contract.
- `FakeInfrastructureProvider`: simulation implementation for development and tests.
- Image catalog: pinned logical DCP image identifiers for Linux, Windows, and macOS.
- Template catalog: bounded CPU, memory, disk metadata for each target OS.

## Lifecycle

`provisioned -> running -> stopped -> running -> deleted`

Invalid transitions fail with a lifecycle conflict. Delete is idempotent. Resource creation is idempotent by caller-supplied key; reusing a key for a different OS/image/template is rejected.

## Safety

- External providers are disabled unless `provisioning_enabled=True` is explicitly supplied by a future composition layer.
- Fake provider is the only default provider and performs no external I/O.
- No Azure, Orka, Hyper-V, Apple host, network, or cloud SDK is called.
- No provider credentials or secrets are stored in the inventory.
- macOS image metadata is catalog metadata only; it is not evidence of macOS host availability or build readiness.
- This phase does not expose unauthenticated HTTP lifecycle endpoints or enable the existing Gateway provisioning route.

## Validation

Run:

```sh
python -m unittest tests.test_cloud_gateway_infrastructure -v
```

The tests use temporary SQLite databases and the fake provider only. Live infrastructure acceptance remains a separate, explicitly approved phase.

## Authenticated Gateway API — Phase 2

The Gateway composes a persistent `InfrastructureManager` using
`DCP_GATEWAY_INFRA_DATABASE` (defaults to the gateway database path plus
`.infra`) and registers only the `fake` provider. The composition hard-codes
`provisioning_enabled=False`; it is not enabled by an environment variable.

All browser endpoints require a trusted proxy identity. Mutating requests also
require the configured exact same-origin and server-issued CSRF token.

| Method | Route | Permission | Purpose |
| --- | --- | --- | --- |
| GET | `/api/infrastructure?view=catalog` | owner/operator | Provider, image and template catalog |
| GET | `/api/infrastructure` | owner/operator | Resource inventory |
| GET | `/api/infrastructure/{uuid}` | owner/operator | Inspect one resource |
| GET | `/api/infrastructure/{uuid}/events` | owner/operator | Lifecycle audit |
| POST | `/api/infrastructure` | owner/operator | Create fake resource; requires Idempotency-Key |
| POST | `/api/infrastructure/{uuid}/start` | owner/operator | Start simulation |
| POST | `/api/infrastructure/{uuid}/stop` | owner/operator | Stop simulation |
| POST | `/api/infrastructure/{uuid}/restart` | owner/operator | Restart simulation |
| DELETE | `/api/infrastructure/{uuid}` | owner | Delete simulation |

The dashboard's Infrastructure Manager view talks only to the same-origin
Gateway API. It does not hold Gateway credentials or call provider SDKs.
GitHub Pages/static-only deployments cannot perform these operations without
the trusted authenticated API backend.

## Validation

```sh
python -m unittest tests.test_cloud_gateway_infrastructure -v
python -m unittest tests.test_cloud_gateway_infrastructure_api -v
```

The API tests sign local proxy assertions and run against an ephemeral loopback
HTTP server with temporary SQLite files. They exercise owner/operator access
and the fake provider only.

## Fake lifecycle acceptance — Phase 3

The manager and authenticated API tests verify that the provider's state and
the SQLite inventory agree after each valid lifecycle action:
`provisioned -> running -> stopped -> running -> deleted`. The manager test
also reopens the SQLite store to verify the terminal state and audit history
are durable. Repeated delete is verified as idempotent without another
provider call. These checks use only the in-memory fake provider and temporary
local databases; they do not establish live cloud or VM readiness.

## Independent Infrastructure Control Gates — Phase 4

The Gateway now stores two independent owner-controlled switches in a dedicated
SQLite database (DCP_GATEWAY_GATES_DATABASE, defaulting to the Gateway
database path plus .gates):

- cloud_provisioning: controls the live cloud runner provisioning path.
- vm_creation: controls non-fake VM/provider creation paths.

Both gates are inserted OFF on first startup and survive Gateway restarts.
The authenticated API is:

| Method | Route | Permission | Purpose |
| --- | --- | --- | --- |
| GET | /api/infrastructure/gates | owner/operator | Read both switch states and provider readiness |
| POST | /api/infrastructure/gates/{cloud_provisioning or vm_creation} | owner | Change one switch; requires same-origin and CSRF |

Enabling requires an exact, gate-specific confirmation phrase and a ready
provider capability. The backend rejects enabling while provider readiness or
static safety configuration is unavailable. The cloud runner create route
requires the effective Cloud Provisioning gate in addition to the existing
owner approval, budget, repository, concurrency, and circuit-breaker checks.
Non-fake Infrastructure Manager create requests require the effective VM
Creation gate; the current composition still registers only the fake provider
and sets manager provisioning to OFF.

A stored ON state is not by itself proof of operational readiness:
effective_enabled is true only while the corresponding provider capability
is ready. Gate changes are audited with actor and timestamp. These switches
do not enable any provider in the current deployment and do not authorize
paid resources. CI uses temporary SQLite databases and fake/no providers only.
