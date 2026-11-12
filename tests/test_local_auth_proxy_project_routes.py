"""Local Auth Proxy allowlist tests for owner-authenticated Local Folder reads."""
import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from tools.local_auth_proxy import LocalAuthProxy, make_handler


class LocalProjectProxyRouteTests(unittest.TestCase):
    def setUp(self):
        self.gateway_requests = []
        parent = self

        class FakeGateway(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):
                parent.gateway_requests.append(self.path)
                if self.path.endswith("/download"):
                    body = b"proxy-artifact\x00bytes"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Content-Disposition", "attachment; filename=web-build.zip")
                    self.send_header("ETag", '"' + hashlib.sha256(body).hexdigest() + '"')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                body = json.dumps({"projects": []}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.gateway = ThreadingHTTPServer(("127.0.0.1", 0), FakeGateway)
        self.gateway_thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
        self.gateway_thread.start()
        self.app = LocalAuthProxy(
            {"username": "owner", "password_hash": "unused"},
            "proxy-test-gateway-token",
            "proxy-test-hmac-secret-" + ("x" * 32),
            self.gateway.server_port,
        )
        self.sid, self.session = self.app.new_session(True)
        self.temp = tempfile.TemporaryDirectory()
        self.proxy = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(self.app, Path(self.temp.name)),
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

    def get(self, path, authenticated=True):
        headers = {}
        if authenticated:
            headers["Cookie"] = "DCP_LOCAL_SESSION=" + self.sid
        request = Request(self.base + path, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def test_allows_only_project_collection_root_and_uuid_reads(self):
        for path in (
            "/api/local-projects",
            "/api/local-projects/roots",
            "/api/local-projects/123e4567-e89b-42d3-a456-426614174000",
            "/api/github/repositories",
            "/api/github/repositories/example/demo/refs?kind=branches",
            "/api/github/repositories/example/demo/refs?kind=tags",
            "/api/github/repositories/example/demo/commits/" + ("a" * 40),
            "/api/github/repositories/example/demo/projects/" + ("b" * 40),
        ):
            status, _ = self.get(path)
            self.assertEqual(status, 200)
            self.assertEqual(self.gateway_requests[-1], path)

    def test_rejects_unapproved_project_api_paths(self):
        for path in (
            "/api/local-projects/not-a-project",
            "/api/github/repositories/example/demo/refs?kind=unknown",
            "/api/github/repositories/example/demo/refs?kind=tags&unexpected=1",
            "/api/local-projects?unexpected=1",
        ):
            status, body = self.get(path)
            self.assertEqual(status, 404)
            self.assertEqual(body["error"], "not found")
        self.assertEqual(len(self.gateway_requests), 0)

    def get_raw(self, path, authenticated=True):
        headers = {}
        if authenticated:
            headers["Cookie"] = "DCP_LOCAL_SESSION=" + self.sid
        request = Request(self.base + path, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except HTTPError as exc:
            try:
                return exc.code, exc.headers, exc.read()
            finally:
                exc.close()

    def test_artifact_download_streams_binary_bytes_and_sha256_headers(self):
        artifact_id = "223e4567-e89b-42d3-a456-426614174000"
        path = "/api/artifacts/" + artifact_id + "/download"
        status, headers, body = self.get_raw(path)
        expected = b"proxy-artifact\x00bytes"
        self.assertEqual(status, 200)
        self.assertEqual(body, expected)
        self.assertEqual(headers.get("Content-Type"), "application/octet-stream")
        self.assertEqual(headers.get("Content-Length"), str(len(expected)))
        self.assertEqual(
            headers.get("ETag"), '"' + hashlib.sha256(expected).hexdigest() + '"'
        )
        self.assertEqual(
            headers.get("Content-Disposition"),
            "attachment; filename=web-build.zip",
        )
        self.assertEqual(self.gateway_requests[-1], path)

    def test_artifact_download_requires_authenticated_session(self):
        artifact_id = "223e4567-e89b-42d3-a456-426614174000"
        status, _, body = self.get_raw(
            "/api/artifacts/" + artifact_id + "/download", authenticated=False
        )
        self.assertEqual(status, 401)
        self.assertIn(b"authenticated session required", body)
        self.assertEqual(len(self.gateway_requests), 0)

    def test_allows_bounded_dashboard_job_artifact_runner_and_terminal_reads(self):
        job_id = "123e4567-e89b-42d3-a456-426614174000"
        artifact_id = "223e4567-e89b-42d3-a456-426614174000"
        for path in (
            "/api/jobs",
            "/api/jobs?limit=25",
            "/api/jobs/" + job_id,
            "/api/jobs/" + job_id + "/artifacts",
            "/api/jobs/" + job_id + "/events",
            "/api/jobs/" + job_id + "/logs?after_id=0&limit=500",
            "/api/artifacts/" + artifact_id + "/download",
            "/api/runners",
            "/api/terminal/templates",
            "/api/terminal/templates/custom-example/events",
        ):
            status, _ = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(self.gateway_requests[-1], path)

    def test_rejects_unbounded_or_unapproved_dashboard_read_routes(self):
        job_id = "123e4567-e89b-42d3-a456-426614174000"
        for path in (
            "/api/jobs?limit=201",
            "/api/jobs?limit=25&unexpected=1",
            "/api/jobs?limit=25&limit=30",
            "/api/jobs/" + job_id + "/artifacts?unexpected=1",
            "/api/jobs/" + job_id + "/logs?after_id=-1&limit=500",
            "/api/jobs/not-a-uuid",
            "/api/artifacts/not-a-uuid/download",
            "/api/terminal/templates/not-custom/events",
            "/api/runners?unexpected=1",
        ):
            status, body = self.get(path)
            self.assertEqual(status, 404, path)
            self.assertEqual(body["error"], "not found")
        self.assertEqual(len(self.gateway_requests), 0)

    def test_dashboard_job_reads_require_authenticated_session(self):
        status, body = self.get("/api/jobs?limit=25", authenticated=False)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "authenticated session required")
        self.assertEqual(len(self.gateway_requests), 0)

    def test_requires_authenticated_owner_session(self):
        status, body = self.get("/api/local-projects", authenticated=False)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "authenticated session required")
        self.assertEqual(len(self.gateway_requests), 0)


if __name__ == "__main__":
    unittest.main()
