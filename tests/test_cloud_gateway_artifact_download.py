"""Gateway HTTP acceptance for authenticated, SHA-256-verified artifact downloads."""
import hashlib
import hmac
import io
import secrets
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from tools.cloud_gateway.artifacts import ArtifactStore
from tools.cloud_gateway.job_control import JobStore
from tools.cloud_gateway.policy import GatewaySettings
from tools.cloud_gateway.server import make_handler
from tools.cloud_gateway.service import GatewayService
from tools.cloud_gateway.store import RunnerStore


class ArtifactDownloadGatewayAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.secret = "artifact-download-test-secret-" + ("x" * 32)
        self.origin = "https://dcp.example.test"
        self.jobs = JobStore(root / "jobs.sqlite3")
        self.artifacts = ArtifactStore(root / "artifacts")
        self.job, _ = self.jobs.create(
            {"repository": "example/project", "commit_sha": "a" * 40,
             "target": "build_static_web"},
            "artifact-download-job-0001",
        )
        claimed = self.jobs.claim("artifact-download-runner")
        self.assertEqual(claimed["id"], self.job["id"])
        service = GatewayService(
            GatewaySettings(), RunnerStore(str(root / "gateway.sqlite3")), object()
        )
        service.job_store = self.jobs
        service.artifact_store = self.artifacts
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

    def upload_artifact(self, payload=b"verified-build-artifact"):
        return self.artifacts.store(
            self.jobs, self.job["id"], "artifact-download-runner",
            "web-build.zip", io.BytesIO(payload), len(payload),
        )

    def request_download(self, path, role="owner", authenticated=True):
        headers = {}
        if authenticated:
            subject = "dcp-owner@example.test"
            session = "artifact_download_session_123"
            timestamp = str(int(time.time()))
            nonce = secrets.token_urlsafe(24)
            canonical = "\\n".join(
                ("GET", urlparse(path).path, subject, role, session, timestamp, nonce)
            ).encode("utf-8")
            signature = hmac.new(
                self.secret.encode("utf-8"), canonical, hashlib.sha256
            ).hexdigest()
            headers.update({
                "X-DCP-User": subject,
                "X-DCP-Role": role,
                "X-DCP-Session": session,
                "X-DCP-Auth-Timestamp": timestamp,
                "X-DCP-Auth-Nonce": nonce,
                "X-DCP-Auth-Signature": signature,
            })
        request = Request(self.base + path, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except HTTPError as exc:
            try:
                return exc.code, exc.headers, exc.read()
            finally:
                exc.close()

    def test_owner_download_returns_exact_bytes_and_sha256_etag(self):
        payload = b"real-build-artifact\\x00with-binary-content"
        metadata = self.upload_artifact(payload)
        status, headers, body = self.request_download(
            "/api/artifacts/" + metadata["id"] + "/download"
        )
        expected_sha = hashlib.sha256(payload).hexdigest()
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)
        self.assertEqual(headers.get("ETag"), '"' + expected_sha + '"')
        self.assertEqual(headers.get("Content-Length"), str(len(payload)))
        self.assertIn("web-build.zip", headers.get("Content-Disposition", ""))

    def test_unauthenticated_download_is_denied(self):
        metadata = self.upload_artifact()
        status, _, body = self.request_download(
            "/api/artifacts/" + metadata["id"] + "/download",
            authenticated=False,
        )
        self.assertEqual(status, 401)
        self.assertIn(b"authenticated dashboard session required", body)

    def test_viewer_role_cannot_download_artifact(self):
        metadata = self.upload_artifact()
        status, _, _ = self.request_download(
            "/api/artifacts/" + metadata["id"] + "/download", role="viewer"
        )
        self.assertEqual(status, 401)

    def test_tampered_artifact_is_not_downloaded(self):
        metadata = self.upload_artifact()
        _, blob = self.artifacts.get(metadata["id"])
        blob.write_bytes(b"tampered-after-upload")
        status, _, body = self.request_download(
            "/api/artifacts/" + metadata["id"] + "/download"
        )
        self.assertEqual(status, 404)
        self.assertIn(b"artifact not found", body)


if __name__ == "__main__":
    unittest.main()
