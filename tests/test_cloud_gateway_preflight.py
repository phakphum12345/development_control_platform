"""Read-only deployment preflight tests; no network or secrets are used."""
import unittest

from tools.cloud_gateway.preflight import inspect_environment


class GatewayPreflightTests(unittest.TestCase):
    def test_empty_environment_is_unknown_and_provisioning_stays_disabled(self):
        result = inspect_environment({})
        self.assertEqual(result["overall"], "UNKNOWN")
        self.assertFalse(result["provisioning_enabled"])
        self.assertTrue(any(item["status"] == "SKIPPED" for item in result["checks"]))

    def test_never_echoes_secret_values(self):
        marker = "DO-NOT-LEAK-THIS-SECRET-VALUE"
        result = inspect_environment({
            "DCP_GATEWAY_API_TOKEN": marker,
            "DCP_TRUSTED_PROXY_HMAC_SECRET": marker,
        })
        self.assertNotIn(marker, str(result))

    def test_valid_gateway_edge_configuration_is_passed_without_claiming_provider_readiness(self):
        env = {
            "DCP_GATEWAY_API_TOKEN": "api-token-value",
            "DCP_TRUSTED_PROXY_HMAC_SECRET": "x" * 40,
            "DCP_PUBLIC_ORIGIN": "https://dcp.example.test",
            "DCP_GATEWAY_ALLOWED_REPOSITORIES": "owner/repo",
            "DCP_GATEWAY_OWNER_APPROVED": "true",
        }
        result = inspect_environment(env)
        checks = {item["check"]: item for item in result["checks"]}
        self.assertEqual(checks["gateway_api_token"]["status"], "PASS")
        self.assertEqual(checks["trusted_proxy"]["status"], "PASS")
        self.assertEqual(checks["repository_allowlist"]["status"], "PASS")
        self.assertEqual(checks["azure_network_policy"]["status"], "UNKNOWN")
        self.assertEqual(checks["orka_user_data_bootstrap"]["status"], "UNKNOWN")
        self.assertEqual(result["overall"], "UNKNOWN")

    def test_invalid_allowlist_and_non_https_origin_do_not_pass(self):
        result = inspect_environment({
            "DCP_GATEWAY_ALLOWED_REPOSITORIES": "owner/repo,not-a-repo",
            "DCP_TRUSTED_PROXY_HMAC_SECRET": "x" * 40,
            "DCP_PUBLIC_ORIGIN": "http://dcp.example.test",
        })
        checks = {item["check"]: item for item in result["checks"]}
        self.assertEqual(checks["repository_allowlist"]["status"], "UNKNOWN")
        self.assertEqual(checks["trusted_proxy"]["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
