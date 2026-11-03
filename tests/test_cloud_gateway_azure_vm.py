"""Mock-only Azure VM provisioner tests. No ARM resources are created."""
import unittest
from tools.cloud_gateway.azure_vm import AzureVMProvider,AzureProvisionError
from tools.runner_backend.manager import PLATFORM_PROFILES
SUB="00000000-0000-0000-0000-000000000000"
IMAGES={"linux":{"publisher":"Canonical","offer":"ubuntu-24_04-lts","sku":"server","version":"24.04.202501150"},"windows":{"publisher":"MicrosoftWindowsServer","offer":"WindowsServer","sku":"2025-datacenter-g2","version":"20348.1.250101"}}
class FakeArm:
 subscription_id=SUB; resource_group="dcp"
 def __init__(self): self.calls=[]; self.get_result={"properties":{"provisioningState":"Succeeded"}}
 def resource_url(self,provider,kind,name,version): return f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/dcp/providers/{provider}/{kind}/{name}?api-version={version}"
 def resource_id(self,provider,kind,name): return f"/subscriptions/{SUB}/resourceGroups/dcp/providers/{provider}/{kind}/{name}"
 def request(self,method,url,payload=None,allow_missing=False): self.calls.append((method,url,payload)); return self.get_result if method=="GET" else {}
def bootstrap(vm,os_name,payload):
 os_profile={"computerName":vm,"adminUsername":"dcpadmin"}
 if os_name=="linux": os_profile["linuxConfiguration"]={"disablePasswordAuthentication":True}
 else: os_profile["adminPassword"]="test-only-password"
 return {"os_profile":os_profile,"extension":{"name":"dcp-bootstrap","properties":{"publisher":"Microsoft.Azure.Extensions","type":"CustomScript","typeHandlerVersion":"2.1","settings":{},"protectedSettings":{"script":"base64-one-time-bootstrap"}}}}
def payload(os_name):
 p=PLATFORM_PROFILES[os_name]; return {"repository":"phakphum12345/generated-A4-pdf","workflow_run_id":123,"commit_sha":"a"*40,"target_os":os_name,"image":p["image"],"labels":list(p["labels"]),"ephemeral":True,"max_runtime_minutes":30,"network_policy":"restricted-egress","registration_token_handling":"provider-side-only"}
class AzureVMTests(unittest.TestCase):
 def make(self,checker=None):
  arm=FakeArm(); p=AzureVMProvider(arm,"eastus",f"/subscriptions/{SUB}/resourceGroups/net/providers/Microsoft.Network/virtualNetworks/vnet/subnets/runners",f"/subscriptions/{SUB}/resourceGroups/net/providers/Microsoft.Network/networkSecurityGroups/runner-nsg",{"linux":"Standard_D2s_v5","windows":"Standard_D4s_v5"},IMAGES,bootstrap,checker); return p,arm
 def test_requires_existing_subnet_nsg_and_both_vm_sizes(self):
  with self.assertRaises(ValueError): AzureVMProvider(FakeArm(),"eastus","bad","bad",{"linux":"D2"},IMAGES,bootstrap)
 def test_rejects_latest_image_version(self):
  with self.assertRaises(ValueError): AzureVMProvider(FakeArm(),"eastus",f"/subscriptions/{SUB}/resourceGroups/net/providers/Microsoft.Network/virtualNetworks/vnet/subnets/runners",f"/subscriptions/{SUB}/resourceGroups/net/providers/Microsoft.Network/networkSecurityGroups/nsg",{"linux":"D2","windows":"D4"},{**IMAGES,"linux":{**IMAGES["linux"],"version":"latest"}},bootstrap)
 def test_provision_uses_ephemeral_disk_private_nic_and_tags(self):
  for os_name in ("linux","windows"):
   p,arm=self.make(); result=p.provision(payload(os_name)); self.assertEqual(result.state,"provisioning")
   nic=arm.calls[0][2]; vm=arm.calls[1][2]; self.assertNotIn("publicIPAddress",str(nic))
   self.assertEqual(vm["storageProfile"]["osDisk"]["diffDiskSettings"]["option"],"Local")
   self.assertEqual(vm["networkProfile"]["networkInterfaces"][0]["id"],f"/subscriptions/{SUB}/resourceGroups/dcp/providers/Microsoft.Network/networkInterfaces/{arm.calls[0][1].split('/')[-1].split('?')[0]}")
   self.assertNotIn("identity",vm); self.assertEqual(vm["tags"]["managed-by"],"dcp-cloud-runner")
   self.assertIn("protectedSettings",vm["resources"][0]["properties"])
 def test_rejects_mac_os_and_public_network_policy(self):
  p,_=self.make()
  with self.assertRaises(AzureProvisionError): p.provision(payload("macos"))
  bad=payload("linux"); bad["network_policy"]="public"
  with self.assertRaises(AzureProvisionError): p.provision(bad)
 def test_vm_running_is_not_runner_online_without_checker(self):
  p,_=self.make(); vm=p.provision(payload("linux")); self.assertEqual(p.status(vm.provider_id).state,"provisioning")
 def test_runner_online_requires_independent_checker(self):
  p,_=self.make(lambda _:True); vm=p.provision(payload("linux")); self.assertEqual(p.status(vm.provider_id).state,"online")
 def test_termination_waits_for_missing_vm_before_nic_cleanup(self):
  p,arm=self.make(); vm=p.provision(payload("linux")); p.terminate(vm.provider_id); self.assertEqual(arm.calls[-1][0],"DELETE")
  arm.get_result=None; self.assertEqual(p.status(vm.provider_id).state,"terminated"); self.assertEqual(arm.calls[-1][0],"DELETE")
 def test_missing_protected_bootstrap_is_rejected(self):
  p,_=self.make(); p.bootstrap_factory=lambda *a:{"os_profile":{},"extension":{"properties":{"settings":{}}}}
  with self.assertRaises(AzureProvisionError): p.provision(payload("linux"))
if __name__=="__main__": unittest.main()
