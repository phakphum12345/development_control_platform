"""Mock-only GitHub App bootstrap tests; no GitHub or cloud calls."""
import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tools.cloud_gateway.github_app import GitHubAppError, GitHubAppRunnerBootstrap


def encoded_part(part):
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


class GitHubAppBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()

    def make(self, opener=None):
        return GitHubAppRunnerBootstrap(
            "123456", 987654, self.pem,
            ["phakphum12345/generated-A4-pdf"],
            clock=lambda: 1_800_000_000,
            opener=opener,
        )

    def test_jwt_is_rs256_and_short_lived(self):
        jwt = self.make()._app_jwt()
        header, claims, signature = jwt.split(".")
        self.assertEqual(encoded_part(header), {"alg": "RS256", "typ": "JWT"})
        body = encoded_part(claims)
        self.assertEqual(body["iss"], "123456")
        self.assertEqual(body["exp"] - body["iat"], 570)
        self.assertTrue(signature)

    def test_rejects_unallowlisted_repository_before_network(self):
        app = self.make()
        with self.assertRaises(GitHubAppError):
            app.create_registration_token("attacker/repo")

    def test_rejects_invalid_app_configuration(self):
        with self.assertRaises(ValueError):
            GitHubAppRunnerBootstrap("not-numeric", 1, self.pem, ["owner/repo"])
        with self.assertRaises(ValueError):
            GitHubAppRunnerBootstrap("123", 0, self.pem, ["owner/repo"])
        with self.assertRaises(ValueError):
            GitHubAppRunnerBootstrap("123", 1, self.pem, ["owner/repo", "owner/repo"])

    def test_scopes_installation_and_registration_to_allowlisted_repo(self):
        app = self.make()
        future = (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat()
        registration_expiry = (datetime.now(timezone.utc) + timedelta(minutes=50)).isoformat()
        responses = [
            {"token": "installation-secret", "expires_at": future, "permissions": {"administration": "write"}},
            {"token": "registration-secret", "expires_at": registration_expiry},
        ]
        seen = []

        def request(method, path, token, payload=None):
            seen.append((method, path, token, payload))
            return responses.pop(0)

        app._request = request
        credential = app.create_registration_token("phakphum12345/generated-A4-pdf")
        self.assertEqual(credential.token, "registration-secret")
        self.assertNotIn("registration-secret", repr(credential))
        self.assertEqual(seen[0][1], "/app/installations/987654/access_tokens")
        self.assertEqual(seen[0][3], {"repositories": ["phakphum12345/generated-A4-pdf"], "permissions": {"administration": "write"}})
        self.assertEqual(seen[1][1], "/repos/phakphum12345/generated-A4-pdf/actions/runners/registration-token")
        self.assertEqual(seen[1][2], "installation-secret")

    def test_requires_administration_write_permission(self):
        app = self.make()
        app._request = lambda *args, **kwargs: {
            "token": "installation-secret",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat(),
            "permissions": {"administration": "read"},
        }
        with self.assertRaises(GitHubAppError):
            app.create_registration_token("phakphum12345/generated-A4-pdf")

    def test_rejects_expired_registration_token(self):
        app = self.make()
        app._request = lambda method, path, token, payload=None: (
            {"token": "installation-secret",
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
             "permissions": {"administration": "write"}}
            if path.startswith("/app/") else
            {"token": "registration-secret",
             "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        )
        with self.assertRaises(GitHubAppError):
            app.create_registration_token("phakphum12345/generated-A4-pdf")

    def test_http_error_is_sanitized(self):
        from urllib.error import HTTPError
        app = self.make(opener=lambda *a, **k: (_ for _ in ()).throw(
            HTTPError("url", 403, "denied", {}, None)
        ))
        with self.assertRaisesRegex(GitHubAppError, "HTTP 403") as caught:
            app._request("POST", "/app/installations/1/access_tokens", "jwt")
        self.assertNotIn("jwt", str(caught.exception))


    def test_runner_online_requires_exact_name_status_and_labels(self):
        app = self.make()
        calls = []
        def request(method, path, token, payload=None):
            calls.append((method, path, payload))
            if path.startswith("/app/"):
                return {
                    "token": "read-installation-token",
                    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat(),
                    "permissions": {"administration": "read"},
                }
            return {"runners": [{
                "id": 42,
                "name": "dcp-123-abcdef12",
                "status": "online",
                "labels": [{"name": "self-hosted"}, {"name": "Linux"}, {"name": "X64"}],
            }]}
        app._request = request
        self.assertTrue(app.is_runner_online(
            "phakphum12345/generated-A4-pdf",
            "dcp-123-abcdef12",
            ["self-hosted", "Linux", "X64"],
        ))
        self.assertEqual(calls[0][2], {
            "repositories": ["phakphum12345/generated-A4-pdf"],
            "permissions": {"administration": "read"},
        })
        self.assertEqual(calls[1][1], "/repos/phakphum12345/generated-A4-pdf/actions/runners?per_page=100")

    def test_runner_online_fails_closed_for_missing_runner(self):
        app = self.make()
        token_response = {
            "token": "read-installation-token",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat(),
            "permissions": {"administration": "read"},
        }
        app._request = lambda method, path, token, payload=None: (
            token_response if path.startswith("/app/") else {"runners": []}
        )
        self.assertFalse(app.is_runner_online(
            "phakphum12345/generated-A4-pdf", "dcp-123-abcdef12", ["Linux"]
        ))

    def test_remove_runner_uses_scoped_admin_write_token_after_offline_check(self):
        app = self.make()
        calls = []
        def request(method, path, token, payload=None):
            calls.append((method, path, payload))
            if path.startswith("/app/"):
                permission = "read" if sum(1 for call in calls if call[1].startswith("/app/")) == 1 else "write"
                return {
                    "token": permission + "-installation-token",
                    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat(),
                    "permissions": {"administration": permission},
                }
            if method == "GET":
                return {"runners": [{"id": 42, "name": "dcp-123-abcdef12", "status": "offline"}]}
            return {}
        app._request = request
        self.assertTrue(app.remove_runner("phakphum12345/generated-A4-pdf", 42))
        self.assertEqual(calls[1][0], "GET")
        self.assertEqual(calls[2][1], "/app/installations/987654/access_tokens")
        self.assertEqual(calls[3][0], "DELETE")
        self.assertEqual(calls[3][1], "/repos/phakphum12345/generated-A4-pdf/actions/runners/42")
        with self.assertRaises(GitHubAppError):
            app.remove_runner("phakphum12345/generated-A4-pdf", True)

    def test_remove_runner_refuses_online_runner(self):
        app = self.make()
        def request(method, path, token, payload=None):
            if path.startswith("/app/"):
                return {
                    "token": "read-installation-token",
                    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat(),
                    "permissions": {"administration": "read"},
                }
            return {"runners": [{"id": 42, "name": "dcp-123-abcdef12", "status": "online"}]}
        app._request = request
        with self.assertRaisesRegex(GitHubAppError, "not confirmed offline"):
            app.remove_runner("phakphum12345/generated-A4-pdf", 42)


if __name__ == "__main__":
    unittest.main()
