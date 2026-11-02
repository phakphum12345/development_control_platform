"""Safety and contract tests for the DCP macOS cloud runner backend."""
import json
import unittest
from urllib.error import HTTPError

from tools.cloud_runner.backend import (
    ProvisionRequest, RunnerSettings, request_provisioning,
)


class RunnerBackendTests(unittest.TestCase):
    def setUp(self):
        self.settings = RunnerSettings(
            endpoint="https://provider.example.test/provision",
            bearer_token="test-token",
        )
        self.request = ProvisionRequest(
            repository="phakphum12345/generated-A4-pdf",
            commit_sha="a" * 40,
            ref="refs/heads/main",
            workflow_run_id=100,
        )

    def test_payload_is_ephemeral_one_job_and_repository_scoped(self):
        payload = self.request.payload(self.settings)
        self.assertEqual(payload["contract"], "dcp.macos-runner-provision.v1")
        self.assertTrue(payload["runner"]["ephemeral"])
        self.assertEqual(payload["runner"]["max_jobs"], 1)
        self.assertEqual(payload["repository"], "phakphum12345/generated-A4-pdf")
        self.assertTrue(payload["safety"]["one_job_then_destroy"])

    def test_rejects_repository_outside_allowlist(self):
        request = ProvisionRequest("attacker/repo", "a" * 40, "refs/heads/main", 100)
        with self.assertRaisesRegex(ValueError, "allowlist"):
            request.payload(self.settings)

    def test_rejects_short_sha_and_invalid_run_id(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            ProvisionRequest(self.request.repository, "abc", "main", 100).payload(self.settings)
        with self.assertRaisesRegex(ValueError, "positive"):
            ProvisionRequest(self.request.repository, "a" * 40, "main", 0).payload(self.settings)

    def test_settings_require_https_and_secret(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            RunnerSettings("http://provider.example.test", "token")
        with self.assertRaisesRegex(ValueError, "bearer token"):
            RunnerSettings("https://provider.example.test", " ")

    def test_from_env_parses_json_allowlist_and_labels(self):
        settings = RunnerSettings.from_env({
            "DCP_RUNNER_PROVIDER_URL": "https://provider.example.test/provision",
            "DCP_RUNNER_PROVIDER_TOKEN": "secret",
            "DCP_RUNNER_ALLOWED_REPOSITORIES": '["owner/repo"]',
            "DCP_MACOS_RUNNER_LABELS": '["self-hosted","macOS","ARM64"]',
        })
        self.assertEqual(settings.allowed_repositories, ("owner/repo",))
        self.assertEqual(settings.labels[-1], "ARM64")
        self.assertNotIn("secret", repr(settings))

    def test_dispatch_posts_auth_payload_and_accepts_request(self):
        captured = {}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return json.dumps({"accepted": True, "request_id": "req-1", "state": "provisioning"}).encode()
        def fake_urlopen(req, timeout):
            captured["auth"] = req.get_header("Authorization")
            captured["body"] = json.loads(req.data.decode())
            captured["timeout"] = timeout
            return Response()
        import urllib.request
        original = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            result = request_provisioning(self.settings, self.request)
        finally:
            urllib.request.urlopen = original
        self.assertTrue(result.accepted)
        self.assertEqual(result.request_id, "req-1")
        self.assertEqual(captured["auth"], "Bearer test-token")
        self.assertTrue(captured["body"]["runner"]["ephemeral"])

    def test_provider_rejection_does_not_leak_response_body(self):
        import urllib.request
        original = urllib.request.urlopen
        def fail(*_args, **_kwargs):
            raise HTTPError("https://provider.example.test", 403, "Forbidden", {}, None)
        urllib.request.urlopen = fail
        try:
            with self.assertRaisesRegex(RuntimeError, "HTTP 403") as ctx:
                request_provisioning(self.settings, self.request)
        finally:
            urllib.request.urlopen = original
        self.assertNotIn("test-token", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
