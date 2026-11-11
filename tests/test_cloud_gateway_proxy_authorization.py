"""HTTP authorization tests for owner-only cloud-runner mutations.

All requests target an ephemeral loopback server and use a local HMAC proxy
assertion. No GitHub or cloud provider endpoint is contacted.
"""
import hashlib
import hmac
import json
import secrets
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.cloud_gateway.policy import GatewaySettings
from tools.cloud_gateway.server import make_handler
from tools.cloud_gateway.service import GatewayService
from tools.cloud_gateway.store import RunnerStore


class NeverCalledProvider:
    def provision(self, payload):
        raise AssertionError("operator request reached provider provisioning")

    def status(self, runner_id):
        raise AssertionError("unexpected provider status request")

    def terminate(self, runner_id):
        raise AssertionError("operator request reached provider termination")


class ProxyMutationAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.secret = "local-test-proxy-secret-" + ("x" * 32)
        self.origin = "https://dcp.example.test"
        store = RunnerStore(str(Path(self.temp.name) / "gateway.sqlite"))
        service = GatewayService(GatewaySettings(), store, NeverCalledProvider())
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(
                service,
                token="unused-server-token",
                proxy_secret=self.secret,
                public_origin=self.origin,
            ),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.subject = "operator@example.test"
        self.session = "session_identifier_123"
        self.csrf = hmac.new(
            self.secret.encode(),
            ("csrf\n" + self.subject + "\n" + self.session).encode(),
            hashlib.sha256,
        ).hexdigest()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def headers(self, method, path, include_csrf=False):
        role = "operator"
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        canonical = "\n".join((
            method, path, self.subject, role, self.session, timestamp, nonce
        )).encode()
        signature = hmac.new(
            self.secret.encode(), canonical, hashlib.sha256
        ).hexdigest()
        result = {
            "X-DCP-User": self.subject,
            "X-DCP-Role": role,
            "X-DCP-Session": self.session,
            "X-DCP-Auth-Timestamp": timestamp,
            "X-DCP-Auth-Nonce": nonce,
            "X-DCP-Auth-Signature": signature,
        }
        if include_csrf:
            result["Origin"] = self.origin
            result["X-CSRF-Token"] = self.csrf
        return result

    def test_operator_can_read_session_but_cannot_create_runner(self):
        session_path = "/api/auth/session"
        request = Request(
            self.base + session_path,
            headers=self.headers("GET", session_path),
        )
        with urlopen(request) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read())["authenticated"])

        path = "/api/cloud-runners"
        request = Request(
            self.base + path,
            data=b"{}",
            method="POST",
            headers=self.headers("POST", path, include_csrf=True),
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        try:
            self.assertEqual(caught.exception.code, 403)
            self.assertEqual(
                json.loads(caught.exception.read())["error"], "owner role required"
            )
        finally:
            caught.exception.close()

    def test_operator_cannot_terminate_runner(self):
        path = "/api/cloud-runners/runner-123"
        request = Request(
            self.base + path,
            method="DELETE",
            headers=self.headers("DELETE", path, include_csrf=True),
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        try:
            self.assertEqual(caught.exception.code, 403)
            self.assertEqual(
                json.loads(caught.exception.read())["error"], "owner role required"
            )
        finally:
            caught.exception.close()


if __name__ == "__main__":
    unittest.main()
