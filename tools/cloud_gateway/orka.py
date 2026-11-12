"""MacStadium Orka adapter. Runner-online evidence is checked separately from VM state."""
from __future__ import annotations
import base64,json,re,uuid
from datetime import datetime,timedelta,timezone
from urllib.error import HTTPError,URLError
from urllib.parse import quote,urlparse
from urllib.request import Request,urlopen
from tools.runner_backend.provider import RunnerInstance

class OrkaError(RuntimeError): pass
class OrkaProvider:
 budget_provider="orka"
 requires_runner_cleanup=True
 requires_budget_guard=True
 def __init__(self,base_url,namespace,vm_config,secret_reader,secret_name="orka-api-token",runner_online_checker=None,timeout=20,bootstrap_factory=None,userdata_rbac_reviewed=False,userdata_exposure_reviewed=False,network_policy_checker=None,cluster_readiness_checker=None,budget_readiness_checker=None):
  parsed=urlparse(base_url)
  if parsed.scheme!="https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.path not in ("","/") or parsed.query or parsed.fragment: raise ValueError("Orka endpoint must be an HTTPS origin")
  if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?",namespace): raise ValueError("Invalid Orka namespace")
  if not re.fullmatch(r"[A-Za-z0-9_.-]{1,63}",vm_config): raise ValueError("Invalid approved Orka VM config")
  if not re.fullmatch(r"[A-Za-z0-9-]{1,127}",secret_name): raise ValueError("Invalid Key Vault secret name")
  self.base=base_url.rstrip("/"); self.namespace=namespace; self.vm_config=vm_config
  self.secret_reader=secret_reader; self.secret_name=secret_name; self.online=runner_online_checker; self.timeout=timeout
  self.bootstrap_factory=bootstrap_factory; self.userdata_rbac_reviewed=userdata_rbac_reviewed is True
  self.userdata_exposure_reviewed=userdata_exposure_reviewed is True
  self.network_policy_checker=network_policy_checker
  self.cluster_readiness_checker=cluster_readiness_checker
  self.budget_readiness_checker=budget_readiness_checker
 def _request(self,method,path,payload=None,allow_missing=False):
  token=self.secret_reader.get_secret(self.secret_name)
  body=None if payload is None else json.dumps(payload,separators=(",",":")).encode()
  req=Request(self.base+path,data=body,method=method,headers={"Accept":"application/json","Content-Type":"application/json","User-Agent":"DCP-Orka-Adapter/1.0"})
  req.add_unredirected_header("Authorization","Bearer "+token)
  try:
   with urlopen(req,timeout=self.timeout) as response: raw=response.read(65537)
  except HTTPError as exc:
   try:
    if allow_missing and exc.code==404: return None
    raise OrkaError("Orka API request failed with HTTP "+str(exc.code)) from exc
   finally:
    exc.close()
  except (URLError,TimeoutError) as exc: raise OrkaError("Orka API request failed: "+type(exc).__name__) from exc
  if len(raw)>65536: raise OrkaError("Orka response exceeded size limit")
  if not raw: return {}
  try: data=json.loads(raw.decode("utf-8"))
  except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise OrkaError("Orka returned malformed JSON") from exc
  if not isinstance(data,dict): raise OrkaError("Orka returned an invalid response shape")
  return data
 def readiness(self,os_name):
  if os_name!="macos": return {"ready":False,"message":"Orka supports only the approved macOS profile"}
  if not callable(self.online): return {"ready":False,"message":"Independent GitHub runner-online verification is not configured"}
  if not callable(self.bootstrap_factory): return {"ready":False,"message":"Protected Orka User Data bootstrap is not configured"}
  if not self.userdata_rbac_reviewed: return {"ready":False,"message":"Orka namespace User Data RBAC review is not approved"}
  if not self.userdata_exposure_reviewed: return {"ready":False,"message":"Orka User Data request and log exposure review is not approved"}
  checks=(
   ("network_policy_checker","Orka runner network egress policy is not verified"),
   ("cluster_readiness_checker","Orka 4.0 Apple-silicon cluster, VM Tools and finite User Data timeout are not verified"),
   ("budget_readiness_checker","Authoritative Orka provider-specific budget is not verified"),
  )
  for name,message in checks:
   checker=getattr(self,name)
   if not callable(checker): return {"ready":False,"message":message}
   try: accepted=checker(self.namespace,self.vm_config) is True
   except Exception: accepted=False
   if not accepted: return {"ready":False,"message":message}
  return {"ready":True,"message":"Orka macOS provider, User Data, egress, cluster and budget checks passed"}
 def provision(self,payload):
  if payload.get("target_os")!="macos" or payload.get("image")!="macos-15-arm64": raise OrkaError("Orka adapter accepts only the approved macOS 15 ARM64 profile")
  if payload.get("ephemeral") is not True or payload.get("network_policy")!="restricted-egress": raise OrkaError("Orka request violates ephemeral network policy")
  gate=self.readiness("macos")
  if gate.get("ready") is not True: raise OrkaError("Orka provider is not ready: "+str(gate.get("message","readiness check failed")))
  name="dcp-"+str(payload["workflow_run_id"])+"-"+uuid.uuid4().hex[:8]
  bootstrap=self.bootstrap_factory(name,"macos",payload)
  script=bootstrap.get("script") if isinstance(bootstrap,dict) else None
  expires_at=bootstrap.get("expires_at") if isinstance(bootstrap,dict) else None
  if (
   not isinstance(script,str) or not script or "\\x00" in script
   or not isinstance(expires_at,datetime) or expires_at.tzinfo is None
   or expires_at<=datetime.now(timezone.utc)+timedelta(minutes=1)
  ): raise OrkaError("Orka User Data bootstrap script or short-lived credential expiry is invalid")
  userdata=base64.b64encode(script.encode("utf-8")).decode("ascii")
  if len(userdata)>65536: raise OrkaError("Orka User Data script exceeds the 64 KiB encoded limit")
  metadata={"managed-by":"dcp-cloud-runner","repository":payload["repository"],"workflow-run-id":str(payload["workflow_run_id"]),"commit-sha":payload["commit_sha"],"target-os":"macos"}
  body={"name":name,"vmConfig":self.vm_config,"shouldGenerateName":False,"customMetadata":metadata,"userdata":userdata}
  path="/api/v1/namespaces/"+quote(self.namespace,safe="")+"/vms/"+quote(name,safe="")
  collection="/api/v1/namespaces/"+quote(self.namespace,safe="")+"/vms"
  try:
   data=self._request("POST",collection,body)
  except Exception as original:
   if self._rollback_partial_vm(path):
    error=OrkaError("Orka provisioning failed; VM cleanup is pending")
    error.provider_id=name
    raise error from original
   raise
  vm_name=data.get("name")
  if not isinstance(vm_name,str) or vm_name!=name:
   if self._rollback_partial_vm(path):
    error=OrkaError("Orka did not confirm VM identity; cleanup is pending")
    error.provider_id=name
    raise error
   raise OrkaError("Orka did not confirm the requested VM identity")
  # A running VM is not proof that the GitHub runner has registered.
  return RunnerInstance(vm_name,"provisioning",vm_name,tuple(payload["labels"]),"VM accepted; runner registration pending")
 def _rollback_partial_vm(self,path):
  try:
   existing=self._request("GET",path,allow_missing=True)
   if existing is None: return False
   self._request("DELETE",path,allow_missing=True)
   return self._request("GET",path,allow_missing=True) is not None
  except Exception:
   return True
 def status(self,provider_id):
  if not isinstance(provider_id,str) or not re.fullmatch(r"dcp-[0-9]+-[a-f0-9]{8}",provider_id): raise OrkaError("Invalid DCP Orka VM identifier")
  path="/api/v1/namespaces/"+quote(self.namespace,safe="")+"/vms/"+quote(provider_id,safe="")
  data=self._request("GET",path,allow_missing=True)
  if data is None: return RunnerInstance(provider_id,"terminated")
  vm_status=str(data.get("status","")).lower()
  userdata_phase=str(data.get("userdataPhase","")).lower()
  if vm_status in ("failed","error","crashed") or userdata_phase in ("failed","timeout"):
   self._request("DELETE",path,allow_missing=True)
   state="terminating"
  elif vm_status in ("deleting","terminating"): state="terminating"
  elif vm_status in ("running","ready") and userdata_phase in ("success","skipped") and self.online:
   metadata=data.get("customMetadata",{})
   repository=metadata.get("repository") if isinstance(metadata,dict) else None
   try: online=self.online(provider_id,repository,"macos") is True
   except Exception: online=False
   if userdata_phase=="skipped" and not online:
    self._request("DELETE",path,allow_missing=True)
    state="terminating"
   else: state="online" if online else "provisioning"
  else: state="provisioning"
  return RunnerInstance(provider_id,state,provider_id)
 def terminate(self,provider_id):
  if not isinstance(provider_id,str) or not re.fullmatch(r"dcp-[0-9]+-[a-f0-9]{8}",provider_id): raise OrkaError("Invalid DCP Orka VM identifier")
  path="/api/v1/namespaces/"+quote(self.namespace,safe="")+"/vms/"+quote(provider_id,safe="")
  result=self._request("DELETE",path,allow_missing=True)
  if result is None: return RunnerInstance(provider_id,"terminated")
  # DELETE acceptance is not proof that the VM has disappeared; status() confirms 404.
  return RunnerInstance(provider_id,"terminating")
