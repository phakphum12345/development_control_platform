"""Mock-only protected Azure bootstrap payload tests."""
import base64
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tools.cloud_gateway.runner_bootstrap import AzureRunnerBootstrapFactory, RunnerBootstrapError


class FakeGitHubApp:
    def __init__(self, token="mock-registration-token"):
        self.token = token
        self.repositories = []

    def create_registration_token(self, repository):
        self.repositories.append(repository)
        return SimpleNamespace(
            token=self.token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=self.expiry_delta),
        )


def payload(os_name):
    labels = ["self-hosted", "Linux", "X64", "dcp-cloud-linux"] if os_name == "linux" else [
        "self-hosted", "Windows", "X64", "dcp-cloud-windows"
    ]
    return {
        "repository": "phakphum12345/generated-A4-pdf",
        "target_os": os_name,
        "labels": labels,
        "ephemeral": True,
        "network_policy": "restricted-egress",
    }


class AzureRunnerBootstrapTests(unittest.TestCase):
    def make(self, app=None):
        return AzureRunnerBootstrapFactory(
            app or FakeGitHubApp(),
            "2.331.0",
            "a" * 64,
            "b" * 64,
            lambda vm, os_name, request: {"computerName": vm, "os": os_name},
        )

    def test_linux_registration_token_is_only_in_protected_script(self):
        app = FakeGitHubApp()
        result = self.make(app)("dcp-123-abcdef12", "linux", payload("linux"))
        props = result["extension"]["properties"]
        script = base64.b64decode(props["protectedSettings"]["script"]).decode()
        self.assertEqual(props["publisher"], "Microsoft.Azure.Extensions")
        self.assertEqual(props["settings"], {})
        self.assertIn("mock-registration-token", script)
        self.assertIn("sha256sum --check --status", script)
        self.assertIn("--ephemeral --disableupdate", script)
        self.assertNotIn("mock-registration-token", str(props["settings"]))
        self.assertEqual(app.repositories, ["phakphum12345/generated-A4-pdf"])

    def test_windows_token_is_only_in_encoded_protected_command(self):
        app = FakeGitHubApp()
        result = self.make(app)("dcp-123-abcdef12", "windows", payload("windows"))
        props = result["extension"]["properties"]
        command = props["protectedSettings"]["commandToExecute"]
        encoded = command.rsplit(" ", 1)[1]
        script = base64.b64decode(encoded).decode("utf-16le")
        self.assertEqual(props["publisher"], "Microsoft.Compute")
        self.assertEqual(props["settings"], {})
        self.assertIn("mock-registration-token", script)
        self.assertIn("Get-FileHash -Algorithm SHA256", script)
        self.assertIn("--ephemeral --disableupdate", script)
        self.assertNotIn("mock-registration-token", str(props["settings"]))

    def test_rejects_unpinned_runner_artifacts(self):
        with self.assertRaises(ValueError):
            AzureRunnerBootstrapFactory(FakeGitHubApp(), "latest", "a" * 64, "b" * 64, lambda *_: {})
        with self.assertRaises(ValueError):
            AzureRunnerBootstrapFactory(FakeGitHubApp(), "2.331.0", "bad", "b" * 64, lambda *_: {})

    def test_rejects_invalid_profile_before_minting_token(self):
        app = FakeGitHubApp()
        with self.assertRaises(RunnerBootstrapError):
            self.make(app)("dcp-123-abcdef12", "macos", payload("macos"))
        self.assertEqual(app.repositories, [])

    def test_rejects_unrestricted_or_non_ephemeral_request(self):
        app = FakeGitHubApp()
        bad = payload("linux")
        bad["network_policy"] = "public"
        with self.assertRaises(RunnerBootstrapError):
            self.make(app)("dcp-123-abcdef12", "linux", bad)
        self.assertEqual(app.repositories, [])

    def test_rejects_invalid_registration_token(self):
        with self.assertRaises(RunnerBootstrapError):
            self.make(FakeGitHubApp("bad token"))("dcp-123-abcdef12", "linux", payload("linux"))


if __name__ == "__main__":
    unittest.main()
