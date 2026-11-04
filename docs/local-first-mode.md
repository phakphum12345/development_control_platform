# DCP Local-first Mode

DCP is developed and validated locally first. Cloud providers are optional
adapters, not prerequisites for the dashboard, Gateway contracts, evidence
model, tests, or local development workflow.

## Cost and safety defaults

- Do not create paid VMs, managed services, storage accounts, or subscriptions
  to run unit, contract, browser, or mock-provider tests.
- Keep `DCP_GATEWAY_PROVISIONING_ENABLED=false`.
- Keep provider credentials out of source files, shell history, browser storage,
  test fixtures, logs, and issue/PR comments.
- Use mock/fake provider clients for Azure and Orka contract tests. Tests must
  assert that no outbound provider call occurs unless a separately approved
  live-acceptance procedure is being run.
- A mock-provider PASS proves the adapter contract only; it does not prove that
  a cloud VM or a GitHub runner was actually provisioned.
- Prefer an existing local Windows/Linux/macOS host runner when available.
  Registering a self-hosted runner is an explicit GitHub-side action and should
  use GitHub's short-lived registration instructions locally. Never paste the
  registration token into ChatGPT, source code, or CI logs.
- Use Docker/Podman only when already installed and available. The local doctor
  does not install packages or start the container daemon.

## Run the local environment doctor

From the repository root:

```sh
python -m tools.cloud_gateway.local_mode
```

The command is read-only. It checks Python, SQLite, optional Git and container
runtime executables, and whether cloud provisioning is disabled. It does not
open a port, start a server, contact GitHub/Azure/Orka, inspect secret values,
or create resources.

Statuses have explicit meaning:

- `PASS`: the local check was verified.
- `FAIL`: a local-first safety or runtime requirement is violated.
- `UNKNOWN`: an optional local tool was not found or could not be verified.
- `SKIPPED`: the check intentionally performs no network/cloud action.

## Run tests without cloud credentials

```sh
python -m unittest discover -s tests -v
```

The Azure and Orka adapter tests must use deterministic fake HTTP/credential
clients. They must not require a subscription, a MacStadium account, or a
provider API token.

## Dynamic local Gateway port

The Gateway accepts `DCP_GATEWAY_PORT=0` to let the operating system allocate
an available port. The selected port is reported after binding. A fixed port is
not required. Keep the default bind address on loopback unless a separately
reviewed deployment explicitly needs another interface.

## Start the fail-closed local Gateway

The API can be run locally without any provider account. It still uses
`DisabledProvider`, so runner creation is denied; this is useful for checking
health and the HTTP service boundary without provisioning anything.

PowerShell (Windows):

```powershell
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$bytes = New-Object byte[] 32
$rng.GetBytes($bytes)
$env:DCP_GATEWAY_API_TOKEN = [Convert]::ToBase64String($bytes)
$rng.Dispose()
$env:DCP_GATEWAY_PROVISIONING_ENABLED = "false"
$env:DCP_GATEWAY_PORT = "0"
$env:DCP_GATEWAY_DATABASE = Join-Path $env:TEMP "dcp-gateway-local.sqlite3"
python -m tools.cloud_gateway.server
```

The token is generated in process memory and is not printed. The server binds
to loopback and prints the OS-assigned port. Open the printed `/healthz` URL
locally to confirm health. Stop it with Ctrl+C. The local database contains
lifecycle/audit records only; do not commit it.

For macOS/Linux, generate the token directly into the current shell environment
without echoing it:

```sh
export DCP_GATEWAY_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export DCP_GATEWAY_PROVISIONING_ENABLED=false
export DCP_GATEWAY_PORT=0
export DCP_GATEWAY_DATABASE="${TMPDIR:-/tmp}/dcp-gateway-local.sqlite3"
python -m tools.cloud_gateway.server
```

## What remains intentionally unproven

Local mode does not claim that cloud infrastructure is ready. Azure VM
provisioning, Orka VM creation, external network policy, GitHub runner online
registration, real workflow execution, and remote teardown remain
`UNKNOWN` until independently verified. They are not required to develop the
DCP core or run its local test suite.
