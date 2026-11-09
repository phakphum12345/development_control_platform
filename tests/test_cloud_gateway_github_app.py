"""Mock-only GitHub App bootstrap tests; no GitHub or cloud calls."""
import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tools.cloud_gateway.github_app import GitHubAppError, GitHubAppRunnerBootstrap, GitHubRunnerOnlineChecker


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

    def test_bearer_token_is_marked_unredirected(self):
        captured = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b"{}"
        def opener(request, timeout):
            captured.append(request)
            return Response()
        self.make(opener=opener)._request("GET", "/app/installations/1", "jwt-secret")
        request = captured[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer jwt-secret")
        self.assertTrue(any(key.lower() == "authorization" for key in request.unredirected_hdrs))

    def test_http_error_is_sanitized(self):
        from urllib.error import HTTPError
        app = self.make(opener=lambda *a, **k: (_ for _ in ()).throw(
            HTTPError("url", 403, "denied", {}, None)
        ))
        with self.assertRaisesRegex(GitHubAppError, "HTTP 403") as caught:
            app._request("POST", "/app/installations/1/access_tokens", "jwt")
        self.assertNotIn("jwt", str(caught.exception))


    def test_platform_online_checker_uses_expected_os_labels(self):
        class StubApp:
            def __init__(self):
                self.args = None
            def is_runner_online(self, repository, runner_name, labels):
                self.args = (repository, runner_name, tuple(labels))
                return True
        stub = StubApp()
        checker = GitHubRunnerOnlineChecker(stub)
        self.assertTrue(checker("dcp-123-abcdef12", "phakphum12345/generated-A4-pdf", "windows"))
        self.assertEqual(stub.args[2], ("self-hosted", "Windows", "X64", "dcp-cloud-windows"))
        self.assertFalse(checker("dcp-123-abcdef12", "phakphum12345/generated-A4-pdf", "unknown"))

    def test_runner_inventory_paginates_before_deciding_runner_is_absent(self):
        app = self.make()
        calls = []
        def request(method, path, token, payload=None):
            calls.append(path)
            if path.startswith("/app/"):
                return {
                    "token": "read-installation-token",
                    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat(),
                    "permissions": {"administration": "read"},
                }
            if path.endswith("page=1"):
                return {"runners": [
                    {"id": i + 1, "name": "other-" + str(i), "status": "offline"}
                    for i in range(100)
                ]}
            return {"runners": [{
                "id": 999, "name": "dcp-123-abcdef12", "status": "offline",
                "labels": [{"name": "self-hosted"}],
            }]}
        app._request = request
        runner = app.find_runner("phakphum12345/generated-A4-pdf", "dcp-123-abcdef12")
        self.assertEqual(runner["id"], 999)
        self.assertEqual(len([path for path in calls if "actions/runners?" in path]), 2)

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
        self.assertEqual(calls[1][1], "/repos/phakphum12345/generated-A4-pdf/actions/runners?per_page=100&page=1")

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


    def test_dynamic_installation_catalog_lists_only_installed_repositories(self):
        app = GitHubAppRunnerBootstrap(
            "123456", 987654, self.pem, [],
            clock=lambda: 1_800_000_000,
        )
        app._installation_catalog_token = lambda: "catalog-token"
        calls = []

        def request(method, path, token, payload=None):
            calls.append((method, path, token))
            return {
                "total_count": 2,
                "repositories": [
                    {
                        "full_name": "example/private-app",
                        "private": True,
                        "default_branch": "main",
                        "permissions": {"admin": True, "push": True, "metadata": "read"},
                        "html_url": "https://github.com/example/private-app",
                    },
                    {
                        "full_name": "example/public-app",
                        "private": False,
                        "default_branch": "trunk",
                        "permissions": {"pull": True, "push": False},
                    },
                ],
            }

        app._request = request
        catalog = app.list_installation_repositories()
        self.assertEqual([item["full_name"] for item in catalog], [
            "example/private-app", "example/public-app"
        ])
        self.assertTrue(catalog[0]["private"])
        self.assertEqual(catalog[0]["permissions"], {"admin": True, "push": True})
        self.assertNotIn("html_url", catalog[0])
        self.assertTrue(app.is_repository_accessible("example/private-app"))
        self.assertFalse(app.is_repository_accessible("example/not-installed"))
        self.assertEqual(len(calls), 1, "catalog should be cached for its short TTL")

    def test_dynamic_installation_catalog_fails_closed_on_malformed_repository(self):
        app = GitHubAppRunnerBootstrap(
            "123456", 987654, self.pem, [],
            clock=lambda: 1_800_000_000,
        )
        app._installation_catalog_token = lambda: "catalog-token"
        app._request = lambda *args, **kwargs: {
            "total_count": 1,
            "repositories": [{"full_name": "invalid-name", "private": True}],
        }
        with self.assertRaisesRegex(GitHubAppError, "malformed"):
            app.list_installation_repositories()

    def test_dynamic_registration_refuses_repository_outside_installation(self):
        app = GitHubAppRunnerBootstrap(
            "123456", 987654, self.pem, [],
            clock=lambda: 1_800_000_000,
        )
        app._installation_catalog_token = lambda: "catalog-token"
        app._request = lambda method, path, token, payload=None: {
            "total_count": 1,
            "repositories": [{
                "full_name": "example/installed",
                "private": True,
                "default_branch": "main",
            }],
        }
        with self.assertRaisesRegex(GitHubAppError, "not accessible"):
            app.create_registration_token("attacker/repo")


if __name__ == "__main__":
    unittest.main()
