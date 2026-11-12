"""Mocked Orka API tests; never contact an Orka cluster."""
import base64,json,unittest
from unittest.mock import MagicMock,patch
from urllib.error import HTTPError
from tools.cloud_gateway.orka import OrkaProvider,OrkaError
from tools.runner_backend.manager import PLATFORM_PROFILES
def request():
 p=PLATFORM_PROFILES["macos"]; return {"repository":"phakphum12345/generated-A4-pdf","workflow_run_id":123,"commit_sha":"a"*40,"target_os":"macos","image":p["image"],"labels":list(p["labels"]),"ephemeral":True,"max_runtime_minutes":30,"network_policy":"restricted-egress","registration_token_handling":"provider-side-only"}
def response(data):
 r=MagicMock(); r.__enter__.return_value=r; r.read.return_value=json.dumps(data).encode(); return r
class SecretReader:
 def get_secret(self,name): return "mock-bearer"
class OrkaTests(unittest.TestCase):
 def make(self,checker=None,**kwargs): return OrkaProvider("https://orka.example.test","dcp","macos15-arm64",SecretReader(),runner_online_checker=checker,**kwargs)
 def make_ready(self,checker=None,bootstrap=None,**kwargs):
  return self.make(
   checker or (lambda *args:True),
   bootstrap_factory=bootstrap or (lambda name,os_name,payload:{"script":"#!/bin/bash\\nset +x\\nTOKEN='mock-registration-token'\\n"}),
   userdata_rbac_reviewed=True,
   network_policy_checker=lambda *args:True,
   cluster_readiness_checker=lambda *args:True,
   budget_readiness_checker=lambda *args:True,
   **kwargs,
  )
 def test_rejects_non_https_or_untrusted_configuration(self):
  with self.assertRaises(ValueError): OrkaProvider("http://orka.example.test","dcp","macos",SecretReader())
  with self.assertRaises(ValueError): OrkaProvider("https://@orka.example.test","dcp","macos",SecretReader())
  with self.assertRaises(ValueError): OrkaProvider("https://:pass@orka.example.test","dcp","macos",SecretReader())
  with self.assertRaises(ValueError): OrkaProvider("https://orka.example.test","../admin","macos",SecretReader())
 def test_provision_posts_pinned_vm_config_and_nonsecret_metadata(self):
  provider=self.make_ready()
  def create(req,timeout):
   body=json.loads(req.data); return response({"name":body["name"],"status":"Running"})
  with patch("tools.cloud_gateway.orka.urlopen",side_effect=create) as call: result=provider.provision(request())
  req=call.call_args.args[0]; body=json.loads(req.data)
  self.assertEqual(req.get_method(),"POST"); self.assertEqual(req.get_header("Authorization"),"Bearer mock-bearer"); self.assertTrue(any(k.lower()=="authorization" for k in req.unredirected_hdrs))
  self.assertEqual(body["vmConfig"],"macos15-arm64")
  self.assertNotIn("mock-registration-token",json.dumps(body))
  self.assertIn("mock-registration-token",base64.b64decode(body["userdata"]).decode())
  self.assertEqual(result.state,"provisioning")
 def test_rejects_linux_and_non_ephemeral_payloads(self):
  p=self.make(); bad=request(); bad["target_os"]="linux"
  with self.assertRaises(OrkaError): p.provision(bad)
  bad=request(); bad["ephemeral"]=False
  with self.assertRaises(OrkaError): p.provision(bad)
 def test_running_vm_is_not_online_without_github_runner_evidence(self):
  p=self.make(); name="dcp-123-"+"a"*8
  with patch("tools.cloud_gateway.orka.urlopen",return_value=response({"status":"Running","name":name})): result=p.status(name)
  self.assertEqual(result.state,"provisioning")
 def test_online_requires_runner_checker(self):
  p=self.make(lambda *args:True); name="dcp-123-"+"a"*8
  with patch("tools.cloud_gateway.orka.urlopen",return_value=response({"status":"Running","userdataPhase":"success","name":name,"customMetadata":{"repository":"phakphum12345/generated-A4-pdf","target-os":"macos"}})): self.assertEqual(p.status(name).state,"online")
 def test_delete_acceptance_is_terminating_and_404_confirms_gone(self):
  p=self.make(); name="dcp-123-"+"a"*8
  with patch("tools.cloud_gateway.orka.urlopen",return_value=response({"status":"Terminating"})): self.assertEqual(p.terminate(name).state,"terminating")
  with patch("tools.cloud_gateway.orka.urlopen",side_effect=HTTPError("url",404,"missing",{},None)): self.assertEqual(p.status(name).state,"terminated")
 def test_failed_orka_vm_is_deleted_before_terminal_state(self):
  p=self.make(); name="dcp-123-"+"a"*8
  with patch("tools.cloud_gateway.orka.urlopen",return_value=response({"status":"Failed","name":name})):
   result=p.status(name)
  self.assertEqual(result.state,"terminating")
 def test_readiness_fails_closed_without_protected_guest_bootstrap(self):
  p=self.make(lambda *args:True)
  readiness=p.readiness("macos")
  self.assertFalse(readiness["ready"])
  self.assertIn("User Data bootstrap",readiness["message"])
 def test_readiness_and_provisioning_require_namespace_rbac_network_cluster_and_budget(self):
  p=self.make(lambda *args:True,bootstrap_factory=lambda *args:{"script":"#!/bin/bash"},userdata_rbac_reviewed=True,network_policy_checker=lambda *args:True,cluster_readiness_checker=lambda *args:True)
  self.assertFalse(p.readiness("macos")["ready"])
  with self.assertRaises(OrkaError): p.provision(request())
 def test_rejects_user_data_larger_than_encoded_api_limit(self):
  p=self.make_ready(bootstrap=lambda *args:{"script":"x"*50000})
  with self.assertRaises(OrkaError):
   p.provision(request())
 def test_userdata_phase_must_succeed_before_runner_online(self):
  p=self.make(lambda *args:True); name="dcp-123-"+"a"*8
  with patch("tools.cloud_gateway.orka.urlopen",return_value=response({"status":"Running","userdataPhase":"pending","name":name})):
   self.assertEqual(p.status(name).state,"provisioning")
  with patch("tools.cloud_gateway.orka.urlopen",side_effect=[response({"status":"Running","userdataPhase":"failed","name":name}),response({"status":"Terminating"})]):
   self.assertEqual(p.status(name).state,"terminating")
 def test_provider_errors_do_not_echo_credentials(self):
  p=self.make_ready()
  with patch("tools.cloud_gateway.orka.urlopen",side_effect=HTTPError("url",401,"denied",{},None)):
   with self.assertRaises(OrkaError) as caught: p.provision(request())
  self.assertNotIn("mock-bearer",str(caught.exception))
if __name__=="__main__": unittest.main()
