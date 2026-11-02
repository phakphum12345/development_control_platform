"""Policy and lifecycle contract tests for the DCP runner backend."""
import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError

from tools.runner_backend.cloud_api import CloudAPIProvider, ProviderError
from tools.runner_backend.manager import RunnerManager, RunnerPolicyError, RunnerRequest
from tools.runner_backend.provider import RunnerInstance


class FakeProvider:
    def __init__(self):
        self.calls = []

    def provision(self, payload):
        self.calls.append(("provision", payload))
        return RunnerInstance("runner-123", "provisioning", labels=tuple(payload["labels"]))

    def status(self, provider_id):
        self.calls.append(("status", provider_id))
        return RunnerInstance(provider_id, "online")

    def terminate(self, provider_id):
        self.calls.append(("terminate", provider_id))
        return RunnerInstance(provider_id, "terminated")


class FakeHTTPResponse:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class CloudRunnerBackendTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.manager = RunnerManager(self.provider, {"phakphum12345/generated-A4-pdf"})
        self.request = RunnerRequest(
            "phakphum12345/generated-A4-pdf", 12345, "a" * 40
        )

    def test_provision_uses_ephemeral_macos_arm64_and_provider_side_token(self):
        result = self.manager.provision_macos(self.request)
        self.assertEqual(result.state, "provisioning")
        payload = self.provider.calls[0][1]
        self.assertEqual(payload["image"], "macos-15-arm64")
        self.assertTrue(payload["ephemeral"])
        self.assertEqual(payload["registration_token_handling"], "provider-side-only")
        self.assertIn("dcp-cloud-macos", payload["labels"])

    def test_unregistered_repository_is_rejected_before_provider_call(self):
        bad = RunnerRequest("attacker/repo", 12345, "a" * 40)
        with self.assertRaises(RunnerPolicyError):
            self.manager.provision_macos(bad)
        self.assertEqual(self.provider.calls, [])

    def test_invalid_sha_is_rejected(self):
        bad = RunnerRequest(self.request.repository, 12345, "not-a-sha")
        with self.assertRaises(RunnerPolicyError):
            self.manager.provision_macos(bad)

    def test_runtime_limit_is_bounded(self):
        bad = RunnerRequest(self.request.repository, 12345, "a" * 40, max_runtime_minutes=999)
        with self.assertRaises(RunnerPolicyError):
            self.manager.provision_macos(bad)

    def test_workflow_run_id_rejects_bool_float_and_string(self):
        for value in (True, 12.5, "123"):
            with self.subTest(value=value):
                bad = RunnerRequest(self.request.repository, value, "a" * 40)
                with self.assertRaises(RunnerPolicyError):
                    self.manager.provision_macos(bad)
        self.assertEqual(self.provider.calls, [])

    def test_runtime_rejects_non_integer_values(self):
        for value in (True, 5.5, "60"):
            with self.subTest(value=value):
                bad = RunnerRequest(self.request.repository, 12345, "a" * 40, max_runtime_minutes=value)
                with self.assertRaises(RunnerPolicyError):
                    self.manager.provision_macos(bad)

    def test_status_and_terminate_delegate_to_provider(self):
        self.assertEqual(self.manager.status("runner-123").state, "online")
        self.assertEqual(self.manager.terminate("runner-123").state, "terminated")


class CloudAPIProviderTests(unittest.TestCase):
    def setUp(self):
        self.token = "test-secret-token"
        self.provider = CloudAPIProvider("https://gateway.example.test", self.token, timeout=3)

    def test_rejects_non_origin_urls(self):
        for url in (
            "http://gateway.example.test",
            "https://user:pass@gateway.example.test",
            "https://gateway.example.test/api",
            "https://gateway.example.test/?next=/",
            "https://gateway.example.test/#fragment",
            "https://gateway.example.test:bad",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ProviderError):
                    CloudAPIProvider(url, self.token)

    def test_requires_token_and_positive_timeout(self):
        with self.assertRaises(ProviderError):
            CloudAPIProvider("https://gateway.example.test", "")
        with self.assertRaises(ProviderError):
            CloudAPIProvider("https://gateway.example.test", self.token, timeout=0)

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_provision_sends_bearer_auth_and_expected_json(self, mocked_open):
        mocked_open.return_value = FakeHTTPResponse({
            "id": "request-1", "state": "provisioning",
            "runner_name": "dcp-runner-1", "labels": ["macOS"], "detail": "accepted",
        })
        payload = {"repository": "owner/repo", "workflow_run_id": 123}
        result = self.provider.provision(payload)
        request = mocked_open.call_args.args[0]
        self.assertEqual(request.full_url, "https://gateway.example.test/v1/runners")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.token}")
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(json.loads(request.data.decode("utf-8")), payload)
        self.assertEqual(mocked_open.call_args.kwargs["timeout"], 20 if False else 3)
        self.assertEqual((result.provider_id, result.state, result.runner_name), ("request-1", "provisioning", "dcp-runner-1"))

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_status_and_terminate_quote_provider_ids(self, mocked_open):
        mocked_open.return_value = FakeHTTPResponse({"id": "a/b", "state": "online"})
        self.provider.status("a/b")
        self.assertEqual(mocked_open.call_args.args[0].full_url, "https://gateway.example.test/v1/runners/a%2Fb")
        self.provider.terminate("a/b")
        self.assertEqual(mocked_open.call_args.args[0].full_url, "https://gateway.example.test/v1/runners/a%2Fb")
        self.assertEqual(mocked_open.call_args.args[0].method, "DELETE")

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_rejects_invalid_response_shapes_and_optional_field_types(self, mocked_open):
        invalid = (
            [],
            {"state": "online"},
            {"id": "id", "state": ""},
            {"id": "id", "state": "online", "labels": "macOS"},
            {"id": "id", "state": "online", "runner_name": 42},
            {"id": "id", "state": "online", "detail": []},
        )
        for body in invalid:
            with self.subTest(body=body):
                mocked_open.return_value = FakeHTTPResponse(body)
                with self.assertRaises(ProviderError):
                    self.provider.status("id")

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_rejects_oversized_response(self, mocked_open):
        mocked_open.return_value = FakeHTTPResponse(b" " * 65537)
        with self.assertRaisesRegex(ProviderError, "65536-byte limit"):
            self.provider.status("id")

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_transport_errors_do_not_leak_token_or_error_text(self, mocked_open):
        mocked_open.side_effect = URLError(f"failed with {self.token}")
        with self.assertRaises(ProviderError) as caught:
            self.provider.status("id")
        self.assertNotIn(self.token, str(caught.exception))
        self.assertNotIn(self.token, repr(caught.exception))


if __name__ == "__main__":
    unittest.main()
