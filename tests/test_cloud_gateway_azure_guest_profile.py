"""Unit tests for least-privilege Azure ephemeral guest profiles."""
import base64
import unittest

from tools.cloud_gateway.azure_guest_profile import (
    AzureGuestProfileError,
    AzureGuestProfileFactory,
)


def public_key():
    key_type = b"ssh-ed25519"
    wire = (
        len(key_type).to_bytes(4, "big") + key_type
        + (32).to_bytes(4, "big") + b"\x01" * 32
    )
    return "ssh-ed25519 " + base64.b64encode(wire).decode("ascii") + " test-key"


def request(os_name):
    return {"target_os": os_name, "ephemeral": True}


class AzureGuestProfileTests(unittest.TestCase):
    def make(self):
        return AzureGuestProfileFactory("dcpadmin", public_key())

    def test_linux_disables_password_auth_and_uses_only_public_key(self):
        profile = self.make()("dcp-123-abcdef12", "linux", request("linux"))
        self.assertEqual(profile["adminUsername"], "dcpadmin")
        self.assertTrue(profile["linuxConfiguration"]["disablePasswordAuthentication"])
        key = profile["linuxConfiguration"]["ssh"]["publicKeys"][0]
        self.assertEqual(key["path"], "/home/dcpadmin/.ssh/authorized_keys")
        self.assertEqual(key["keyData"], public_key())
        self.assertNotIn("adminPassword", profile)
        self.assertNotIn("identity", profile)

    def test_windows_password_is_random_complex_and_not_persisted_by_factory(self):
        factory = self.make()
        first = factory("dcp-123-abcdef12", "windows", request("windows"))
        second = factory("dcp-124-abcdef12", "windows", request("windows"))
        password = first["adminPassword"]
        self.assertGreaterEqual(len(password), 48)
        self.assertRegex(password, r"[a-z]")
        self.assertRegex(password, r"[A-Z]")
        self.assertRegex(password, r"[0-9]")
        self.assertTrue(any(char in "!@#$%^-_=+" for char in password))
        self.assertNotEqual(password, second["adminPassword"])
        self.assertNotIn("linuxConfiguration", first)
        self.assertNotIn("identity", first)
        self.assertNotIn("password", repr(factory).lower())

    def test_environment_factory_requires_username_and_valid_public_key(self):
        env = {
            "DCP_AZURE_GUEST_ADMIN_USERNAME": "dcpadmin",
            "DCP_AZURE_LINUX_SSH_PUBLIC_KEY": public_key(),
        }
        factory = AzureGuestProfileFactory.from_environment(env)
        self.assertEqual(factory.admin_username, "dcpadmin")
        with self.assertRaises(AzureGuestProfileError):
            AzureGuestProfileFactory.from_environment({})

    def test_rejects_non_ed25519_or_malformed_public_keys(self):
        for key in ("ssh-rsa AAAA", "not-a-key", "ssh-ed25519 !!!"):
            with self.subTest(key=key), self.assertRaises(AzureGuestProfileError):
                AzureGuestProfileFactory("dcpadmin", key)

    def test_rejects_reserved_or_invalid_admin_usernames(self):
        for username in ("root", "admin", "Administrator", "x", "bad user"):
            with self.subTest(username=username), self.assertRaises(AzureGuestProfileError):
                AzureGuestProfileFactory(username, public_key())

    def test_rejects_non_ephemeral_or_mismatched_guest_os(self):
        factory = self.make()
        with self.assertRaises(AzureGuestProfileError):
            factory("dcp-123-abcdef12", "linux", {"target_os": "linux", "ephemeral": False})
        with self.assertRaises(AzureGuestProfileError):
            factory("dcp-123-abcdef12", "windows", request("linux"))
        with self.assertRaises(AzureGuestProfileError):
            factory("dcp-123-abcdef12", "macos", request("macos"))


if __name__ == "__main__":
    unittest.main()
