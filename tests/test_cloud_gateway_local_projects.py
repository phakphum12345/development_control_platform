"""Owner-only Gateway API tests for Local Folder project metadata."""
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
from urllib.parse import urlparse

from tools.cloud_gateway.policy import GatewaySettings
from tools.cloud_gateway.server import make_handler
from tools.cloud_gateway.service import GatewayService
from tools.cloud_gateway.store import RunnerStore
from tools.local_runner_agent.local_project import LocalProjectRegistry


class LocalProjectGatewayAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        approved = base / "approved"
        project = approved / "demo"
        project.mkdir(parents=True)
        (project / "index.html").write_text("<h1>DCP</h1>\n", encoding="utf-8")
        registry = LocalProjectRegistry(base / "local-projects.json")
        root = registry.enroll_root(approved)
        self.project = registry.register_project(root["root_id"], project)
        self.secret = "local-project-api-secret-" + ("x" * 32)
        self.origin = "https://dcp.example.test"
        store = RunnerStore(str(base / "gateway.sqlite"))
        service = GatewayService(GatewaySettings(), store, object())
        service.local_project_registry = registry
        service.repository_authorizer = lambda repository: repository == "example/demo"
        service.repository_ref_catalog = lambda repository, kind: [
            {"name": kind + "-selected", "commit_sha": "a" * 40}
        ]
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

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, path, role="owner", method="GET"):
        subject = "dcp-owner@example.test"
        session = "local_project_session_123"
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        canonical = "\n".join((method, urlparse(path).path, subject, role, session, timestamp, nonce)).encode()
        signature = hmac.new(self.secret.encode(), canonical, hashlib.sha256).hexdigest()
        headers = {
            "X-DCP-User": subject,
            "X-DCP-Role": role,
            "X-DCP-Session": session,
            "X-DCP-Auth-Timestamp": timestamp,
            "X-DCP-Auth-Nonce": nonce,
            "X-DCP-Auth-Signature": signature,
        }
        if method != "GET":
            headers["Origin"] = self.origin
            headers["X-CSRF-Token"] = hmac.new(
                self.secret.encode(),
                ("csrf\n" + subject + "\n" + session).encode(),
                hashlib.sha256,
            ).hexdigest()
        request = Request(self.base + path, method=method, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def test_owner_can_list_roots_and_projects_without_host_absolute_paths(self):
        status, roots = self.request("/api/local-projects/roots")
        self.assertEqual(status, 200)
        self.assertEqual(roots["roots"][0]["label"], "approved")
        self.assertNotIn("path", roots["roots"][0])

        status, projects = self.request("/api/local-projects")
        self.assertEqual(status, 200)
        row = projects["projects"][0]
        self.assertEqual(row["project_id"], self.project["project_id"])
        self.assertEqual(row["relative_path"], "demo")
        self.assertEqual(row["snapshot_sha256"], self.project["snapshot_sha256"])
        self.assertNotIn("path", row)
        self.assertNotIn(str(Path(self.temp.name)), json.dumps(projects))

    def test_owner_can_read_one_project_by_id(self):
        status, result = self.request("/api/local-projects/" + self.project["project_id"])
        self.assertEqual(status, 200)
        self.assertEqual(result["project_id"], self.project["project_id"])

    def test_github_ref_kind_query_is_honored(self):
        status, result = self.request(
            "/api/github/repositories/example/demo/refs?kind=tags"
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["refs"][0]["name"], "tags-selected")

    def test_operator_cannot_read_github_app_project_catalog(self):
        status, result = self.request("/api/github/repositories", role="operator")
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "owner role required")

    def test_operator_cannot_read_local_filesystem_metadata(self):
        status, result = self.request("/api/local-projects", role="operator")
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "owner role required")

    def test_unknown_project_is_not_disclosed(self):
        status, result = self.request("/api/local-projects/00000000-0000-4000-8000-000000000000")
        self.assertEqual(status, 404)
        self.assertEqual(result["error"], "local project not found or invalid")

    def test_registry_changes_are_reloaded_without_gateway_restart(self):
        registry_path = Path(self.temp.name) / "local-projects.json"
        registry = LocalProjectRegistry(registry_path)
        root = registry.list_roots()[0]
        other = Path(self.temp.name) / "approved" / "second"
        other.mkdir()
        (other / "index.html").write_text("second", encoding="utf-8")
        registry.register_project(root["root_id"], other)
        status, projects = self.request("/api/local-projects")
        self.assertEqual(status, 200)
        self.assertEqual(len(projects["projects"]), 2)

    def test_local_project_api_is_read_only(self):
        status, result = self.request("/api/local-projects", method="POST")
        self.assertEqual(status, 404)
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
