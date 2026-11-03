"""Mock-only tests for Managed Identity, Key Vault, and Azure budget reads."""
import json,unittest
from unittest.mock import patch,MagicMock
from tools.cloud_gateway.azure_identity import ManagedIdentityCredential,IdentityError
from tools.cloud_gateway.key_vault import KeyVaultSecretReader
from tools.cloud_gateway.azure_budget import AzureBudgetReader,BudgetSnapshot,BudgetReadError
class CredentialTests(unittest.TestCase):
 def test_no_secret_fallback_when_identity_missing(self):
  with self.assertRaises(IdentityError): ManagedIdentityCredential(env={}).get_token("https://vault.azure.net")
 def test_identity_endpoint_uses_local_header_and_resource(self):
  env={"IDENTITY_ENDPOINT":"http://localhost:42356/msi/token","IDENTITY_HEADER":"header-value"}
  response=MagicMock(); response.__enter__.return_value=response; response.read.return_value=json.dumps({"access_token":"opaque-token"}).encode()
  with patch("tools.cloud_gateway.azure_identity.urlopen",return_value=response) as call:
   self.assertEqual(ManagedIdentityCredential(env).get_token("https://vault.azure.net"),"opaque-token")
  req=call.call_args.args[0]; self.assertEqual(req.get_header("X-identity-header"),"header-value"); self.assertIn("resource=https%3A%2F%2Fvault.azure.net",req.full_url)
 def test_untrusted_identity_endpoint_rejected(self):
  env={"IDENTITY_ENDPOINT":"https://attacker.example/token","IDENTITY_HEADER":"x"}
  with self.assertRaises(IdentityError): ManagedIdentityCredential(env).get_token("resource")
class KeyVaultTests(unittest.TestCase):
 def test_rejects_non_azure_vault_origin(self):
  with self.assertRaises(ValueError): KeyVaultSecretReader("https://example.com")
 def test_secret_read_uses_managed_identity_and_never_logs_value(self):
  credential=MagicMock(); credential.get_token.return_value="access"
  response=MagicMock(); response.__enter__.return_value=response; response.read.return_value=b'{"value":"secret-value"}'
  with patch("tools.cloud_gateway.key_vault.urlopen",return_value=response) as call:
   value=KeyVaultSecretReader("https://demo.vault.azure.net",credential).get_secret("orka-token")
  self.assertEqual(value,"secret-value"); self.assertIn("/secrets/orka-token?api-version=7.4",call.call_args.args[0].full_url)
 def test_invalid_secret_name_rejected(self):
  reader=KeyVaultSecretReader("https://demo.vault.azure.net",MagicMock())
  with self.assertRaises(ValueError): reader.get_secret("../leak")
class BudgetTests(unittest.TestCase):
 def test_budget_permit_checks_current_forecast_and_currency(self):
  self.assertTrue(BudgetSnapshot(100,20,70,"USD").permits(10))
  self.assertFalse(BudgetSnapshot(100,95,None,"USD").permits(10))
  self.assertFalse(BudgetSnapshot(100,20,95,"USD").permits(10))
  self.assertFalse(BudgetSnapshot(100,20,None,"THB").permits(1))
 def test_budget_reader_is_read_only_and_parses_budget(self):
  credential=MagicMock(); credential.get_token.return_value="arm-token"
  response=MagicMock(); response.__enter__.return_value=response
  response.read.return_value=json.dumps({"properties":{"amount":50,"currentSpend":{"amount":12,"unit":"USD"},"forecastSpend":{"amount":35,"unit":"USD"}}}).encode()
  with patch("tools.cloud_gateway.azure_budget.urlopen",return_value=response) as call:
   snapshot=AzureBudgetReader("00000000-0000-0000-0000-000000000000","dcp-monthly",credential).read()
  self.assertEqual(snapshot.current_spend,12); self.assertTrue(snapshot.permits(3))
  self.assertEqual(call.call_args.args[0].get_method(),"GET")
 def test_invalid_budget_data_fails_closed(self):
  credential=MagicMock(); credential.get_token.return_value="token"
  response=MagicMock(); response.__enter__.return_value=response; response.read.return_value=b'{}'
  with patch("tools.cloud_gateway.azure_budget.urlopen",return_value=response):
   with self.assertRaises(BudgetReadError): AzureBudgetReader("00000000-0000-0000-0000-000000000000","dcp-budget",credential).read()
if __name__=="__main__": unittest.main()
