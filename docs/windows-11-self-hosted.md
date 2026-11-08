# Windows 11 self-hosted deployment (local resources)

**Status:** local-host setup guide. This does not claim production readiness, authenticated browser-to-Gateway integration, or dynamic runner provisioning.

This deployment uses the Windows 11 PC's own CPU, memory, and disk. It does not create Azure resources or require a paid cloud subscription. Electricity, internet access, and any optional third-party software remain the owner's responsibility.

## 1. What runs on this PC

| Component | Local behavior | Current limitation |
| --- | --- | --- |
| Dashboard | Static web UI served on loopback by `Start-DCP-Dashboard.ps1` | It is not a secured public website. |
| Gateway | Python HTTP service on loopback; SQLite lifecycle/audit store | Production provider composition is still `DisabledProvider`; runner creation is intentionally unavailable. |
| Local tests | Python unit/contract tests; optional Node.js/Playwright browser smoke tests | Mock tests do not prove a real runner is online. |
| Self-hosted GitHub Actions runner | Optional GitHub runner process on this PC | It executes workflows only after you register it with GitHub. It is not the DCP cloud-runner provider. |

The current Dashboard does not yet have a complete local OIDC/session edge that securely connects its browser controls to the Gateway's `/api/*` routes. Do not put a Gateway bearer token in browser JavaScript or browser storage. The Gateway's token-protected `/v1/*` API is for trusted local/service clients only.

## 2. Windows 11 prerequisites

- Windows 11 x64 with a supported PowerShell.
- Python 3.10 or newer (Python 3.12+ is recommended for the full validation workflow).
- Git for Windows.
- Optional: Node.js LTS and npm for Playwright browser smoke tests.
- Optional: Docker Desktop with the WSL 2 backend, only if a future local workload specifically needs containers. The current local Gateway does not require Docker.

Open PowerShell in the repository root. Confirm the tools:

```powershell
py --version
git --version
node --version   # optional
docker version   # optional; may require Docker Desktop to be running
```

Do not install Docker solely to run the Gateway or unit tests.

## 3. Check the local environment

```powershell
py -3 -m tools.cloud_gateway.local_mode
py -3 -m unittest discover -s tests -v
```

The environment doctor is read-only. It does not install software, start services, open ports, or contact Azure/Orka. A missing optional Docker/Podman executable is not a blocker for the local Gateway.

## 4. Start the Dashboard

Double-click `Open-DCP-Dashboard.cmd`, or run:

```powershell
.\Start-DCP-Dashboard.ps1 -OpenBrowser
```

The launcher serves only the static Dashboard on `127.0.0.1` and chooses an available port. It does not start the Gateway or authenticate a user.

## 5. Start the fail-closed local Gateway

Open a second PowerShell window in the repository root. Generate a temporary API token in that PowerShell process and start the Gateway:

```powershell
$env:DCP_GATEWAY_API_TOKEN = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$env:DCP_GATEWAY_HOST = "127.0.0.1"
$env:DCP_GATEWAY_PORT = "8789"
$env:DCP_GATEWAY_PROVISIONING_ENABLED = "false"
$env:DCP_GATEWAY_OWNER_APPROVED = "false"
$env:DCP_GATEWAY_DATABASE = Join-Path $env:LOCALAPPDATA "DCP\gateway.sqlite3"
python -m tools.cloud_gateway.server
```

Keep this PowerShell window open while the Gateway is running. The token is not printed; it exists only in that process environment. Stop the Gateway with Ctrl+C. The SQLite file is stored outside the Git repository under your Windows user profile.

In another PowerShell window, check the health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8789/healthz
```

The Gateway binds to loopback only. Do not change the host to `0.0.0.0`, add a router port-forward, or expose this service to the internet as part of this local setup.

## 6. Optional: use this PC as a GitHub Actions self-hosted runner

A GitHub Actions self-hosted runner lets GitHub send eligible workflow jobs to this PC. It is separate from the DCP Gateway and does not make DCP capable of creating or managing ephemeral runners.

1. Open the repository on GitHub.
2. Go to **Settings → Actions → Runners → New self-hosted runner**.
3. Select **Windows** and **x64**.
4. Follow the exact setup commands shown by GitHub in a local PowerShell window. The registration token is short-lived; never paste it into ChatGPT, a commit, an issue, or a log.
5. Start with the runner in interactive mode. Configure it as a Windows service only after reviewing the repository workflows and deciding that the machine may execute them unattended.
6. Use a dedicated Windows account and a machine/workspace that contains no personal secrets. Do not run untrusted pull-request code on a self-hosted runner with access to private files or credentials.

Do not add broad labels or enable privileged workflows without reviewing their permissions and triggers.

## 7. Data, backups, and safe operation

- Repository source remains in the Git working tree.
- Gateway lifecycle/audit data is in `%LOCALAPPDATA%\DCP\gateway.sqlite3`.
- Back up the SQLite database only after stopping the Gateway, or use a SQLite-consistent backup method.
- Keep Windows Defender Firewall enabled. Loopback-only binding is the default boundary.
- Keep cloud provisioning and owner approval false. Do not set either to true in a local-only installation.
- Do not commit database files, local tokens, runner registration tokens, or environment dumps.

## 8. What is not yet production-ready

This local installation is useful for development, local health checks, contract testing, and optionally running GitHub Actions jobs on your own PC. It is **not** a completed production control plane yet. In particular:

- Dashboard OIDC login/session service and trusted same-origin edge are not implemented here.
- Browser-facing `/api/*` routes require trusted proxy identity assertions and CSRF protection; do not bypass that boundary.
- The Gateway still uses `DisabledProvider`, so DCP cannot provision Azure/Orka runners or dynamically create local VMs.
- A self-hosted GitHub Actions runner is a manually registered GitHub worker, not a DCP-managed ephemeral runner.
- Remote access, multi-user authorization, TLS, durable backup/restore automation, and security review are not supplied by this local-only guide.

Keep the machine private and local until those items have been implemented and independently tested.
