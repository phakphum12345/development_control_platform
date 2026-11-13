"""Owner-only Gateway API tests for Local Folder project metadata."""
import hashlib
import hmac
import json
import secrets
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from tools.cloud_gateway.policy import GatewaySettings
from tools.cloud_gateway.job_control import JobStore
from tools.cloud_gateway.server import make_handler
from tools.cloud_gateway.service import GatewayService
from tools.cloud_gateway.store import RunnerStore
from tools.cloud_gateway.terminal_grants import TerminalGrantStore
from tools.cloud_gateway.terminal_catalog import preview_template
from tools.cloud_gateway.terminal_execution_contract import template_version_digest
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
        self.service = service
        service.local_project_registry = registry
        service.job_store = JobStore(base / "jobs.sqlite3")
        service.terminal_grant_store = TerminalGrantStore(base / "terminal-grants.sqlite3")
        service.repository_catalog = lambda: []
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

    def request(self, path, role="owner", method="GET", payload=None, idempotency_key=None, origin=None, csrf=True):
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
            headers["Origin"] = self.origin if origin is None else origin
            if csrf:
                headers["X-CSRF-Token"] = hmac.new(
                    self.secret.encode(),
                    ("csrf\n" + subject + "\n" + session).encode(),
                    hashlib.sha256,
                ).hexdigest()
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(self.base + path, data=body, method=method, headers=headers)
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
        self.assertEqual(row["workspace_id"], self.project["workspace_id"])
        self.assertEqual(row["relative_path"], "demo")
        self.assertEqual(row["snapshot_sha256"], self.project["snapshot_sha256"])
        self.assertNotIn("path", row)
        self.assertNotIn(str(Path(self.temp.name)), json.dumps(projects))

    def test_local_project_list_includes_bounded_framework_detection_without_host_path(self):
        status, projects = self.request("/api/local-projects")
        self.assertEqual(status, 200)
        row = projects["projects"][0]
        self.assertEqual(row["framework_detection"]["framework"], "Static HTML/CSS/JS")
        self.assertEqual(row["framework_detection"]["project_type"], "web")
        self.assertNotIn("workspace", row)
        self.assertNotIn("path", row)

    def _issue_terminal_test_grant(self, *, session="local_project_session_123"):
        parameters = {}
        template = preview_template("git_status", parameters)
        template["execution_enabled"] = True
        with patch("tools.cloud_gateway.terminal_execution_contract.preview_template", return_value=template):
            digest = template_version_digest("git_status", parameters)
        grant = self.service.terminal_grant_store.issue(
            subject="dcp-owner@example.test", session_id=session,
            project_id=self.project["project_id"],
            workspace_id=self.project["workspace_id"],
            snapshot_sha256=self.project["snapshot_sha256"],
            template_id="git_status", template_digest=digest,
            parameters_sha256=self.service.terminal_grant_store.parameters_digest(
                template["parameter_values"]
            ),
        )
        return grant, template, digest

    def test_terminal_catalog_and_preview_report_enabled_gate_from_trusted_template(self):
        enabled = preview_template("git_status", {})
        enabled["execution_enabled"] = True
        enabled["status"] = "EXECUTION_ENABLED"
        with patch(
            "tools.cloud_gateway.server.list_terminal_templates",
            return_value=[enabled],
        ):
            status, catalog = self.request("/api/terminal/templates")
        self.assertEqual(status, 200)
        self.assertTrue(catalog["execution_enabled"])

        with patch(
            "tools.cloud_gateway.server.preview_terminal_template",
            return_value=enabled,
        ):
            status, preview = self.request(
                "/api/terminal/commands/preview", method="POST",
                payload={"template_id": "git_status", "parameters": {}},
            )
        self.assertEqual(status, 200)
        self.assertTrue(preview["execution_enabled"])
        self.assertEqual(preview["preview"]["status"], "EXECUTION_ENABLED")

    def test_unused_terminal_grant_can_be_revoked_through_owner_api(self):
        grant, _, _ = self._issue_terminal_test_grant()
        status, result = self.request(
            "/api/terminal/grants/" + grant["authorization_id"] + "/revoke",
            method="POST",
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["revoked"])
        with self.service.terminal_grant_store.db() as db:
            row = db.execute(
                "SELECT revoked_at,consumed_at FROM terminal_grants WHERE grant_id=?",
                (grant["authorization_id"],),
            ).fetchone()
        self.assertIsNotNone(row["revoked_at"])
        self.assertIsNone(row["consumed_at"])

    def test_terminal_job_is_created_only_with_matching_app_grant(self):
        grant, enabled_template, digest = self._issue_terminal_test_grant()
        payload = {
            "project_id": self.project["project_id"],
            "workspace_id": self.project["workspace_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "template_id": "git_status",
            "parameters": {},
            "authorization_id": grant["authorization_id"],
        }
        with patch("tools.cloud_gateway.terminal_execution_contract.preview_template", return_value=enabled_template), \
             patch("tools.cloud_gateway.job_control.preview_template", return_value=enabled_template):
            status, job = self.request(
                "/api/terminal/jobs", method="POST", payload=payload,
                idempotency_key="terminal-job-created-0001",
            )
        self.assertEqual(status, 202)
        self.assertEqual(job["source_type"], "terminal_script")
        self.assertEqual(job["max_attempts"], 1)
        self.assertEqual(job["target"], "terminal_script")
        self.assertEqual(job["terminal"]["project_id"], self.project["project_id"])
        self.assertEqual(job["terminal"]["workspace_id"], self.project["workspace_id"])
        self.assertEqual(job["terminal"]["template_id"], "git_status")
        self.assertEqual(job["terminal"]["authorization_id"], grant["authorization_id"])
        with self.service.terminal_grant_store.db() as db:
            row = db.execute(
                "SELECT job_id,worker_id FROM terminal_grants WHERE grant_id=?",
                (grant["authorization_id"],),
            ).fetchone()
        self.assertEqual(row["job_id"], job["id"])
        self.assertIsNone(row["worker_id"])

    def test_terminal_job_rejects_grant_from_another_session(self):
        grant, enabled_template, _ = self._issue_terminal_test_grant(session="another_session_token_123")
        payload = {
            "project_id": self.project["project_id"],
            "workspace_id": self.project["workspace_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "template_id": "git_status",
            "parameters": {},
            "authorization_id": grant["authorization_id"],
        }
        with patch("tools.cloud_gateway.terminal_execution_contract.preview_template", return_value=enabled_template), \
             patch("tools.cloud_gateway.job_control.preview_template", return_value=enabled_template):
            status, result = self.request(
                "/api/terminal/jobs", method="POST", payload=payload,
                idempotency_key="terminal-job-session-mismatch",
            )
        self.assertEqual(status, 403)
        self.assertIn("scope", result["error"])

    def test_terminal_grant_cannot_be_reserved_to_two_different_jobs(self):
        grant, enabled_template, _ = self._issue_terminal_test_grant()
        payload = {
            "project_id": self.project["project_id"],
            "workspace_id": self.project["workspace_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "template_id": "git_status",
            "parameters": {},
            "authorization_id": grant["authorization_id"],
        }
        with patch("tools.cloud_gateway.terminal_execution_contract.preview_template", return_value=enabled_template), \
             patch("tools.cloud_gateway.job_control.preview_template", return_value=enabled_template):
            first_status, first = self.request(
                "/api/terminal/jobs", method="POST", payload=payload,
                idempotency_key="terminal-job-reserve-first",
            )
            second_status, second = self.request(
                "/api/terminal/jobs", method="POST", payload=payload,
                idempotency_key="terminal-job-reserve-second",
            )
        self.assertEqual(first_status, 202)
        self.assertEqual(second_status, 403)
        rows = self.service.job_store.list_recent(10)
        terminal_rows = [row for row in rows if row["target"] == "terminal_script"]
        self.assertEqual(len(terminal_rows), 1)
        self.assertEqual(terminal_rows[0]["id"], first["id"])
        self.assertEqual(terminal_rows[0]["state"], "queued")

    def test_terminal_job_submission_is_idempotent_after_grant_reservation(self):
        grant, enabled_template, _ = self._issue_terminal_test_grant()
        payload = {
            "project_id": self.project["project_id"],
            "workspace_id": self.project["workspace_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "template_id": "git_status",
            "parameters": {},
            "authorization_id": grant["authorization_id"],
        }
        with patch("tools.cloud_gateway.terminal_execution_contract.preview_template", return_value=enabled_template), \
             patch("tools.cloud_gateway.job_control.preview_template", return_value=enabled_template):
            first_status, first = self.request(
                "/api/terminal/jobs", method="POST", payload=payload,
                idempotency_key="terminal-job-idempotent-001",
            )
            retry_status, retry = self.request(
                "/api/terminal/jobs", method="POST", payload=payload,
                idempotency_key="terminal-job-idempotent-001",
            )
        self.assertEqual(first_status, 202)
        self.assertEqual(retry_status, 200)
        self.assertEqual(first["id"], retry["id"])
        self.assertTrue(first["created"])
        self.assertFalse(retry["created"])
        rows = [row for row in self.service.job_store.list_recent(10)
                if row["target"] == "terminal_script"]
        self.assertEqual(len(rows), 1)

    def test_terminal_authorization_endpoint_fails_closed_while_templates_are_disabled(self):
        payload = {
            "project_id": self.project["project_id"],
            "workspace_id": self.project["workspace_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "template_id": "git_status",
            "parameters": {},
        }
        status, result = self.request(
            "/api/terminal/authorize", method="POST", payload=payload
        )
        self.assertEqual(status, 409)
        self.assertIn("not enabled", result["error"])
        with self.service.terminal_grant_store.db() as db:
            count = db.execute("SELECT count(*) FROM terminal_grants").fetchone()[0]
        self.assertEqual(count, 0)

    def test_terminal_authorization_endpoint_is_owner_only(self):
        payload = {
            "project_id": self.project["project_id"],
            "workspace_id": self.project["workspace_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "template_id": "git_status",
            "parameters": {},
        }
        status, result = self.request(
            "/api/terminal/authorize", role="operator", method="POST", payload=payload
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "owner role required")

    def test_terminal_authorization_endpoint_requires_same_origin_and_csrf(self):
        payload = {
            "project_id": self.project["project_id"],
            "workspace_id": self.project["workspace_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "template_id": "git_status",
            "parameters": {},
        }
        status, result = self.request(
            "/api/terminal/authorize", method="POST", payload=payload,
            origin="https://attacker.example.test",
        )
        self.assertEqual(status, 403)
        self.assertIn("same-origin", result["error"])
        status, result = self.request(
            "/api/terminal/authorize", method="POST", payload=payload, csrf=False,
        )
        self.assertEqual(status, 403)
        self.assertIn("CSRF", result["error"])

    def test_terminal_authorization_endpoint_rejects_browser_shell_fields(self):
        payload = {
            "project_id": self.project["project_id"],
            "workspace_id": self.project["workspace_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "template_id": "git_status",
            "parameters": {},
            "shell": "whoami",
        }
        status, result = self.request(
            "/api/terminal/authorize", method="POST", payload=payload
        )
        self.assertEqual(status, 409)
        self.assertIn("fields are invalid", result["error"])

    def test_owner_can_queue_job_bound_to_current_local_snapshot(self):
        payload = {
            "source_type": "local_folder",
            "project_id": self.project["project_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "target": "build_static_web",
        }
        status, job = self.request(
            "/api/jobs", method="POST", payload=payload,
            idempotency_key="local-project-job-0001",
        )
        self.assertEqual(status, 202)
        self.assertEqual(job["source_type"], "local_folder")
        self.assertEqual(job["source_id"], self.project["project_id"])
        self.assertEqual(job["source_sha256"], self.project["snapshot_sha256"])
        self.assertIsNone(job["repository"])
        self.assertIsNone(job["commit_sha"])
        self.assertEqual(job["state"], "queued")
        self.assertNotIn(str(Path(self.temp.name)), json.dumps(job))

    def test_local_job_requires_owner_and_detected_matching_target(self):
        payload = {
            "source_type": "local_folder",
            "project_id": self.project["project_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "target": "build_static_web",
        }
        status, _ = self.request(
            "/api/jobs", role="operator", method="POST", payload=payload,
            idempotency_key="local-project-job-0002",
        )
        self.assertEqual(status, 403)
        invalid_target = {**payload, "target": "build_vite"}
        status, _ = self.request(
            "/api/jobs", method="POST", payload=invalid_target,
            idempotency_key="local-project-job-0003",
        )
        self.assertEqual(status, 400)

    def test_changed_local_project_requires_refresh_before_queue(self):
        payload = {
            "source_type": "local_folder",
            "project_id": self.project["project_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "target": "build_static_web",
        }
        (Path(self.temp.name) / "approved" / "demo" / "index.html").write_text(
            "<h1>changed</h1>", encoding="utf-8"
        )
        status, response = self.request(
            "/api/jobs", method="POST", payload=payload,
            idempotency_key="local-project-job-0004",
        )
        self.assertEqual(status, 409)
        self.assertEqual(len(response["current_snapshot_sha256"]), 64)
        self.assertEqual(self.service.job_store.list_recent(), [])

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

    def test_operator_can_read_github_app_project_catalog(self):
        status, result = self.request("/api/github/repositories", role="operator")
        self.assertEqual(status, 200)
        self.assertEqual(result["repositories"], [])

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
