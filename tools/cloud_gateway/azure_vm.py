"""Azure VM provisioner using pre-existing network controls and ephemeral OS disks."""
from __future__ import annotations
import json,re,uuid
from urllib.error import HTTPError,URLError
from urllib.parse import quote
from urllib.request import Request,urlopen
from tools.runner_backend.provider import RunnerInstance
class AzureProvisionError(RuntimeError): pass
API_COMPUTE="2024-03-01"; API_NETWORK="2023-09-01"
class AzureArmClient:
 def __init__(self,subscription_id,resource_group,credential,timeout=30):
  if not re.fullmatch(r"[0-9a-fA-F-]{36}",subscription_id): raise ValueError("Invalid Azure subscription ID")
  if not re.fullmatch(r"[A-Za-z0-9_.()-]{1,90}",resource_group): raise ValueError("Invalid Azure resource group")
  self.subscription_id=subscription_id; self.resource_group=resource_group; self.credential=credential; self.timeout=timeout
 def resource_url(self,provider,resource_type,name,api_version):
  return "https://management.azure.com/subscriptions/"+self.subscription_id+"/resourceGroups/"+quote(self.resource_group,safe="")+"/providers/"+provider+"/"+resource_type+"/"+quote(name,safe="")+"?api-version="+api_version
 def resource_id(self,provider,resource_type,name):
  return "/subscriptions/"+self.subscription_id+"/resourceGroups/"+self.resource_group+"/providers/"+provider+"/"+resource_type+"/"+name
 def request(self,method,url,payload=None,allow_missing=False):
  token=self.credential.get_token("https://management.azure.com/")
  body=None if payload is None else json.dumps(payload,separators=(",",":")).encode()
  req=Request(url,data=body,method=method,headers={"Accept":"application/json","Content-Type":"application/json","User-Agent":"DCP-Azure-VM-Provisioner/1.0"})
  req.add_unredirected_header("Authorization","Bearer "+token)
  try:
   with urlopen(req,timeout=self.timeout) as response: raw=response.read(65537)
  except HTTPError as exc:
   if allow_missing and exc.code==404: return None
   raise AzureProvisionError("Azure Resource Manager returned HTTP "+str(exc.code)) from exc
  except (URLError,TimeoutError) as exc: raise AzureProvisionError("Azure Resource Manager request failed: "+type(exc).__name__) from exc
  if len(raw)>65536: raise AzureProvisionError("Azure response exceeded size limit")
  if not raw: return {}
  try: data=json.loads(raw.decode("utf-8"))
  except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise AzureProvisionError("Azure returned malformed JSON") from exc
  if not isinstance(data,dict): raise AzureProvisionError("Azure returned an invalid response shape")
  return data
class AzureVMProvider:
 budget_provider="azure"
 requires_runner_cleanup=True
 requires_budget_guard=True
 def __init__(self,arm,location,subnet_id,nsg_id,vm_sizes,image_references,bootstrap_factory,runner_online_checker=None,network_policy_checker=None):
  self.arm=arm; self.location=location; self.subnet_id=subnet_id; self.nsg_id=nsg_id
  self.vm_sizes=dict(vm_sizes); self.image_references={k:dict(v) for k,v in image_references.items()}
  self.bootstrap_factory=bootstrap_factory; self.online=runner_online_checker; self.network_policy=network_policy_checker
  sub=arm.subscription_id; scope=r"^/subscriptions/"+re.escape(sub)+r"/resourceGroups/[A-Za-z0-9_.()-]+/providers/Microsoft\.Network/"
  if not re.match(scope,subnet_id,re.I) or "/virtualNetworks/" not in subnet_id or "/subnets/" not in subnet_id: raise ValueError("Subnet must be a resource ID in the configured subscription")
  if not re.match(scope,nsg_id,re.I) or "/networkSecurityGroups/" not in nsg_id: raise ValueError("NSG must be a resource ID in the configured subscription")
  if not location or not re.fullmatch(r"[a-z0-9]+",location): raise ValueError("Invalid Azure location")
  if not callable(bootstrap_factory): raise ValueError("A protected bootstrap factory is required")
  if set(self.vm_sizes)!={"linux","windows"} or any(not isinstance(v,str) or not re.fullmatch(r"[A-Za-z0-9_]+",v) for v in self.vm_sizes.values()): raise ValueError("Explicit Linux and Windows VM sizes are required")
  if set(self.image_references)!={"linux","windows"}: raise ValueError("Exact image references for Linux and Windows are required")
  for ref in self.image_references.values():
   if set(ref)!={"publisher","offer","sku","version"} or any(not isinstance(v,str) or not v or v.lower()=="latest" for v in ref.values()): raise ValueError("Marketplace image must be explicitly version-pinned; latest is forbidden")
 def readiness(self,os_name):
  if os_name not in ("linux","windows"):
   return {"ready":False,"message":"Azure supports only approved Linux or Windows runner profiles"}
  if not callable(self.bootstrap_factory):
   return {"ready":False,"message":"Protected GitHub runner bootstrap is not configured"}
  if not callable(self.online):
   return {"ready":False,"message":"Independent GitHub runner-online verification is not configured"}
  if not callable(self.network_policy):
   return {"ready":False,"message":"Subnet and NSG egress policy verification is not configured"}
  try:
   verified=self.network_policy(os_name,self.subnet_id,self.nsg_id)
  except Exception:
   verified=False
  if verified is not True:
   detail=getattr(self.network_policy,"last_error",None)
   message="Runner network egress policy has not been verified"
   if isinstance(detail,str) and detail:
    message += ": "+detail[:240]
   return {"ready":False,"message":message}
  return {"ready":True,"message":"Protected bootstrap, runner-online check, and network policy are configured"}
 def _url(self,provider,kind,name,version=API_COMPUTE): return self.arm.resource_url(provider,kind,name,version)
 def _names(self,run_id):
  suffix=uuid.uuid4().hex[:8]; return "dcp-"+str(run_id)+"-"+suffix,"dcpnic"+suffix
 def provision(self,payload):
  os_name=payload.get("target_os"); expected={"linux":"ubuntu-24.04-x64","windows":"windows-2025-x64"}
  if os_name not in expected or payload.get("image")!=expected[os_name]: raise AzureProvisionError("Azure adapter accepts only approved Linux or Windows profiles")
  if payload.get("ephemeral") is not True or payload.get("network_policy")!="restricted-egress": raise AzureProvisionError("Runner must be ephemeral with restricted egress")
  gate=self.readiness(os_name)
  if gate.get("ready") is not True: raise AzureProvisionError("Azure runner provider is not ready: "+str(gate.get("message","readiness check failed")))
  vm_name,nic_name=self._names(payload["workflow_run_id"]); bootstrap=self.bootstrap_factory(vm_name,os_name,payload)
  if not isinstance(bootstrap,dict) or not isinstance(bootstrap.get("os_profile"),dict) or not isinstance(bootstrap.get("extension"),dict): raise AzureProvisionError("Protected bootstrap factory returned an invalid contract")
  extension_name=bootstrap["extension"].get("name")
  props=bootstrap["extension"].get("properties",{})
  if not isinstance(extension_name,str) or not re.fullmatch(r"dcp-[a-z0-9-]{1,50}",extension_name):
   raise AzureProvisionError("Runner bootstrap extension name is invalid")
  if not isinstance(props,dict) or not props.get("protectedSettings"): raise AzureProvisionError("Runner bootstrap must use protected extension settings")
  if props.get("settings") not in (None,{}): raise AzureProvisionError("Public extension settings must be empty; bootstrap data belongs in protectedSettings")
  tags={"managed-by":"dcp-cloud-runner","runner-id":vm_name,"repository":payload["repository"],"workflow-run-id":str(payload["workflow_run_id"]),"commit-sha":payload["commit_sha"],"target-os":os_name,"ephemeral":"true","bootstrap-extension":extension_name}
  nic_url=self._url("Microsoft.Network","networkInterfaces",nic_name,API_NETWORK)
  nic_id=self.arm.resource_id("Microsoft.Network","networkInterfaces",nic_name)
  nic_body={"location":self.location,"tags":tags,"properties":{"networkSecurityGroup":{"id":self.nsg_id},"ipConfigurations":[{"name":"primary","properties":{"primary":True,"privateIPAllocationMethod":"Dynamic","subnet":{"id":self.subnet_id}}}]}}
  extension=dict(bootstrap["extension"])
  extension["location"]=self.location
  extension["type"]="Microsoft.Compute/virtualMachines/extensions"
  vm_body={"location":self.location,"tags":tags,"properties":{
   "hardwareProfile":{"vmSize":self.vm_sizes[os_name]},
   "storageProfile":{"imageReference":self.image_references[os_name],"osDisk":{"name":vm_name+"-os","createOption":"FromImage","caching":"ReadOnly","managedDisk":{"storageAccountType":"Standard_LRS"},"diffDiskSettings":{"option":"Local"}}},
   "osProfile":bootstrap["os_profile"],"networkProfile":{"networkInterfaces":[{"id":nic_id,"properties":{"primary":True}}]},
   "securityProfile":{"uefiSettings":{"secureBootEnabled":True,"vTpmEnabled":True},"securityType":"TrustedLaunch"},
   "extensionsTimeBudget":"PT45M"
  },"resources":[extension]}
  vm_url=self._url("Microsoft.Compute","virtualMachines",vm_name)
  vm_create_started=False
  try:
   self.arm.request("PUT",nic_url,nic_body)
   vm_create_started=True
   self.arm.request("PUT",vm_url,vm_body)
  except Exception as original:
   cleanup_pending=False
   if vm_create_started:
    try:
     self.arm.request("DELETE",vm_url,allow_missing=True)
     if self.arm.request("GET",vm_url,allow_missing=True) is not None: cleanup_pending=True
    except Exception:
     cleanup_pending=True
   try:
    self.arm.request("DELETE",nic_url,allow_missing=True)
    if self.arm.request("GET",nic_url,allow_missing=True) is not None: cleanup_pending=True
   except Exception:
    cleanup_pending=True
   if cleanup_pending:
    error=AzureProvisionError("Azure provisioning failed; resource cleanup is pending")
    error.provider_id=vm_name
    raise error from original
   raise
  return RunnerInstance(vm_name,"provisioning",vm_name,tuple(payload.get("labels",[])),"Azure VM create accepted; runner registration pending")
 def status(self,provider_id):
  if not isinstance(provider_id,str) or not re.fullmatch(r"dcp-[0-9]+-[a-f0-9]{8}",provider_id): raise AzureProvisionError("Invalid DCP Azure VM identifier")
  data=self.arm.request("GET",self._url("Microsoft.Compute","virtualMachines",provider_id)+"&$expand=instanceView",allow_missing=True)
  if data is None:
   nic="dcpnic"+provider_id.rsplit("-",1)[1]
   nic_url=self._url("Microsoft.Network","networkInterfaces",nic,API_NETWORK)
   nic_data=self.arm.request("GET",nic_url,allow_missing=True)
   if nic_data is None:
    return RunnerInstance(provider_id,"terminated",provider_id)
   self.arm.request("DELETE",nic_url,allow_missing=True)
   remaining=self.arm.request("GET",nic_url,allow_missing=True)
   if remaining is None:
    return RunnerInstance(provider_id,"terminated",provider_id)
   return RunnerInstance(provider_id,"terminating",provider_id,detail="NIC cleanup pending")

  state=str(data.get("properties",{}).get("provisioningState","")).lower()
  if state=="failed":
   self.arm.request("DELETE",self._url("Microsoft.Compute","virtualMachines",provider_id),allow_missing=True)
   return RunnerInstance(provider_id,"terminating",provider_id,detail="failed VM cleanup requested")
  tags=data.get("tags",{})
  extension_name=tags.get("bootstrap-extension") if isinstance(tags,dict) else None
  resources=data.get("resources",[])
  extension_matches=[
   item for item in resources
   if isinstance(item,dict) and item.get("name")==extension_name
  ] if isinstance(resources,list) and extension_name else []
  if len(extension_matches)!=1:
   return RunnerInstance(provider_id,"provisioning",provider_id,detail="runner bootstrap extension status is not available")
  extension_properties=extension_matches[0].get("properties",{})
  if not isinstance(extension_properties,dict):
   return RunnerInstance(provider_id,"provisioning",provider_id,detail="runner bootstrap extension status is malformed")
  extension_state=str(extension_properties.get("provisioningState","")).lower()
  if extension_state in ("failed","canceled"):
   self.arm.request("DELETE",self._url("Microsoft.Compute","virtualMachines",provider_id),allow_missing=True)
   return RunnerInstance(provider_id,"terminating",provider_id,detail="runner bootstrap extension failed; VM cleanup requested")
  if extension_state!="succeeded":
   return RunnerInstance(provider_id,"provisioning",provider_id,detail="runner bootstrap extension is not complete")
  repository=tags.get("repository") if isinstance(tags,dict) else None
  target_os=tags.get("target-os") if isinstance(tags,dict) else None
  try: online=callable(self.online) and self.online(provider_id,repository,target_os) is True
  except Exception: online=False
  result="online" if online else "provisioning"
  return RunnerInstance(provider_id,result,provider_id)
 def terminate(self,provider_id):
  if not isinstance(provider_id,str) or not re.fullmatch(r"dcp-[0-9]+-[a-f0-9]{8}",provider_id): raise AzureProvisionError("Invalid DCP Azure VM identifier")
  self.arm.request("DELETE",self._url("Microsoft.Compute","virtualMachines",provider_id),allow_missing=True)
  return RunnerInstance(provider_id,"terminating")
