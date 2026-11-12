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

import tools.local_auth_proxy as auth
from tools.local_auth_proxy import LocalAuthProxy, make_handler


class LocalProjectProxyRouteTests(unittest.TestCase):
    def setUp(self):
        self.gateway_requests = []
        self.gateway_methods = []
        self.gateway_bodies = []
        self.gateway_idempotency_keys = []
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

            def do_POST(self):
                parent.gateway_requests.append(self.path)
                parent.gateway_methods.append("POST")
                size = int(self.headers.get("Content-Length", "0"))
                parent.gateway_bodies.append(self.rfile.read(size))
                parent.gateway_idempotency_keys.append(self.headers.get("Idempotency-Key"))
                body = json.dumps({
                    "runner": {
                        "worker_id": self.path.split("/")[-2],
                        "state": self.path.rsplit("/", 1)[-1] + "d",
                    }
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_DELETE(self):
                parent.gateway_requests.append(self.path)
                parent.gateway_methods.append("DELETE")
                body = json.dumps({"deleted": True}).encode()
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
        self.old_local_port = auth.PORT
        auth.PORT = self.proxy.server_port
        self.origin = "http://127.0.0.1:" + str(self.proxy.server_port)
        self.base = self.origin

    def tearDown(self):
        self.proxy.shutdown()
        self.proxy.server_close()
        self.proxy_thread.join(timeout=2)
        self.gateway.shutdown()
        self.gateway.server_close()
        self.gateway_thread.join(timeout=2)
        self.temp.cleanup()
        auth.PORT = self.old_local_port

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

    def post(self, path, payload=None, authenticated=True, valid_csrf=True, idempotency_key=None):
        headers = {"Origin": self.origin, "Content-Type": "application/json"}
        if authenticated:
            headers["Cookie"] = "DCP_LOCAL_SESSION=" + self.sid
            headers["X-CSRF-Token"] = (
                self.app.csrf(self.session) if valid_csrf else "invalid-csrf-token"
            )
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        body = json.dumps({} if payload is None else payload).encode("utf-8")
        request = Request(self.base + path, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def delete(self, path, authenticated=True, valid_csrf=True):
        headers = {"Origin": self.origin}
        if authenticated:
            headers["Cookie"] = "DCP_LOCAL_SESSION=" + self.sid
            headers["X-CSRF-Token"] = (
                self.app.csrf(self.session) if valid_csrf else "invalid-csrf-token"
            )
        request = Request(self.base + path, headers=headers, method="DELETE")
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

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
            "/api/runners",
            "/api/terminal/templates",
            "/api/terminal/templates/custom-example/events",
            "/api/infrastructure",
            "/api/infrastructure?view=catalog",
            "/api/infrastructure/123e4567-e89b-42d3-a456-426614174000",
            "/api/infrastructure/123e4567-e89b-42d3-a456-426614174000/events",
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
            "/api/infrastructure?view=other",
            "/api/infrastructure?view=catalog&unexpected=1",
            "/api/infrastructure/123e4567-e89b-42d3-a456-426614174000/events?unexpected=1",
            "/api/infrastructure/not-a-uuid",
        ):
            status, body = self.get(path)
            self.assertEqual(status, 404, path)
            self.assertEqual(body["error"], "not found")
        self.assertEqual(len(self.gateway_requests), 0)

    def test_forwards_only_csrf_protected_local_runner_drain_and_enable(self):
        for action in ("drain", "enable"):
            path = "/api/runners/local-worker-1/" + action
            status, body = self.post(path, {})
            self.assertEqual(status, 200)
            self.assertEqual(body["runner"]["worker_id"], "local-worker-1")
            self.assertEqual(self.gateway_requests[-1], path)
            self.assertEqual(self.gateway_methods[-1], "POST")
            self.assertEqual(json.loads(self.gateway_bodies[-1]), {})

    def test_local_runner_controls_require_session_csrf_and_empty_payload(self):
        path = "/api/runners/local-worker-1/drain"
        status, _ = self.post(path, {}, authenticated=False)
        self.assertEqual(status, 403)
        status, _ = self.post(path, {}, valid_csrf=False)
        self.assertEqual(status, 403)
        status, _ = self.post(path, {"force": True})
        self.assertEqual(status, 400)
        status, _ = self.post("/api/runners/../drain", {})
        self.assertEqual(status, 404)
        self.assertEqual(len(self.gateway_requests), 0)

    def test_forwards_cloud_runner_create_idempotency_key(self):
        payload = {
            "repository": "example/project",
            "commit_sha": "a" * 40,
            "target_os": "linux",
            "workflow_run_id": 123,
            "max_runtime_minutes": 15,
        }
        status, _ = self.post(
            "/api/cloud-runners", payload,
            idempotency_key="cloud-runner-create-test-001",
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.gateway_requests[-1], "/api/cloud-runners")
        self.assertEqual(self.gateway_methods[-1], "POST")
        self.assertEqual(
            self.gateway_idempotency_keys[-1], "cloud-runner-create-test-001"
        )

    def test_forwards_csrf_protected_terminal_studio_actions(self):
        requests = (
            ("/api/terminal/commands/preview", {"template_id": "git.status", "parameters": {}}),
            ("/api/terminal/templates/import", {"pack_id": "fixture-pack", "templates": []}),
            (
                "/api/terminal/templates/custom-example/review",
                {"decision": "approve", "confirmation": "APPROVE", "source_sha256": "a" * 64},
            ),
        )
        for path, payload in requests:
            status, _ = self.post(path, payload)
            self.assertEqual(status, 200)
            self.assertEqual(self.gateway_requests[-1], path)
            self.assertEqual(self.gateway_methods[-1], "POST")
            self.assertEqual(json.loads(self.gateway_bodies[-1]), payload)

    def test_terminal_studio_mutations_require_session_csrf_and_exact_routes(self):
        path = "/api/terminal/commands/preview"
        status, _ = self.post(path, {}, authenticated=False)
        self.assertEqual(status, 403)
        status, _ = self.post(path, {}, valid_csrf=False)
        self.assertEqual(status, 403)
        status, _ = self.post("/api/terminal/templates/not-custom/review", {})
        self.assertEqual(status, 404)
        self.assertEqual(len(self.gateway_requests), 0)

    def test_forwards_fake_infrastructure_create_lifecycle_and_delete(self):
        create_path = "/api/infrastructure"
        payload = {
            "target_os": "linux",
            "image_id": "ubuntu-test",
            "template_id": "small-test",
            "provider_id": "fake",
        }
        status, _ = self.post(
            create_path, payload, idempotency_key="infra-create-test-0001"
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.gateway_requests[-1], create_path)
        self.assertEqual(self.gateway_methods[-1], "POST")
        self.assertEqual(json.loads(self.gateway_bodies[-1]), payload)
        self.assertEqual(
            self.gateway_idempotency_keys[-1], "infra-create-test-0001"
        )

        resource_id = "123e4567-e89b-42d3-a456-426614174000"
        for action in ("start", "stop", "restart"):
            action_path = "/api/infrastructure/" + resource_id + "/" + action
            status, _ = self.post(action_path, {})
            self.assertEqual(status, 200)
            self.assertEqual(self.gateway_requests[-1], action_path)
            self.assertEqual(json.loads(self.gateway_bodies[-1]), {})

        delete_path = "/api/infrastructure/" + resource_id
        status, result = self.delete(delete_path)
        self.assertEqual(status, 200)
        self.assertTrue(result["deleted"])
        self.assertEqual(self.gateway_requests[-1], delete_path)
        self.assertEqual(self.gateway_methods[-1], "DELETE")

    def test_infrastructure_mutations_require_session_csrf_and_exact_routes(self):
        create_path = "/api/infrastructure"
        payload = {"target_os": "linux", "image_id": "i", "template_id": "t", "provider_id": "fake"}
        status, _ = self.post(create_path, payload, authenticated=False)
        self.assertEqual(status, 403)
        status, _ = self.post(create_path, payload, valid_csrf=False)
        self.assertEqual(status, 403)
        status, _ = self.post(
            "/api/infrastructure/123e4567-e89b-42d3-a456-426614174000/unknown", {}
        )
        self.assertEqual(status, 404)
        status, _ = self.post(
            "/api/infrastructure/123e4567-e89b-42d3-a456-426614174000/start",
            {"force": True},
        )
        self.assertEqual(status, 400)
        status, _ = self.delete(
            "/api/infrastructure/123e4567-e89b-42d3-a456-426614174000",
            valid_csrf=False,
        )
        self.assertEqual(status, 403)
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
