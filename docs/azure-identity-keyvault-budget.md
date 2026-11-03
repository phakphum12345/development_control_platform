# Azure identity, Key Vault, and budget reader

This adapter set is read-only. It obtains Microsoft Entra access tokens through a platform-provided Managed Identity endpoint, reads named Key Vault secrets, and reads an existing Azure Consumption budget. It does not create a vault, role assignment, budget, subscription, resource group, or compute resource.

## Required deployment configuration
- Configure a system- or user-assigned Managed Identity on the gateway host.
- Grant only Key Vault Secrets User on the specific vault and read-only Cost Management/Budget permissions at the narrowest applicable scope.
- Configure DCP_AZURE_USE_IMDS=true only on an Azure VM that exposes IMDS, or use the platform-provided local IDENTITY_ENDPOINT and IDENTITY_HEADER.
- Set the Key Vault origin and secret names through deployment configuration. Never put secret values in GitHub Actions variables, source files, command lines, or logs.
- Provide subscription ID and an already-existing budget name. This code intentionally contains no create/update/delete budget operation.

## Budget semantics
A budget read must return amount, currentSpend, and currency. Forecast spend is included when present. Missing or malformed budget data fails closed. The adapter only compares USD amounts; other currencies are denied until a reviewed conversion policy exists. Azure budgets are monitoring/alerting constructs, so the gateway's independent spend circuit breaker remains mandatory.

## Verification boundary
Tests use mocked HTTP responses only. No Azure endpoint was contacted, no identity token was requested from a live host, and no billable Azure resource was created. Required role assignments and live authorization are deployment-time checks and remain unverified here.
