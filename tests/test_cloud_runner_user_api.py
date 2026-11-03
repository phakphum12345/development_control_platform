"""Authenticated browser control API tests; no cloud resources or real credentials."""
import hashlib
import hmac
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.cloud_gateway.policy import GatewaySettings
from tools.cloud_gateway.server import DisabledProvider, ProxyIdentityVerifier, make_handler
from tools.cloud_gateway.oidc_assertion import OIDCAssertionError, sign_verified_oidc_assertion
from tools.cloud_gateway.service import GatewayService
from tools.cloud_gateway.store import RunnerStore

SECRET = "test-proxy-secret-that-is-at-least-32-bytes-long"
ORIGIN = "https://dcp.example.test"


def signed_headers(method, path, nonce, role="operator", subject="test-user",
                   session="session_1234567890abcdef"):
    timestamp = str(int(time.time()))
    canonical = "\n".join((method, path, subject, role, session, timestamp, nonce)).encode()
    signature = hmac.new(SECRET.encode(), canonical, hashlib.sha256).hexdigest()
    return {
        "X-DCP-User": subject, "X-DCP-Role": role, "X-DCP-Session": session,
        "X-DCP-Auth-Timestamp": timestamp, "X-DCP-Auth-Nonce": nonce,
        "X-DCP-Auth-Signature": signature,
    }


class AuthenticatedControlAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RunnerStore(str(Path(self.temp.name) / "gateway.sqlite"))
        self.settings = GatewaySettings(allowed_repositories=("phakphum12345/generated-A4-pdf",))
        self.service = GatewayService(self.settings, self.store, DisabledProvider())
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(self.service, "internal-gateway-token", SECRET, ORIGIN),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, nonce, extra=None, body=None):
        headers = signed_headers(method, path, nonce)
        headers.update(extra or {})
        data = None if body is None else json.dumps(body).encode()
        return Request(self.base + path, data=data, method=method, headers=headers)

    def test_session_status_and_inventory_require_signed_proxy_identity(self):
        with urlopen(self.request("GET", "/api/auth/session", "nonce_session_0001")) as response:
            session = json.loads(response.read())
            self.assertTrue(session["authenticated"])
            self.assertEqual(len(session["csrfToken"]), 64)
        with urlopen(self.request("GET", "/api/cloud-runners/status", "nonce_status_0001")) as response:
            status = json.loads(response.read())
            self.assertEqual(status["gateway"], "READY")
            self.assertFalse(status["bootstrap_ready"])
            self.assertFalse(status["providers"]["linux"]["ready"])
            self.assertEqual(status["budget_gate"], "UNKNOWN")
        with urlopen(self.request("GET", "/api/cloud-runners", "nonce_list_000001")) as response:
            self.assertEqual(json.loads(response.read()), {"runners": []})

    def test_missing_or_invalid_identity_is_denied(self):
        req = Request(self.base + "/api/cloud-runners/status")
        with self.assertRaises(HTTPError) as error:
            urlopen(req)
        self.assertEqual(error.exception.code, 401)
        headers = signed_headers("GET", "/api/cloud-runners/status", "nonce_forged_00001")
        headers["X-DCP-Auth-Signature"] = "0" * 64
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base + "/api/cloud-runners/status", headers=headers))
        self.assertEqual(error.exception.code, 401)

    def test_oidc_verified_claims_map_to_signed_gateway_assertion(self):
        claims = {
            "iss": "https://idp.example.test/",
            "aud": ["dcp-web", "other-client"], "azp": "dcp-web",
            "sub": "oidc-subject-123",
            "groups": ["dcp-operators"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }
        headers = sign_verified_oidc_assertion(
            "GET", "/api/cloud-runners/status?view=compact", claims,
            "session_1234567890abcdef", SECRET,
            "https://idp.example.test/", "dcp-web",
            ["dcp-owners"], ["dcp-operators"],
        )
        self.assertEqual(headers["X-DCP-User"], "oidc-subject-123")
        self.assertEqual(headers["X-DCP-Role"], "operator")
        class Handler:
            command = "GET"
            path = "/api/cloud-runners/status?view=compact"
            def __init__(self, headers):
                self.headers = headers
        verifier = ProxyIdentityVerifier(SECRET)
        identity = verifier.verify(Handler(headers))
        self.assertEqual(identity["subject"], "oidc-subject-123")
        self.assertEqual(identity["role"], "operator")

    def test_oidc_owner_group_has_owner_role_and_invalid_claims_fail_closed(self):
        claims = {
            "iss": "https://idp.example.test/", "aud": "dcp-web",
            "sub": "owner-subject", "groups": ["dcp-owners"],
            "iat": int(time.time()), "exp": int(time.time()) + 300,
        }
        headers = sign_verified_oidc_assertion(
            "POST", "/api/cloud-runners", claims, "session_1234567890abcdef",
            SECRET, "https://idp.example.test/", "dcp-web",
            ["dcp-owners"], ["dcp-operators"],
        )
        self.assertEqual(headers["X-DCP-Role"], "owner")
        with self.assertRaises(OIDCAssertionError):
            sign_verified_oidc_assertion(
                "GET", "/api/cloud-runners", claims, "session_1234567890abcdef",
                SECRET, "https://wrong.example/", "dcp-web",
                ["dcp-owners"], ["dcp-operators"],
            )
        bad_azp = dict(claims, azp="other-client")
        with self.assertRaises(OIDCAssertionError):
            sign_verified_oidc_assertion(
                "GET", "/api/cloud-runners", bad_azp, "session_1234567890abcdef",
                SECRET, "https://idp.example.test/", "dcp-web",
                ["dcp-owners"], ["dcp-operators"],
            )
        not_yet_valid = dict(claims, nbf=int(time.time()) + 300)
        with self.assertRaises(OIDCAssertionError):
            sign_verified_oidc_assertion(
                "GET", "/api/cloud-runners", not_yet_valid, "session_1234567890abcdef",
                SECRET, "https://idp.example.test/", "dcp-web",
                ["dcp-owners"], ["dcp-operators"],
            )
        expired = dict(claims, exp=int(time.time()) - 1)
        with self.assertRaises(OIDCAssertionError):
            sign_verified_oidc_assertion(
                "GET", "/api/cloud-runners", expired, "session_1234567890abcdef",
                SECRET, "https://idp.example.test/", "dcp-web",
                ["dcp-owners"], ["dcp-operators"],
            )

    def test_durable_nonce_expiry_allows_reuse_only_after_window(self):
        nonce = "durable_nonce_000001"
        self.assertTrue(self.store.consume_auth_nonce(nonce, 100.0, 160.0))
        self.assertFalse(self.store.consume_auth_nonce(nonce, 120.0, 180.0))
        self.assertTrue(self.store.consume_auth_nonce(nonce, 161.0, 221.0))

    def test_oidc_assertion_is_bound_to_method_and_path(self):
        claims = {
            "iss": "https://idp.example.test/", "aud": "dcp-web",
            "sub": "oidc-subject-789", "groups": ["dcp-operators"],
            "iat": int(time.time()), "exp": int(time.time()) + 300,
        }
        headers = sign_verified_oidc_assertion(
            "GET", "/api/cloud-runners/status", claims,
            "session_1234567890abcdef", SECRET,
            "https://idp.example.test/", "dcp-web",
            ["dcp-owners"], ["dcp-operators"],
        )
        class Handler:
            command = "GET"
            path = "/api/cloud-runners"
            def __init__(self, value):
                self.headers = value
        self.assertIsNone(ProxyIdentityVerifier(SECRET).verify(Handler(headers)))

    def test_durable_nonce_replay_is_rejected_across_verifier_instances(self):
        claims = {
            "iss": "https://idp.example.test/", "aud": "dcp-web",
            "sub": "oidc-subject-456", "groups": ["dcp-operators"],
            "iat": int(time.time()), "exp": int(time.time()) + 300,
        }
        headers = sign_verified_oidc_assertion(
            "GET", "/api/cloud-runners/status", claims,
            "session_1234567890abcdef", SECRET,
            "https://idp.example.test/", "dcp-web",
            ["dcp-owners"], ["dcp-operators"],
        )
        class Handler:
            command = "GET"
            path = "/api/cloud-runners/status"
            def __init__(self, value):
                self.headers = value
        first = ProxyIdentityVerifier(SECRET, nonce_store=self.store)
        second = ProxyIdentityVerifier(SECRET, nonce_store=self.store)
        self.assertIsNotNone(first.verify(Handler(headers)))
        self.assertIsNone(second.verify(Handler(headers)))

    def test_durable_nonce_store_fails_closed_when_unavailable(self):
        class BrokenStore:
            def consume_auth_nonce(self, *args):
                raise RuntimeError("database unavailable")
        headers = signed_headers("GET", "/api/cloud-runners/status", "nonce_durable_0001")
        class Handler:
            command = "GET"
            path = "/api/cloud-runners/status"
            def __init__(self, value):
                self.headers = value
        verifier = ProxyIdentityVerifier(SECRET, nonce_store=BrokenStore())
        self.assertIsNone(verifier.verify(Handler(headers)))

    def test_proxy_nonce_replay_is_rejected(self):
        req = self.request("GET", "/api/cloud-runners/status", "nonce_replay_00001")
        with urlopen(req) as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as error:
            urlopen(req)
        self.assertEqual(error.exception.code, 401)

    def test_viewer_role_is_not_authorized(self):
        headers = signed_headers("GET", "/api/cloud-runners/status", "nonce_viewer_000001", role="viewer")
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base + "/api/cloud-runners/status", headers=headers))
        self.assertEqual(error.exception.code, 401)

    def test_mutation_requires_origin_and_csrf(self):
        session_req = self.request("GET", "/api/auth/session", "nonce_session_0002")
        with urlopen(session_req) as response:
            csrf = json.loads(response.read())["csrfToken"]
        body = {"repository": "phakphum12345/generated-A4-pdf"}
        headers = {"Content-Type": "application/json", "Origin": ORIGIN, "Idempotency-Key": "api-test-key-0001"}
        bad_csrf = self.request("POST", "/api/cloud-runners", "nonce_post_badcsrf_01", headers, body)
        with self.assertRaises(HTTPError) as error:
            urlopen(bad_csrf)
        self.assertEqual(error.exception.code, 403)
        headers["X-CSRF-Token"] = csrf
        headers["Origin"] = "https://attacker.example"
        bad_origin = self.request("POST", "/api/cloud-runners", "nonce_post_badorigin1", headers, body)
        with self.assertRaises(HTTPError) as error:
            urlopen(bad_origin)
        self.assertEqual(error.exception.code, 403)

    def test_valid_mutation_still_fails_closed_when_provisioning_disabled(self):
        session_req = self.request("GET", "/api/auth/session", "nonce_session_0003")
        with urlopen(session_req) as response:
            csrf = json.loads(response.read())["csrfToken"]
        payload = {
            "repository": "phakphum12345/generated-A4-pdf", "workflow_run_id": 123,
            "commit_sha": "a" * 40, "target_os": "linux",
            "image": "ubuntu-24.04-x64",
            "labels": ["self-hosted", "Linux", "X64", "dcp-cloud-linux"],
            "ephemeral": True, "max_runtime_minutes": 30,
            "network_policy": "restricted-egress",
            "registration_token_handling": "provider-side-only",
        }
        headers = {
            "Content-Type": "application/json", "Origin": ORIGIN,
            "X-CSRF-Token": csrf, "Idempotency-Key": "api-test-key-0002",
        }
        req = self.request("POST", "/api/cloud-runners", "nonce_post_safe_000001", headers, payload)
        with self.assertRaises(HTTPError) as error:
            urlopen(req)
        self.assertEqual(error.exception.code, 503)
        self.assertEqual(self.store.active_count(), 0)


if __name__ == "__main__":
    unittest.main()
