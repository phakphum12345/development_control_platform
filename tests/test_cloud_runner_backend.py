"""Policy and HTTP-adapter contract tests for the DCP runner backend."""
import json
import unittest
from unittest.mock import MagicMock, patch
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


class CloudRunnerBackendTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.manager = RunnerManager(self.provider, {"phakphum12345/generated-A4-pdf"})
        self.request = RunnerRequest("phakphum12345/generated-A4-pdf", 12345, "a" * 40)

    def test_provision_uses_ephemeral_macos_arm64_and_provider_side_token(self):
        result = self.manager.provision_macos(self.request)
        self.assertEqual(result.state, "provisioning")
        payload = self.provider.calls[0][1]
        self.assertEqual(payload["image"], "macos-15-arm64")
        self.assertTrue(payload["ephemeral"])
        self.assertEqual(payload["registration_token_handling"], "provider-side-only")
        self.assertIn("dcp-cloud-macos", payload["labels"])

    def test_unregistered_repository_is_rejected_before_provider_call(self):
        with self.assertRaises(RunnerPolicyError):
            self.manager.provision_macos(RunnerRequest("attacker/repo", 12345, "a" * 40))
        self.assertEqual(self.provider.calls, [])

    def test_invalid_sha_is_rejected(self):
        with self.assertRaises(RunnerPolicyError):
            self.manager.provision_macos(RunnerRequest(self.request.repository, 12345, "not-a-sha"))

    def test_runtime_limit_is_bounded(self):
        with self.assertRaises(RunnerPolicyError):
            self.manager.provision_macos(RunnerRequest(self.request.repository, 12345, "a" * 40, max_runtime_minutes=999))

    def test_status_and_terminate_delegate_to_provider(self):
        self.assertEqual(self.manager.status("runner-123").state, "online")
        self.assertEqual(self.manager.terminate("runner-123").state, "terminated")

    def test_boolean_run_id_and_runtime_are_rejected(self):
        for bad in (
            RunnerRequest(self.request.repository, True, "a" * 40),
            RunnerRequest(self.request.repository, 123, "a" * 40, max_runtime_minutes=True),
        ):
            with self.subTest(request=bad), self.assertRaises(RunnerPolicyError):
                bad.validate({self.request.repository})


class CloudAPIProviderTests(unittest.TestCase):
    TOKEN = "test-secret-token"

    def make_provider(self, **kwargs):
        return CloudAPIProvider(base_url="https://gateway.example.test", token=self.TOKEN, **kwargs)

    @staticmethod
    def response(payload, status=200):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        response.status = status
        return response

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_provision_sends_bearer_auth_and_expected_json(self, urlopen):
        urlopen.return_value = self.response({
            "id": "request-1", "state": "provisioning",
            "runner_name": "dcp-runner", "labels": ["dcp-cloud-macos"], "detail": "accepted"
        })
        provider = self.make_provider()
        result = provider.provision({"repository": "owner/repo"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://gateway.example.test/v1/runners")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {self.TOKEN}")
        self.assertEqual(json.loads(request.data), {"repository": "owner/repo"})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 20)
        self.assertEqual(result, RunnerInstance("request-1", "provisioning", "dcp-runner", ("dcp-cloud-macos",), "accepted"))

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_status_and_terminate_quote_provider_identifier(self, urlopen):
        urlopen.return_value = self.response({"id": "a/b", "state": "online"})
        provider = self.make_provider()
        provider.status("a/b")
        self.assertEqual(urlopen.call_args.args[0].full_url, "https://gateway.example.test/v1/runners/a%2Fb")
        provider.terminate("a/b")
        self.assertEqual(urlopen.call_args.args[0].full_url, "https://gateway.example.test/v1/runners/a%2Fb")
        self.assertEqual(urlopen.call_args.args[0].method, "DELETE")

    def test_rejects_non_origin_urls(self):
        for url in (
            "http://gateway.example.test",
            "https://user:pass@gateway.example.test",
            "https://gateway.example.test/path",
            "https://gateway.example.test/?token=x",
            "https://gateway.example.test/#fragment",
            "https://",
        ):
            with self.subTest(url=url), self.assertRaises(ProviderError):
                CloudAPIProvider(base_url=url, token=self.TOKEN)

    def test_rejects_missing_token_and_invalid_timeout(self):
        with self.assertRaises(ProviderError):
            CloudAPIProvider(base_url="https://gateway.example.test", token="")
        for timeout in (0, -1, True, "20"):
            with self.subTest(timeout=timeout), self.assertRaises(ProviderError):
                self.make_provider(timeout=timeout)

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_provider_error_does_not_disclose_token_or_endpoint(self, urlopen):
        secret_url = "https://gateway.example.test/private?token=do-not-leak"
        urlopen.side_effect = URLError(secret_url + self.TOKEN)
        provider = CloudAPIProvider(base_url="https://gateway.example.test", token=self.TOKEN)
        with self.assertRaises(ProviderError) as caught:
            provider.provision({})
        self.assertNotIn(self.TOKEN, str(caught.exception))
        self.assertNotIn("do-not-leak", str(caught.exception))

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_rejects_oversized_response(self, urlopen):
        urlopen.return_value = self.response(b"x" * 65537)
        with self.assertRaisesRegex(ProviderError, "65536-byte limit"):
            self.make_provider().provision({})

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_rejects_invalid_response_shapes_and_field_types(self, urlopen):
        invalid = [
            [],
            {"id": "", "state": "online"},
            {"id": "id", "state": ""},
            {"id": "id", "state": "online", "labels": "not-a-list"},
            {"id": "id", "state": "online", "runner_name": 123},
            {"id": "id", "state": "online", "detail": {"secret": "value"}},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                urlopen.return_value = self.response(payload)
                with self.assertRaises(ProviderError):
                    self.make_provider().provision({})

    @patch("tools.runner_backend.cloud_api.urllib.request.urlopen")
    def test_rejects_non_object_request_payload(self, urlopen):
        with self.assertRaises(ProviderError):
            self.make_provider().provision([])
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
