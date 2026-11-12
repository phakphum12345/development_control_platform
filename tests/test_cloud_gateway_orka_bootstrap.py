"""Tests for protected Orka 4.0 User Data bootstrap generation."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tools.cloud_gateway.orka_bootstrap import OrkaBootstrapError, OrkaRunnerBootstrapFactory


class FakeGitHubApp:
    def __init__(self, token="short-lived-runner-registration-token", expiry=None):
        self.token = token
        self.expiry = expiry or (datetime.now(timezone.utc) + timedelta(minutes=30))
        self.repositories = []

    def create_registration_token(self, repository):
        self.repositories.append(repository)
        return SimpleNamespace(token=self.token, expires_at=self.expiry)


def payload():
    return {
        "repository": "phakphum12345/generated-A4-pdf",
        "workflow_run_id": 123,
        "commit_sha": "a" * 40,
        "target_os": "macos",
        "image": "macos-15-arm64",
        "labels": ["self-hosted", "macos", "macos-15-arm64"],
        "ephemeral": True,
        "network_policy": "restricted-egress",
    }


class OrkaRunnerBootstrapFactoryTests(unittest.TestCase):
    def make(self, app=None):
        return OrkaRunnerBootstrapFactory(
            app or FakeGitHubApp(),
            "2.331.0",
            "a" * 64,
            "dcp-runner",
            "/Users/dcp-runner",
        )

    def test_builds_idempotent_pinned_arm64_user_data_without_logging_token(self):
        app = FakeGitHubApp()
        result = self.make(app)("dcp-123-abcdef12", "macos", payload())
        script = result["script"]
        self.assertEqual(app.repositories, ["phakphum12345/generated-A4-pdf"])
        self.assertIn("actions-runner-osx-arm64-2.331.0.tar.gz", script)
        self.assertIn("shasum -a 256 -c -", script)
        self.assertIn("for attempt in 1 2 3 4 5 6", script)
        self.assertIn("--ephemeral --disableupdate --work _work", script)
        self.assertIn("svc.sh install", script)
        self.assertIn("svc.sh start", script)
        self.assertIn("set +x", script)
        self.assertIn("umask 077", script)
        self.assertIn("admin|wheel", script)
        self.assertIn("if [ ! -f .runner ]; then", script)
        self.assertNotIn("echo " + app.token, script)
        self.assertIn(app.token, script)
        self.assertLess(len(script.encode("utf-8")), 48 * 1024)

    def test_rejects_expired_or_malformed_registration_credentials(self):
        expired = FakeGitHubApp(expiry=datetime.now(timezone.utc) + timedelta(seconds=30))
        with self.assertRaises(OrkaBootstrapError):
            self.make(expired)("dcp-123-abcdef12", "macos", payload())
        invalid = FakeGitHubApp(token="bad token")
        with self.assertRaises(OrkaBootstrapError):
            self.make(invalid)("dcp-123-abcdef12", "macos", payload())

    def test_rejects_wrong_os_image_or_network_policy(self):
        bad = payload()
        bad["target_os"] = "linux"
        with self.assertRaises(OrkaBootstrapError):
            self.make()("dcp-123-abcdef12", "macos", bad)
        bad = payload()
        bad["image"] = "macos-14-intel"
        with self.assertRaises(OrkaBootstrapError):
            self.make()("dcp-123-abcdef12", "macos", bad)
        bad = payload()
        bad["network_policy"] = "public"
        with self.assertRaises(OrkaBootstrapError):
            self.make()("dcp-123-abcdef12", "macos", bad)

    def test_rejects_invalid_runner_identity_and_image_inputs(self):
        with self.assertRaises(ValueError):
            OrkaRunnerBootstrapFactory(FakeGitHubApp(), "latest", "a" * 64, "dcp-runner", "/Users/dcp-runner")
        with self.assertRaises(ValueError):
            OrkaRunnerBootstrapFactory(FakeGitHubApp(), "2.331.0", "bad", "dcp-runner", "/Users/dcp-runner")
        with self.assertRaises(ValueError):
            OrkaRunnerBootstrapFactory(FakeGitHubApp(), "2.331.0", "a" * 64, "root", "/Users/dcp-runner")
        with self.assertRaises(ValueError):
            OrkaRunnerBootstrapFactory(FakeGitHubApp(), "2.331.0", "a" * 64, "dcp-runner", "/tmp/dcp-runner")


if __name__ == "__main__":
    unittest.main()
