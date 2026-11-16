"""Mock-only Azure VM provisioner tests. No ARM resources are created."""
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from tools.cloud_gateway.azure_vm import AzureArmClient, AzureVMProvider, AzureProvisionError
from tools.runner_backend.manager import PLATFORM_PROFILES
SUB="00000000-0000-0000-0000-000000000000"
IMAGES={"linux":{"publisher":"Canonical","offer":"ubuntu-24_04-lts","sku":"server","version":"24.04.202501150"},"windows":{"publisher":"MicrosoftWindowsServer","offer":"WindowsServer","sku":"2025-datacenter-g2","version":"20348.1.250101"}}

class FakeCredential:
 def __init__(self,token="arm-test-token"): self.token=token
 def get_token(self,scope): return self.token
class AzureArmClientTests(unittest.TestCase):
 def make_response(self,status=200,body=b'{"ok":true}',headers=None):
  response=MagicMock(); response.__enter__.return_value=response
  response.status=status; response.headers=headers or {"Content-Type":"application/json"}
  response.read.return_value=body
  return response
 def make_client(self,timeout=20,token="arm-test-token"):
  return AzureArmClient(SUB,"dcp-runners",FakeCredential(token),timeout=timeout)
 def test_uses_no_redirect_transport_and_unredirected_bearer(self):
  client=self.make_client()
  response=self.make_response(202,b"",{"Location":"https://management.azure.com/subscriptions/"+SUB+"/operation"})
  with patch("tools.cloud_gateway.azure_vm.urlopen",return_value=response) as opener:
   status,headers,body=client.request_with_metadata("POST","https://management.azure.com/subscriptions/"+SUB+"/resourceGroups/dcp-runners/providers/Microsoft.Network/networkInterfaces/nic?api-version=2025-05-01",{})
  request=opener.call_args.args[0]
  self.assertEqual(status,202)
  self.assertEqual(request.unredirected_hdrs.get("Authorization"),"Bearer arm-test-token")
  self.assertNotIn("Authorization",request.headers)
 def test_rejects_redirects_and_non_json_response_media_type(self):
  client=self.make_client()
  with patch("tools.cloud_gateway.azure_vm.urlopen",side_effect=HTTPError("https://management.azure.com/",302,"redirect",{},None)):
   with self.assertRaises(AzureProvisionError): client.request("GET","https://management.azure.com/subscriptions/"+SUB+"/resourceGroups/dcp-runners/providers/Microsoft.Network/networkInterfaces/nic?api-version=2025-05-01")
  response=self.make_response(200,b'{"ok":true}',{"Content-Type":"text/plain"})
  with patch("tools.cloud_gateway.azure_vm.urlopen",return_value=response):
   with self.assertRaises(AzureProvisionError): client.request("GET","https://management.azure.com/subscriptions/"+SUB+"/resourceGroups/dcp-runners/providers/Microsoft.Network/networkInterfaces/nic?api-version=2025-05-01")
 def test_rejects_invalid_token_timeout_and_untrusted_arm_url(self):
  with self.assertRaises(ValueError): self.make_client(timeout=31)
  with self.assertRaises(AzureProvisionError): self.make_client(token="bad\r\nheader").request("GET","https://management.azure.com/subscriptions/"+SUB+"/resourceGroups/dcp-runners/providers/Microsoft.Network/networkInterfaces/nic?api-version=2025-05-01")
  with self.assertRaises(AzureProvisionError): self.make_client().request("GET","https://attacker.example/subscriptions/"+SUB+"/resourceGroups/dcp-runners/providers/Microsoft.Network/networkInterfaces/nic?api-version=2025-05-01")
 def test_allow_missing_maps_only_http_404_to_none(self):
  client=self.make_client()
  with patch("tools.cloud_gateway.azure_vm.urlopen",side_effect=HTTPError("https://management.azure.com/",404,"not found",{},None)):
   self.assertIsNone(client.request("GET","https://management.azure.com/subscriptions/"+SUB+"/resourceGroups/dcp-runners/providers/Microsoft.Network/networkInterfaces/nic?api-version=2025-05-01",allow_missing=True))

class FakeArm:
 subscription_id=SUB; resource_group="dcp"
 def __init__(self):
  self.calls=[]; self.nic_exists=True; self.fail_vm_put=False
  self.get_result={"properties":{"provisioningState":"Succeeded"},"tags":{"repository":"phakphum12345/generated-A4-pdf","target-os":"linux","bootstrap-extension":"dcp-bootstrap"},"resources":[{"name":"dcp-bootstrap","properties":{"provisioningState":"Succeeded"}}]}
 def resource_url(self,provider,kind,name,version): return f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/dcp/providers/{provider}/{kind}/{name}?api-version={version}"
 def resource_id(self,provider,kind,name): return f"/subscriptions/{SUB}/resourceGroups/dcp/providers/{provider}/{kind}/{name}"
 def request(self,method,url,payload=None,allow_missing=False):
  self.calls.append((method,url,payload))
  if self.fail_vm_put and method=="PUT" and "Microsoft.Compute/virtualMachines/" in url: raise RuntimeError("simulated VM create uncertainty")
  if "Microsoft.Network/networkInterfaces/" in url:
   if method=="GET": return {"properties":{"provisioningState":"Succeeded"}} if self.nic_exists else None
   if method=="DELETE": return {}
  return self.get_result if method=="GET" else {}
def bootstrap(vm,os_name,payload):
 os_profile={"computerName":vm if os_name=="linux" else "DCPW"+vm.rsplit("-",1)[-1].upper(),"adminUsername":"dcpadmin"}
 if os_name=="linux": os_profile["linuxConfiguration"]={"disablePasswordAuthentication":True}
 else: os_profile["adminPassword"]="test-only-password"
 return {"os_profile":os_profile,"extension":{"name":"dcp-bootstrap","properties":{"publisher":"Microsoft.Azure.Extensions","type":"CustomScript","typeHandlerVersion":"2.1","settings":{},"protectedSettings":{"script":"base64-one-time-bootstrap"}}}}
def payload(os_name):
 p=PLATFORM_PROFILES[os_name]; return {"repository":"phakphum12345/generated-A4-pdf","workflow_run_id":123,"commit_sha":"a"*40,"target_os":os_name,"image":p["image"],"labels":list(p["labels"]),"ephemeral":True,"max_runtime_minutes":30,"network_policy":"restricted-egress","registration_token_handling":"provider-side-only"}
class FakeEffectiveNetworkPolicy:
 def __init__(self,result=True): self.result=result; self.calls=[]
 def verify_nic(self,nic_id,nsg_id,subnet_id):
  self.calls.append((nic_id,nsg_id,subnet_id))
  return self.result
class AzureVMTests(unittest.TestCase):
 def make(self,checker=None,network=None,effective=True):
  arm=FakeArm(); verifier=FakeEffectiveNetworkPolicy(effective) if isinstance(effective,bool) else effective
  p=AzureVMProvider(arm,"eastus",f"/subscriptions/{SUB}/resourceGroups/net/providers/Microsoft.Network/virtualNetworks/vnet/subnets/runners",f"/subscriptions/{SUB}/resourceGroups/net/providers/Microsoft.Network/networkSecurityGroups/runner-nsg",{"linux":"Standard_D2s_v5","windows":"Standard_D4s_v5"},IMAGES,bootstrap,checker,network,verifier); return p,arm,verifier
 def test_requires_existing_subnet_nsg_and_both_vm_sizes(self):
  with self.assertRaises(ValueError): AzureVMProvider(FakeArm(),"eastus","bad","bad",{"linux":"D2"},IMAGES,bootstrap)
 def test_rejects_latest_image_version(self):
  with self.assertRaises(ValueError): AzureVMProvider(FakeArm(),"eastus",f"/subscriptions/{SUB}/resourceGroups/net/providers/Microsoft.Network/virtualNetworks/vnet/subnets/runners",f"/subscriptions/{SUB}/resourceGroups/net/providers/Microsoft.Network/networkSecurityGroups/nsg",{"linux":"D2","windows":"D4"},{**IMAGES,"linux":{**IMAGES["linux"],"version":"latest"}},bootstrap)
 def test_provision_uses_ephemeral_disk_private_nic_and_tags(self):
  for os_name in ("linux","windows"):
   p,arm,verifier=self.make(lambda *args:True,lambda *args:True); result=p.provision(payload(os_name)); self.assertEqual(result.state,"provisioning")
   self.assertEqual(len(verifier.calls),1)
   nic=arm.calls[0][2]; vm=arm.calls[1][2]; self.assertNotIn("publicIPAddress",str(nic))
   self.assertEqual(vm["properties"]["storageProfile"]["osDisk"]["diffDiskSettings"]["option"],"Local")
   self.assertEqual(vm["properties"]["extensionsTimeBudget"],"PT45M")
   self.assertEqual(vm["properties"]["networkProfile"]["networkInterfaces"][0]["id"],f"/subscriptions/{SUB}/resourceGroups/dcp/providers/Microsoft.Network/networkInterfaces/{arm.calls[0][1].split('/')[-1].split('?')[0]}")
   self.assertNotIn("identity",vm); self.assertEqual(vm["tags"]["managed-by"],"dcp-cloud-runner")
   self.assertIn("protectedSettings",vm["resources"][0]["properties"])
   self.assertEqual(vm["resources"][0]["location"],"eastus")
   self.assertEqual(vm["resources"][0]["type"],"Microsoft.Compute/virtualMachines/extensions")
 def test_partial_vm_create_failure_retains_provider_id_for_reconciliation(self):
  p,arm,_=self.make(lambda *args:True,lambda *args:True); arm.fail_vm_put=True
  with self.assertRaises(AzureProvisionError) as caught: p.provision(payload("linux"))
  self.assertRegex(caught.exception.provider_id,r"^dcp-[0-9]+-[a-f0-9]{8}$")
 def test_rejects_mac_os_and_public_network_policy(self):
  p,_,_=self.make()
  with self.assertRaises(AzureProvisionError): p.provision(payload("macos"))
  bad=payload("linux"); bad["network_policy"]="public"
  with self.assertRaises(AzureProvisionError): p.provision(bad)
 def test_vm_running_is_not_runner_online_without_checker(self):
  p,_,_=self.make(); self.assertEqual(p.status("dcp-123-abcdef12").state,"provisioning")
 def test_runner_online_requires_independent_checker(self):
  p,_,_=self.make(lambda *args:True,lambda *args:True); vm=p.provision(payload("linux")); self.assertEqual(p.status(vm.provider_id).state,"online")
 def test_runner_waits_for_vm_provisioning_success(self):
  p,arm,_=self.make(lambda *args:True,lambda *args:True); vm=p.provision(payload("linux"))
  arm.get_result["properties"]["provisioningState"]="Creating"
  self.assertEqual(p.status(vm.provider_id).state,"provisioning")
 def test_runner_waits_for_bootstrap_extension_and_deletes_on_extension_failure(self):
  p,arm,_=self.make(lambda *args:True,lambda *args:True); vm=p.provision(payload("linux"))
  arm.get_result["resources"][0]["properties"]["provisioningState"]="Creating"
  self.assertEqual(p.status(vm.provider_id).state,"provisioning")
  arm.get_result["resources"][0]["properties"]["provisioningState"]="Failed"
  self.assertEqual(p.status(vm.provider_id).state,"terminating")
  self.assertTrue(any(call[0]=="DELETE" and "Microsoft.Compute/virtualMachines/" in call[1] for call in arm.calls))
 def test_termination_waits_for_missing_vm_and_nic_before_terminal_state(self):
  p,arm,_=self.make(lambda *args:True,lambda *args:True); vm=p.provision(payload("linux")); p.terminate(vm.provider_id)
  arm.get_result=None
  self.assertEqual(p.status(vm.provider_id).state,"terminating")
  self.assertTrue(any(call[0]=="DELETE" and "networkInterfaces/" in call[1] for call in arm.calls))
  arm.nic_exists=False
  self.assertEqual(p.status(vm.provider_id).state,"terminated")
 def test_missing_nic_is_already_clean(self):
  p,arm,_=self.make(lambda *args:True,lambda *args:True); vm=p.provision(payload("linux")); p.terminate(vm.provider_id)
  arm.get_result=None; arm.nic_exists=False
  self.assertEqual(p.status(vm.provider_id).state,"terminated")
  self.assertFalse(any(call[0]=="DELETE" and "networkInterfaces/" in call[1] for call in arm.calls))
 def test_failed_vm_is_deleted_before_runner_cleanup_can_begin(self):
  p,arm,_=self.make(lambda *args:True,lambda *args:True); vm=p.provision(payload("linux"))
  arm.get_result={"properties":{"provisioningState":"Failed"},"tags":{"repository":"phakphum12345/generated-A4-pdf","target-os":"linux"}}
  self.assertEqual(p.status(vm.provider_id).state,"terminating")
  self.assertTrue(any(call[0]=="DELETE" and "Microsoft.Compute/virtualMachines/" in call[1] for call in arm.calls))
 def test_readiness_requires_bootstrap_online_and_network_policy(self):
  p,_,_=self.make()
  self.assertFalse(p.readiness("linux")["ready"])
  p,_,_=self.make(lambda _:True)
  self.assertFalse(p.readiness("linux")["ready"])
  p,_,_=self.make(lambda *args:True,lambda os_name,subnet,nsg: True)
  self.assertTrue(p.readiness("linux")["ready"])
  p,_,_=self.make(lambda *args:True,lambda *args:True,effective=False)
  # Readiness validates that the effective-policy verifier is configured;
  # the live NIC policy result is checked after NIC creation during provision.
  self.assertTrue(p.readiness("linux")["ready"])
  self.assertFalse(p.readiness("macos")["ready"])
 def test_provision_rechecks_readiness_before_any_arm_write(self):
  p,arm,_=self.make(lambda *args:True,lambda *args:False)
  with self.assertRaises(AzureProvisionError): p.provision(payload("linux"))
  self.assertFalse(any(call[0]=="PUT" for call in arm.calls))
 def test_missing_protected_bootstrap_is_rejected(self):
  p,_,_=self.make(lambda *args:True,lambda *args:True); p.bootstrap_factory=lambda *a:{"os_profile":{},"extension":{"properties":{"settings":{}}}}
  with self.assertRaises(AzureProvisionError): p.provision(payload("linux"))

 def test_effective_network_failure_prevents_bootstrap_and_vm_create(self):
  p,arm,verifier=self.make(lambda *args:True,lambda *args:True,effective=False)
  calls=[]
  def bootstrap_spy(*args):
   calls.append(args)
   return bootstrap(*args)
  p.bootstrap_factory=bootstrap_spy
  with self.assertRaises(AzureProvisionError): p.provision(payload("linux"))
  self.assertEqual(calls,[])
  self.assertFalse(any(call[0]=="PUT" and "Microsoft.Compute/virtualMachines/" in call[1] for call in arm.calls))
  self.assertTrue(any(call[0]=="DELETE" and "networkInterfaces/" in call[1] for call in arm.calls))
  self.assertEqual(len(verifier.calls),1)
if __name__=="__main__": unittest.main()
