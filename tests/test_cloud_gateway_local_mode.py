"""Tests for the no-network, no-cost Local-first environment doctor."""
import unittest

from tools.cloud_gateway.local_mode import inspect_local_environment


class LocalModeDoctorTests(unittest.TestCase):
    def test_reports_local_first_and_skips_network_and_cloud(self):
        result = inspect_local_environment({})
        checks = {item["check"]: item for item in result["checks"]}
        self.assertEqual(result["mode"], "local-first")
        self.assertEqual(checks["cloud_provisioning"]["status"], "SKIPPED")
        self.assertEqual(checks["network_listener"]["status"], "SKIPPED")
        self.assertEqual(checks["cloud_provisioning_default"]["status"], "PASS")

    def test_never_echoes_environment_values(self):
        secret = "local-doctor-must-not-print-this"
        result = inspect_local_environment({
            "DCP_GATEWAY_API_TOKEN": secret,
            "DCP_TRUSTED_PROXY_HMAC_SECRET": secret,
            "DCP_GATEWAY_PROVISIONING_ENABLED": "false",
        })
        self.assertNotIn(secret, str(result))

    def test_cloud_provisioning_enabled_is_a_failure_for_local_first(self):
        result = inspect_local_environment({
            "DCP_GATEWAY_PROVISIONING_ENABLED": "true",
        })
        checks = {item["check"]: item for item in result["checks"]}
        self.assertEqual(checks["cloud_provisioning_default"]["status"], "FAIL")
        self.assertEqual(result["overall"], "FAIL")

    def test_optional_tools_do_not_make_the_doctor_fail(self):
        result = inspect_local_environment({})
        checks = {item["check"]: item for item in result["checks"]}
        self.assertIn(checks["git"]["status"], ("PASS", "UNKNOWN"))
        self.assertIn(checks["container_runtime"]["status"], ("PASS", "UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
