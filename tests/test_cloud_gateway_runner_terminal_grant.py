"""Runner-authenticated Terminal grant verification API tests."""
import json
import tempfile
import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from types import SimpleNamespace

from tools.cloud_gateway.server import make_handler
from tools.cloud_gateway.terminal_grants import TerminalGrantStore


class _Jobs:
    def __init__(self, row):
        self.row = row

    def get(self, job_id):
        return self.row if self.row and self.row["id"] == job_id else None


class TerminalGrantRunnerAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.job_id = str(uuid.uuid4())
        self.project_id = str(uuid.uuid4())
        self.workspace_id = str(uuid.uuid4())
        self.worker = "runner-local"
        self.token = "runner-token-" + ("x" * 32)
        self.claims = {
            "subject": "owner@example.test",
            "session_id": "session_token_1234567890",
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "snapshot_sha256": "a" * 64,
            "template_id": "git_status",
            "template_digest": "b" * 64,
            "parameters_sha256": "c" * 64,
            "action": "terminal.read_only",
        }
        self.grants = TerminalGrantStore(base / "grants.sqlite3")
        self.grant = self.grants.issue(**self.claims, ttl_seconds=120)
        self.grants.reserve_job(self.grant["authorization_id"], job_id=self.job_id)
        self.grants.bind_job(
            self.grant["authorization_id"], job_id=self.job_id,
            worker_id=self.worker,
        )
        self.jobs = _Jobs({
            "id": self.job_id, "target": "terminal_script", "state": "running",
            "worker": self.worker,
            "lease_until": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
            "payload": {
                "source_type": "terminal_script",
                "project_id": self.project_id,
                "workspace_id": self.workspace_id,
                "snapshot_sha256": self.claims["snapshot_sha256"],
                "template_id": self.claims["template_id"],
                "template_digest": self.claims["template_digest"],
                "parameters_sha256": self.claims["parameters_sha256"],
                "authorization_id": self.grant["authorization_id"],
            },
        })
        service = SimpleNamespace(
            job_store=self.jobs,
            terminal_grant_store=self.grants,
        )
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(service, token="unused", runner_tokens={self.worker: self.token}),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, job_id=None, authorization_id=None, token=None):
        payload = {"authorization_id": authorization_id or self.grant["authorization_id"]}
        request = Request(
            self.base + "/v1/runner/" + (job_id or self.job_id) + "/terminal-grant",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer " + (token or self.token),
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def test_authenticated_runner_consumes_job_bound_grant(self):
        status, result = self.request()
        self.assertEqual(status, 200)
        self.assertTrue(result["grant"]["authorized"])
        self.assertEqual(result["grant"]["job_id"], self.job_id)

    def test_replay_is_rejected_after_first_consumption(self):
        self.assertEqual(self.request()[0], 200)
        status, result = self.request()
        self.assertEqual(status, 403)
        self.assertIn("not active", result["error"])

    def test_runner_cannot_verify_a_grant_for_another_job(self):
        other_job = str(uuid.uuid4())
        status, result = self.request(job_id=other_job)
        self.assertEqual(status, 409)
        self.assertIn("active Runner Job lease", result["error"])

    def test_wrong_runner_credential_is_rejected(self):
        status, result = self.request(token="wrong-runner-token-" + ("y" * 32))
        self.assertEqual(status, 401)
        self.assertIn("runner credentials", result["error"])

    def test_grant_reference_must_match_queued_job(self):
        status, result = self.request(authorization_id=str(uuid.uuid4()))
        self.assertEqual(status, 403)
        self.assertIn("does not match", result["error"])

    def test_expired_job_lease_is_rejected(self):
        self.jobs.row["lease_until"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        status, result = self.request()
        self.assertEqual(status, 409)
        self.assertIn("active Runner Job lease", result["error"])


if __name__ == "__main__":
    unittest.main()
