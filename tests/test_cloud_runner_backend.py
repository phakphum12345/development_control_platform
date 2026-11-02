"""Policy and lifecycle contract tests for the DCP runner backend."""
import unittest

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

    def test_status_and_terminate_delegate_to_provider(self):
        self.assertEqual(self.manager.status("runner-123").state, "online")
        self.assertEqual(self.manager.terminate("runner-123").state, "terminated")


if __name__ == "__main__":
    unittest.main()
