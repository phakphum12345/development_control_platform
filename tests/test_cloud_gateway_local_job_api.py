"""Gateway API tests for owner-approved Local Flutter job queueing."""
import hashlib
import hmac
import json
import secrets
import tempfile
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.cloud_gateway.job_control import JobStore
from tools.cloud_gateway.policy import GatewaySettings
from tools.cloud_gateway.server import make_handler
from tools.cloud_gateway.store import RunnerStore
from tools.local_runner_agent.local_project import LocalProjectRegistry


class _Service:
    def __init__(self, jobs, nonce_store, registry):
        self.job_store = jobs
        self.store = nonce_store
        self.local_project_registry = registry
        self.settings = GatewaySettings()
        self.runner_registry = None


class LocalProjectJobAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.approved = self.base / "approved"
        self.flutter = self.approved / "flutter-app"
        self.flutter.mkdir(parents=True)
        (self.flutter / "pubspec.yaml").write_text("name: fixture_app\n", encoding="utf-8")
        (self.flutter / "lib").mkdir()
        (self.flutter / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
        self.registry = LocalProjectRegistry(self.base / "local-projects.json")
        root = self.registry.enroll_root(self.approved)
        self.project = self.registry.register_project(root["root_id"], self.flutter)
        self.jobs = JobStore(str(self.base / "jobs.sqlite"))
        self.nonces = RunnerStore(str(self.base / "nonces.sqlite"))
        self.secret = "local-project-job-api-secret-" + ("x" * 32)
        self.origin = "https://dcp.example.test"
        service = _Service(self.jobs, self.nonces, self.registry)
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(
                service, token="unused-runner-token",
                proxy_secret=self.secret, public_origin=self.origin,
            ),
        )
        import threading
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, payload, *, role="owner", key="local-job-key-0001"):
        path = "/api/jobs"
        subject = "dcp-owner@example.test"
        session = "local_project_job_session"
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        canonical = "\n".join(("POST", path, subject, role, session, timestamp, nonce)).encode()
        signature = hmac.new(self.secret.encode(), canonical, hashlib.sha256).hexdigest()
        csrf = hmac.new(
            self.secret.encode(), ("csrf\n" + subject + "\n" + session).encode(),
            hashlib.sha256,
        ).hexdigest()
        body = json.dumps(payload).encode()
        request = Request(self.base_url + path, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "Origin": self.origin,
            "Idempotency-Key": key,
            "X-CSRF-Token": csrf,
            "X-DCP-User": subject,
            "X-DCP-Role": role,
            "X-DCP-Session": session,
            "X-DCP-Auth-Timestamp": timestamp,
            "X-DCP-Auth-Nonce": nonce,
            "X-DCP-Auth-Signature": signature,
        })
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def payload(self, **overrides):
        value = {
            "source_type": "local",
            "local_project_id": self.project["project_id"],
            "snapshot_sha256": self.project["snapshot_sha256"],
            "target": "test",
            "execution_approved": True,
        }
        value.update(overrides)
        return value

    def test_owner_can_queue_only_current_explicitly_approved_flutter_snapshot(self):
        status, job = self.request(self.payload())
        self.assertEqual(status, 202)
        self.assertEqual(job["source_type"], "local")
        self.assertEqual(job["local_project_id"], self.project["project_id"])
        self.assertEqual(job["snapshot_sha256"], self.project["snapshot_sha256"])
        self.assertTrue(job["execution_approved"])
        self.assertIsNone(job["repository"])
        self.assertIsNone(job["commit_sha"])
        self.assertEqual(job["state"], "queued")

    def test_idempotency_returns_existing_local_job(self):
        status, first = self.request(self.payload(), key="local-job-idem-0001")
        status_again, again = self.request(self.payload(), key="local-job-idem-0001")
        self.assertEqual(status, 202)
        self.assertEqual(status_again, 200)
        self.assertEqual(first["id"], again["id"])

    def test_operator_cannot_queue_local_source_execution(self):
        status, result = self.request(self.payload(), role="operator")
        self.assertEqual(status, 403)
        self.assertIn("Owner role", result["error"])

    def test_local_job_requires_explicit_execution_approval(self):
        status, result = self.request(self.payload(execution_approved=False))
        self.assertEqual(status, 403)
        self.assertIn("approval", result["error"])

    def test_stale_source_fingerprint_is_rejected(self):
        (self.flutter / "pubspec.yaml").write_text("name: changed\n", encoding="utf-8")
        status, result = self.request(self.payload())
        self.assertEqual(status, 409)
        self.assertIn("stale", result["error"])

    def test_non_flutter_local_project_is_not_queued_for_flutter_runner(self):
        web = self.approved / "web-only"
        web.mkdir()
        (web / "index.html").write_text("<h1>web</h1>", encoding="utf-8")
        web_project = self.registry.register_project(self.project["root_id"], web)
        payload = self.payload(local_project_id=web_project["project_id"],
                               snapshot_sha256=web_project["snapshot_sha256"])
        status, result = self.request(payload)
        self.assertEqual(status, 400)
        self.assertIn("Flutter", result["error"])


if __name__ == "__main__":
    unittest.main()
