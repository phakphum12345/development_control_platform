"""Local Runner Agent configuration and HTTP client tests; no commands are executed."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.local_runner_agent.client import (
    GatewayClient, RunnerAgentConfig, RunnerGatewayError,
)


TOKEN = "local-runner-test-token-that-is-at-least-32-bytes-long"
JOB_ID = "123e4567-e89b-42d3-a456-426614174000"


class FakeGatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.server.requests.append((self.command, self.path, self.headers.get("Authorization")))
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://redirect.example.test/collect")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send(200, {"status": "ok", "provisioning_enabled": False})

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size).decode())
        self.server.requests.append((self.command, self.path, self.headers.get("Authorization"), payload))
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send(401, {"error": "unauthorized"})
        if self.path in ("/v1/runner/enroll", "/v1/runner/register"):
            state = "offline" if self.path.endswith("/enroll") else "online"
            return self._send(200, {"runner": {
                "worker_id": "local-worker-01",
                "host_os": payload.get("host_os", "linux"),
                "capabilities": payload.get("capabilities", ["flutter", "linux"]),
                "state": state,
            }})
        if self.path == "/v1/runner/claim":
            return self._send(200, {"job": {"id": JOB_ID, "state": "running"}})
        if self.path.endswith("/checkpoint"):
            self.server.checkpoint_requests += 1
            if self.server.checkpoint_requests == 1:
                return self._send(503, {"error": "temporary"})
            return self._send(200, {
                "id": JOB_ID, "state": "running",
                "checkpoint_seq": payload.get("sequence"),
                "checkpoint": payload.get("checkpoint"),
            })
        if self.path.endswith("/logs"):
            return self._send(202, {"accepted": True})
        return self._send(200, {"id": JOB_ID, "state": "running"})


class RunnerAgentTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGatewayHandler)
        self.server.requests = []
        self.server.checkpoint_requests = 0
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = RunnerAgentConfig(
            f"http://127.0.0.1:{self.server.server_port}",
            "local-worker-01",
            TOKEN,
        )
        self.client = GatewayClient(self.config)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_config_requires_secure_remote_origin_and_strong_worker_credential(self):
        with self.assertRaises(ValueError):
            RunnerAgentConfig("http://gateway.example.test", "worker-1", TOKEN)
        with self.assertRaises(ValueError):
            RunnerAgentConfig("https://gateway.example.test", "../worker", TOKEN)
        with self.assertRaises(ValueError):
            RunnerAgentConfig("https://gateway.example.test", "worker-1", "short")

    def test_from_env_reads_values_without_exposing_token_in_repr(self):
        config = RunnerAgentConfig.from_env({
            "DCP_GATEWAY_URL": "https://gateway.example.test",
            "DCP_RUNNER_WORKER_ID": "worker-02",
            "DCP_RUNNER_TOKEN": TOKEN,
            "DCP_RUNNER_TIMEOUT_SECONDS": "15",
        })
        self.assertEqual(config.timeout_seconds, 15)
        self.assertNotIn(TOKEN, repr(config))

    def test_health_check_does_not_send_runner_token(self):
        result = self.client.health()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(self.server.requests[-1], ("GET", "/healthz", None))

    def test_offline_enrollment_uses_dedicated_token_and_never_claims(self):
        runner = self.client.enroll("windows", ["flutter", "windows"])
        self.assertEqual(runner["worker_id"], "local-worker-01")
        self.assertEqual(runner["state"], "offline")
        request = self.server.requests[-1]
        self.assertEqual(request[0], "POST")
        self.assertEqual(request[1], "/v1/runner/enroll")
        self.assertEqual(request[2], "Bearer " + TOKEN)
        self.assertEqual(request[3]["host_os"], "windows")

    def test_runner_client_calls_claim_heartbeat_logs_and_finish_with_dedicated_token(self):
        job = self.client.claim(lease_seconds=60)
        self.assertEqual(job["id"], JOB_ID)
        heartbeat = self.client.heartbeat(JOB_ID, lease_seconds=45)
        self.assertEqual(heartbeat["state"], "running")
        checkpoint = {
            "version": 1, "step": "workspace-ready",
            "safe_to_resume": True, "data": {"source_sha256": "a" * 64},
        }
        saved = self.client.checkpoint(JOB_ID, 1, checkpoint)
        self.assertEqual(saved["checkpoint_seq"], 1)
        self.assertEqual(saved["checkpoint"], checkpoint)
        self.assertEqual(self.server.checkpoint_requests, 2)
        logged = self.client.append_log(JOB_ID, "agent connected", "system")
        self.assertTrue(logged["accepted"])
        finished = self.client.finish(
            JOB_ID, "failed", {"dry_run": True}, "EXECUTION_DISABLED"
        )
        self.assertEqual(finished["state"], "running")
        for request in self.server.requests[1:]:
            self.assertEqual(request[2], "Bearer " + TOKEN)

    def test_client_rejects_invalid_job_ids_leases_logs_and_outcomes(self):
        with self.assertRaises(ValueError):
            self.client.heartbeat("../job", 30)
        with self.assertRaises(ValueError):
            self.client.claim(lease_seconds=True)
        with self.assertRaises(ValueError):
            self.client.checkpoint(JOB_ID, 0, {})
        with self.assertRaises(ValueError):
            self.client.checkpoint("../job", 1, {})
        with self.assertRaises(ValueError):
            self.client.append_log(JOB_ID, "")
        with self.assertRaises(ValueError):
            self.client.append_log(JOB_ID, "hello", "trace")
        with self.assertRaises(ValueError):
            self.client.finish(JOB_ID, "unknown")

    def test_runner_credentials_are_not_forwarded_across_redirects(self):
        with self.assertRaises(RunnerGatewayError) as error:
            self.client._request("GET", "/redirect")
        self.assertEqual(error.exception.status_code, 302)
        self.assertEqual(self.server.requests[-1], ("GET", "/redirect", "Bearer " + TOKEN))

    def test_gateway_http_errors_are_sanitized(self):
        request = Request(
            self.client.base_url + "/v1/runner/claim",
            data=b'{"lease_seconds":30}',
            headers={"Authorization": "Bearer wrong-token"},
            method="POST",
        )
        bad_config = RunnerAgentConfig(
            self.config.gateway_url, self.config.worker_id, "x" * 32
        )
        with self.assertRaises(RunnerGatewayError) as error:
            GatewayClient(bad_config)._request(
                "POST", "/v1/runner/claim", {"lease_seconds": 30}
            )
        self.assertEqual(error.exception.status_code, 401)
        with self.assertRaises(HTTPError):
            urlopen(request)


if __name__ == "__main__":
    unittest.main()
