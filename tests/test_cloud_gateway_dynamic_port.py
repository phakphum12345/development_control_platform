"""Dynamic Gateway port selection tests."""
import unittest

from tools.cloud_gateway.server import configured_port


class DynamicPortTests(unittest.TestCase):
    def test_default_port_is_preserved_for_compatibility(self):
        self.assertEqual(configured_port({}), 8789)

    def test_zero_requests_an_operating_system_assigned_port(self):
        self.assertEqual(configured_port({"DCP_GATEWAY_PORT": "0"}), 0)

    def test_explicit_available_port_range_is_accepted(self):
        self.assertEqual(configured_port({"DCP_GATEWAY_PORT": "65535"}), 65535)

    def test_invalid_ports_are_rejected(self):
        for value in ("-1", "65536", "abc", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    configured_port({"DCP_GATEWAY_PORT": value})


if __name__ == "__main__":
    unittest.main()
