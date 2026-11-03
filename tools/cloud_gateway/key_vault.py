"""Read-only Azure Key Vault secret access using Managed Identity."""
import json,re
from urllib.parse import quote,urlparse
from urllib.request import Request,urlopen
from .azure_identity import ManagedIdentityCredential
class KeyVaultError(RuntimeError): pass
_SECRET=re.compile(r"^[A-Za-z0-9-]{1,127}$")
class KeyVaultSecretReader:
 def __init__(self,vault_url,credential=None,timeout=5):
  parsed=urlparse(vault_url)
  if parsed.scheme!="https" or not parsed.hostname or not parsed.hostname.endswith(".vault.azure.net") or parsed.path not in ("","/") or parsed.query or parsed.fragment or parsed.username or parsed.password: raise ValueError("Key Vault URL must be an HTTPS Azure vault origin")
  self.base=vault_url.rstrip("/"); self.credential=credential or ManagedIdentityCredential(); self.timeout=timeout
 def get_secret(self,name,version=""):
  if not isinstance(name,str) or not _SECRET.fullmatch(name): raise ValueError("Invalid Key Vault secret name")
  if version and (not isinstance(version,str) or not re.fullmatch(r"[A-Za-z0-9-]{1,128}",version)): raise ValueError("Invalid Key Vault secret version")
  suffix="/secrets/"+quote(name,safe="")
  if version: suffix+="/"+quote(version,safe="")
  try:
   token=self.credential.get_token("https://vault.azure.net")
   req=Request(self.base+suffix+"?api-version=7.4",headers={"Authorization":"Bearer "+token,"Accept":"application/json"})
   with urlopen(req,timeout=self.timeout) as response: data=json.loads(response.read(65537).decode("utf-8"))
  except Exception as exc: raise KeyVaultError("Key Vault read failed: "+type(exc).__name__) from exc
  value=data.get("value") if isinstance(data,dict) else None
  if not isinstance(value,str) or not value: raise KeyVaultError("Key Vault response did not contain a secret value")
  return value
