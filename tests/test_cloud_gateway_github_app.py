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
            {"token": "installation-secret", "expires_at": future, "permissions": {"actions": "write"}},
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
        self.assertEqual(seen[0][3], {"repositories": ["phakphum12345/generated-A4-pdf"]})
        self.assertEqual(seen[1][1], "/repos/phakphum12345/generated-A4-pdf/actions/runners/registration-token")
        self.assertEqual(seen[1][2], "installation-secret")

    def test_requires_actions_write_permission(self):
        app = self.make()
        app._request = lambda *args, **kwargs: {
            "token": "installation-secret",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat(),
            "permissions": {"actions": "read"},
        }
        with self.assertRaises(GitHubAppError):
            app.create_registration_token("phakphum12345/generated-A4-pdf")

    def test_rejects_registration_token_that_outlives_installation_token(self):
        app = self.make()
        app._request = lambda method, path, token, payload=None: (
            {"token": "installation-secret",
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
             "permissions": {"actions": "write"}}
            if path.startswith("/app/") else
            {"token": "registration-secret",
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()}
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


if __name__ == "__main__":
    unittest.main()
