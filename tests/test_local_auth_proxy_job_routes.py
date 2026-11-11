"""Local Auth Proxy job API forwarding is owner-session and CSRF protected."""
import hashlib
import hmac
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.local_auth_proxy import LocalAuthProxy, make_handler


class LocalAuthProxyJobRouteTests(unittest.TestCase):
    def setUp(self):
        self.gateway_requests = []
        parent = self

        class FakeGateway(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_POST(self):
                size = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(size)
                parent.gateway_requests.append({
                    "path": self.path,
                    "body": json.loads(body) if body else None,
                    "idempotency_key": self.headers.get("Idempotency-Key"),
                    "csrf": self.headers.get("X-CSRF-Token"),
                })
                response = json.dumps({"job": "queued"}).encode()
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        self.gateway = ThreadingHTTPServer(("127.0.0.1", 0), FakeGateway)
        self.gateway_thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
        self.gateway_thread.start()
        self.secret = "job-proxy-test-secret-" + ("x" * 32)
        self.app = LocalAuthProxy(
            {"username": "owner", "password_hash": "unused"},
            "job-proxy-gateway-token",
            self.secret,
            self.gateway.server_port,
        )
        self.sid, self.session = self.app.new_session(True)
        self.csrf = hmac.new(
            self.secret.encode(),
            ("csrf\n" + self.session["username"] + "\n" + self.session["id"]).encode(),
            hashlib.sha256,
        ).hexdigest()
        self.temp = tempfile.TemporaryDirectory()
        self.proxy = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.app, Path(self.temp.name))
        )
        self.proxy_thread = threading.Thread(target=self.proxy.serve_forever, daemon=True)
        self.proxy_thread.start()
        self.base = "http://127.0.0.1:" + str(self.proxy.server_port)

    def tearDown(self):
        self.proxy.shutdown()
        self.proxy.server_close()
        self.proxy_thread.join(timeout=2)
        self.gateway.shutdown()
        self.gateway.server_close()
        self.gateway_thread.join(timeout=2)
        self.temp.cleanup()

    def post(self, path, *, authenticated=True, csrf=None, idempotency_key=None):
        body = json.dumps({
            "source_type": "local",
            "local_project_id": "123e4567-e89b-42d3-a456-426614174000",
            "snapshot_sha256": "a" * 64,
            "target": "test",
            "execution_approved": True,
        }).encode()
        headers = {
            "Origin": "http://127.0.0.1:8789",
            "Content-Type": "application/json",
        }
        if authenticated:
            headers["Cookie"] = "DCP_LOCAL_SESSION=" + self.sid
        if csrf is not None:
            headers["X-CSRF-Token"] = csrf
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(self.base + path, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def test_forwards_approved_job_create_and_idempotency_key(self):
        status, result = self.post(
            "/api/jobs", csrf=self.csrf, idempotency_key="local-job-key-0001"
        )
        self.assertEqual(status, 202)
        self.assertEqual(result["job"], "queued")
        self.assertEqual(len(self.gateway_requests), 1)
        forwarded = self.gateway_requests[0]
        self.assertEqual(forwarded["path"], "/api/jobs")
        self.assertEqual(forwarded["body"]["source_type"], "local")
        self.assertEqual(forwarded["body"]["execution_approved"], True)
        self.assertEqual(forwarded["idempotency_key"], "local-job-key-0001")
        self.assertEqual(forwarded["csrf"], self.csrf)

    def test_rejects_missing_session_or_invalid_csrf_before_gateway(self):
        status, _ = self.post("/api/jobs", authenticated=False, csrf=self.csrf)
        self.assertEqual(status, 403)
        status, _ = self.post("/api/jobs", csrf="invalid")
        self.assertEqual(status, 403)
        self.assertEqual(len(self.gateway_requests), 0)

    def test_rejects_arbitrary_post_paths(self):
        status, result = self.post("/api/local-projects", csrf=self.csrf)
        self.assertEqual(status, 404)
        self.assertEqual(result["error"], "not found")
        self.assertEqual(len(self.gateway_requests), 0)

    def test_rejects_invalid_idempotency_key_before_gateway(self):
        status, result = self.post("/api/jobs", csrf=self.csrf, idempotency_key="bad")
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "Invalid Idempotency-Key")
        self.assertEqual(len(self.gateway_requests), 0)


if __name__ == "__main__":
    unittest.main()
