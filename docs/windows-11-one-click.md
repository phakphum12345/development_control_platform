# Windows 11 one-click local startup

This is the simplest way to run the current DCP local development stack on your own Windows 11 PC. It uses local CPU, memory, and disk only. It does not require Azure, Orka, Docker, a paid cloud account, or a public IP address.

## Requirements

- Windows 11 x64
- Python 3.10+ and the Python Launcher (\`py.exe\`)
- Git is optional for running the application

The scripts do not install software or packages. They create only \`%LOCALAPPDATA%\DCP\` and its log directory. The Gateway currently uses Python's standard library and SQLite.

## First run

1. Download or clone this repository to a folder you control.
2. Double-click \`Setup-DCP-Local.cmd\`. This runs the read-only environment doctor. It does not start services or contact cloud providers.
3. Double-click \`Start-DCP-Local.cmd\`.
4. A separate PowerShell window starts the Gateway. Keep that window open. The Dashboard opens in your browser.

The startup launcher checks \`http://127.0.0.1:8789/healthz\` and refuses to proceed unless the Gateway reports healthy with cloud provisioning disabled. The Dashboard binds only to \`127.0.0.1\` and chooses an available port. If the Gateway port is occupied, the launcher stops and leaves the existing process untouched.

## Stop

Press \`Ctrl+C\` in the PowerShell window running the Gateway. To stop the Dashboard, close its browser tab and use the Dashboard's existing ownership-aware stop procedure or restart Windows; do not kill an unverified process by port number.

## Data and security

- SQLite data: \`%LOCALAPPDATA%\DCP\gateway.sqlite3\`
- Gateway address: \`127.0.0.1:8789\`
- Dashboard address: \`127.0.0.1:<automatically-selected-port>\`
- \`DCP_GATEWAY_PROVISIONING_ENABLED=false\`
- \`DCP_GATEWAY_OWNER_APPROVED=false\`
- The Gateway API token is generated in the Gateway process memory and is not printed or written to disk.
- No inbound firewall rule, router port-forward, public listener, cloud API, or cloud resource is configured.

Keep the Gateway PowerShell window private. Do not change the Gateway host to \`0.0.0.0\` or expose it to the LAN/internet.

## Capability boundary

This launcher starts the existing local Dashboard and fail-closed Gateway. The Gateway still composes \`DisabledProvider\`; it does not create local VMs, containers, or ephemeral DCP-managed runners. The optional manually registered GitHub Actions self-hosted runner is a separate GitHub feature. Browser-to-Gateway OIDC/session integration and production-grade multi-user access are not implemented by this launcher.

For details and limitations, see [Windows 11 self-hosted deployment](windows-11-self-hosted.md).
