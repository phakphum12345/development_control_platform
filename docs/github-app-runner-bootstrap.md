# GitHub App runner bootstrap

## Scope

`tools.cloud_gateway.github_app.GitHubAppRunnerBootstrap` is a server-side
credential broker for issuing a repository-scoped GitHub Actions runner
registration token. It does not create a VM, install a runner, or enable
provisioning by itself.

The implementation is deliberately fail-closed:
- The GitHub App ID and installation ID are validated at startup.
- In GitHub App mode, repositories must be present in the DCP App installation catalog. A legacy explicit allowlist remains available only when App catalog authorization is not configured.
- The installation access token request is scoped to that one repository.
- The installation must grant repository Administration write permission required by the registration-token endpoint.
- The registration token is returned only to the provider-side caller.
- Token fields are excluded from object representations; API errors are sanitized.
- The App private key is accepted in memory and must be read from a server-side
  secret store such as Azure Key Vault. Never commit it or pass it to browser code.

## Required GitHub App configuration

Create/configure the GitHub App outside this repository and install it only on
all intended repositories (choose **All repositories** if every repository should appear in DCP). Grant the minimum permission needed to
create self-hosted runner registration tokens (Actions write / repository
administration permission as required by GitHub's current App permission model).
Do not grant organization-wide installation access unless separately reviewed.

Server-side settings are expected to be supplied by the deployment environment:
- `DCP_GITHUB_APP_ID`
- `DCP_GITHUB_APP_INSTALLATION_ID`
- `DCP_GITHUB_APP_PRIVATE_KEY_SECRET_NAME` (a Key Vault secret name, not key content)
- `DCP_GATEWAY_ALLOWED_REPOSITORIES` (legacy static fallback; ignored as a narrowing filter when GitHub App installation discovery is active)

The App private key must be retrieved server-side through the existing read-only
Key Vault secret reader. Never put private key material, installation tokens,
or runner registration tokens in dashboard responses, browser storage, query
strings, audit events, workflow logs, or Git history.

## Token flow

1. Discover the installation repository catalog using a short-lived server-side installation token and validate the requested repository against that catalog.
2. Sign a short-lived RS256 App JWT (issued-at skew, expiry under ten minutes).
3. Exchange it for an installation access token scoped to one repository.
4. Require repository Administration write permission in the returned installation permissions.
5. Create that repository's Actions runner registration token.
6. Return a redacted credential object to the provider-side bootstrap caller.

The registration token is a short-lived bootstrap credential, not a durable
runner secret. The caller must pass it only through a protected provider
bootstrap channel (for Azure, protected extension settings; for Orka, a
protected secret injection mechanism) and ensure the guest does not persist it.
The runner must be configured as ephemeral and removed after its one job.

## Validation and current limits

Unit tests use generated test RSA keys and mocked responses. They do not contact
GitHub, Key Vault, Azure Resource Manager, Orka, or create any cloud resources.
A passing unit test proves the local contract only; it is not evidence that a
GitHub App exists, is installed, or has the required permissions.

This PR does not read production secrets, configure an App, activate a provider,
enable provisioning, or deploy an OIDC ingress. Provider integration and
independent GitHub runner-online verification remain subsequent phases.
