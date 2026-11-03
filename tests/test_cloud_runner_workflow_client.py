"""Tests proving the DCP workflow client uses the canonical gateway contract."""
import unittest
from unittest.mock import patch

from tools.cloud_runner.backend import (
    ProvisionRequest,
    RunnerSettings,
    request_provisioning,
)
from tools.runner_backend.provider import RunnerInstance


class FakeProvider:
    def __init__(self):
        self.calls = []

    def provision(self, payload):
        self.calls.append(payload)
        return RunnerInstance(
            "gateway-runner-1",
            "provisioning",
            "dcp-macos-1",
            tuple(payload["labels"]),
            "accepted",
        )

    def status(self, provider_id):
        return RunnerInstance(provider_id, "online")

    def terminate(self, provider_id):
        return RunnerInstance(provider_id, "terminated")


class CloudRunnerWorkflowClientTests(unittest.TestCase):
    def setUp(self):
        self.settings = RunnerSettings(
            endpoint="https://gateway.example.test",
            bearer_token="test-token",
            allowed_repositories=("phakphum12345/generated-A4-pdf",),
        )
        self.request = ProvisionRequest(
            repository="phakphum12345/generated-A4-pdf",
            commit_sha="A" * 40,
            workflow_run_id=12345,
        )

    def test_workflow_dispatch_uses_exact_openapi_request_shape(self):
        fake = FakeProvider()
        with patch("tools.cloud_runner.backend.CloudAPIProvider", return_value=fake):
            result = request_provisioning(self.settings, self.request)

        self.assertEqual(result.runner_id, "gateway-runner-1")
        self.assertEqual(result.state, "provisioning")
        self.assertEqual(result.runner_name, "dcp-macos-1")
        self.assertEqual(result.labels, ("self-hosted", "macOS", "ARM64", "dcp-cloud-macos"))
        self.assertEqual(fake.calls, [{
            "repository": "phakphum12345/generated-A4-pdf",
            "workflow_run_id": 12345,
            "commit_sha": "a" * 40,
            "image": "macos-15-arm64",
            "labels": ["self-hosted", "macOS", "ARM64", "dcp-cloud-macos"],
            "ephemeral": True,
            "max_runtime_minutes": 60,
            "network_policy": "restricted-egress",
            "registration_token_handling": "provider-side-only",
        }])

    def test_unallowlisted_repository_is_rejected_before_provider_creation(self):
        request = ProvisionRequest("attacker/repo", "a" * 40, 12345)
        with patch("tools.cloud_runner.backend.CloudAPIProvider") as factory:
            with self.assertRaisesRegex(ValueError, "allowlist"):
                request_provisioning(self.settings, request)
        factory.assert_not_called()

    def test_invalid_sha_and_run_id_are_rejected(self):
        for request in (
            ProvisionRequest(self.request.repository, "not-a-sha", 12345),
            ProvisionRequest(self.request.repository, "a" * 40, True),
            ProvisionRequest(self.request.repository, "a" * 40, 0),
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                request.validate(self.settings)

    def test_settings_parse_documented_comma_separated_allowlist(self):
        settings = RunnerSettings.from_env({
            "DCP_RUNNER_PROVIDER_URL": "https://gateway.example.test",
            "DCP_RUNNER_PROVIDER_TOKEN": "secret",
            "DCP_RUNNER_ALLOWED_REPOSITORIES": "owner/one, owner/two",
            "DCP_RUNNER_PROVIDER_TIMEOUT": "30",
        })
        self.assertEqual(settings.allowed_repositories, ("owner/one", "owner/two"))
        self.assertEqual(settings.timeout_seconds, 30)

    def test_settings_reject_unsafe_gateway_origins_and_timeouts(self):
        for endpoint in (
            "http://gateway.example.test",
            "https://user:pass@gateway.example.test",
            "https://gateway.example.test/path",
            "https://gateway.example.test/?token=x",
            "https://gateway.example.test/#fragment",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                RunnerSettings(endpoint, "secret")
        with self.assertRaises(ValueError):
            RunnerSettings("https://gateway.example.test", "secret", timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
