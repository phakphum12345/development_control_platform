# Live Gateway acceptance checks

## Automated PR/CI coverage

The ordinary test suite validates the live-smoke probe using mocked HTTP responses.
It proves that the probe:
- accepts only an HTTPS Gateway origin without embedded credentials, query, fragment, or path;
- sends only GET requests;
- checks `GET /healthz` and requires `provisioning_enabled=false`;
- checks bearer authentication by requesting a random, nonexistent runner ID and requiring HTTP 404;
- refuses to continue when provisioning is enabled; and
- never prints the Gateway URL or API bearer token.

These contract tests do not contact a deployed Gateway, GitHub, Azure, or Orka.

## Optional live read-only run

The manual GitHub Actions workflow `Cloud Gateway Live Read-only Smoke` is disabled by default. To run it, an authorized maintainer must explicitly enable the `enable_live_readonly_smoke` input and configure repository Actions secrets:

- `DCP_LIVE_GATEWAY_URL`: the deployed Gateway HTTPS origin.
- `DCP_LIVE_GATEWAY_API_TOKEN`: a Gateway bearer token with read-only access where possible.

The live job performs only the two GET requests described above. The random runner ID is expected not to exist, so the authenticated lookup returns 404 without invoking a provider adapter. The job refuses to run its second request if `/healthz` reports provisioning enabled. Redirects are rejected so the bearer token is not forwarded to another host.

## Explicitly not covered

This workflow is a live Gateway HTTP/authentication smoke test, **not** a live Azure or Orka provisioning acceptance test. Azure Managed Identity, Key Vault, ARM budget reads, Azure VM creation, Orka billing, Orka User Data bootstrap, GitHub App runner registration, online verification, and teardown are not exercised. They remain `SKIPPED` until a dedicated, owner-approved provider environment, isolated test subscription/cluster, provider-specific budget source, and cleanup verification are available.

No PR or push workflow provisions cloud resources. Do not set provisioning enabled merely to make this read-only smoke test pass.
