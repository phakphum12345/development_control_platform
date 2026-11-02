"""Static conformance checks for the provider-neutral gateway OpenAPI contract."""
from pathlib import Path
import unittest

import yaml


SPEC_PATH = Path(__file__).parents[1] / "schemas" / "cloud-runner-gateway.openapi.yaml"


class CloudRunnerOpenAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

    def test_openapi_document_and_placeholder_server_are_explicit(self):
        self.assertEqual(self.spec["openapi"], "3.1.0")
        self.assertEqual(self.spec["info"]["version"], "1.0.0")
        self.assertIn("Placeholder only", self.spec["servers"][0]["description"])

    def test_all_lifecycle_operations_require_bearer_auth(self):
        self.assertEqual(self.spec["security"], [{"GatewayBearerAuth": []}])
        paths = self.spec["paths"]
        self.assertIn("post", paths["/v1/runners"])
        self.assertIn("get", paths["/v1/runners/{id}"])
        self.assertIn("delete", paths["/v1/runners/{id}"])
        auth = self.spec["components"]["securitySchemes"]["GatewayBearerAuth"]
        self.assertEqual(auth["type"], "http")
        self.assertEqual(auth["scheme"], "bearer")

    def test_create_request_matches_dcp_policy(self):
        schema = self.spec["components"]["schemas"]["RunnerCreateRequest"]
        required = {
            "repository", "workflow_run_id", "commit_sha", "image", "labels",
            "ephemeral", "max_runtime_minutes", "network_policy",
            "registration_token_handling",
        }
        self.assertEqual(set(schema["required"]), required)
        props = schema["properties"]
        self.assertEqual(props["image"]["const"], "macos-15-arm64")
        self.assertEqual(props["ephemeral"]["const"], True)
        self.assertEqual(props["network_policy"]["const"], "restricted-egress")
        self.assertEqual(props["registration_token_handling"]["const"], "provider-side-only")
        self.assertEqual(props["max_runtime_minutes"]["minimum"], 5)
        self.assertEqual(props["max_runtime_minutes"]["maximum"], 180)
        self.assertEqual(props["workflow_run_id"]["minimum"], 1)
        self.assertEqual(props["commit_sha"]["pattern"], "^[0-9a-f]{40}$")
        self.assertFalse(schema["additionalProperties"])

    def test_response_contract_and_http_failure_modes_are_documented(self):
        runner = self.spec["components"]["schemas"]["Runner"]
        self.assertEqual(set(runner["required"]), {"id", "state"})
        responses = self.spec["paths"]["/v1/runners"]["post"]["responses"]
        for status in ("202", "400", "401", "403", "409", "429", "503"):
            self.assertIn(status, responses)
        accepted = responses["202"]["description"].lower()
        self.assertIn("not yet verified", accepted)

    def test_gateway_security_and_lifecycle_obligations_are_explicit(self):
        description = self.spec["paths"]["/v1/runners"]["post"]["description"].lower()
        for requirement in (
            "authenticate the caller", "repository", "idempotency", "billing",
            "teardown", "ttl", "not evidence",
        ):
            self.assertIn(requirement, description)


if __name__ == "__main__":
    unittest.main()
