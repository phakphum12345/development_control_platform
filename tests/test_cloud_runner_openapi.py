"""Static conformance checks for the multi-platform gateway OpenAPI contract."""
from pathlib import Path
import unittest, yaml
SPEC_PATH = Path(__file__).parents[1] / "schemas" / "cloud-runner-gateway.openapi.yaml"

class CloudRunnerOpenAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    def test_openapi_and_placeholder_server(self):
        self.assertEqual(self.spec["openapi"],"3.1.0")
        self.assertEqual(self.spec["info"]["version"],"1.1.0")
        self.assertIn("Placeholder only",self.spec["servers"][0]["description"])
    def test_lifecycle_requires_bearer_auth(self):
        self.assertEqual(self.spec["security"],[{"GatewayBearerAuth":[]}])
        p=self.spec["paths"]
        self.assertIn("post",p["/v1/runners"]); self.assertIn("get",p["/v1/runners/{id}"])
        self.assertIn("delete",p["/v1/runners/{id}"])
        self.assertEqual(self.spec["components"]["securitySchemes"]["GatewayBearerAuth"]["scheme"],"bearer")
    def test_contract_supports_three_platforms_and_guards(self):
        s=self.spec["components"]["schemas"]["RunnerCreateRequest"]; p=s["properties"]
        self.assertFalse(s["additionalProperties"])
        self.assertEqual(set(s["required"]),{"repository","workflow_run_id","commit_sha","target_os","image","labels","ephemeral","max_runtime_minutes","network_policy","registration_token_handling"})
        self.assertEqual(p["target_os"]["enum"],["linux","windows","macos"])
        self.assertEqual(p["image"]["enum"],["ubuntu-24.04-x64","windows-2025-x64","macos-15-arm64"])
        self.assertEqual(p["ephemeral"]["const"],True)
        self.assertEqual(p["network_policy"]["const"],"restricted-egress")
        self.assertEqual(p["registration_token_handling"]["const"],"provider-side-only")
        self.assertEqual(p["max_runtime_minutes"]["minimum"],5); self.assertEqual(p["max_runtime_minutes"]["maximum"],180)
    def test_responses_and_gateway_lifecycle_requirements(self):
        responses=self.spec["paths"]["/v1/runners"]["post"]["responses"]
        for code in ("202","400","401","403","409","429","503"): self.assertIn(code,responses)
        self.assertIn("not yet verified",responses["202"]["description"].lower())
        desc=self.spec["paths"]["/v1/runners"]["post"]["description"].lower()
        for word in ("authenticate","allowlisting","idempotency","billing","teardown","ttl","not evidence","server-side"):
            self.assertIn(word,desc)

if __name__ == "__main__": unittest.main()
