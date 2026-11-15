"""Runtime wiring tests for private GitHub App repository authorization and cleanup."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.cloud_gateway import github_app_runtime


def environment():
    return {
        "DCP_AZURE_KEY_VAULT_URL": "https://dcp-vault.vault.azure.net",
        "DCP_GITHUB_APP_ID": "123456",
        "DCP_GITHUB_APP_INSTALLATION_ID": "987654",
        "DCP_GITHUB_APP_PRIVATE_KEY_SECRET_NAME": "github-app-key",
    }


class GitHubAppRuntimeTests(unittest.TestCase):
    def test_configured_allowlist_is_passed_as_a_narrowing_filter(self):
        settings = SimpleNamespace(allowed_repositories=("owner/private-repo",))
        with (
            patch.object(github_app_runtime, "ManagedIdentityCredential") as credential_type,
            patch.object(github_app_runtime, "KeyVaultSecretReader") as secret_type,
            patch.object(github_app_runtime, "GitHubAppRunnerBootstrap") as app_type,
            patch.object(github_app_runtime, "GitHubRunnerCleanup") as cleanup_type,
        ):
            secret_type.return_value.get_secret.return_value = "private-key-material"
            app, checker, cleanup = github_app_runtime.build_github_app_runtime(settings, environment())
        app_type.assert_called_once_with("123456", 987654, "private-key-material", ("owner/private-repo",))
        credential_type.assert_called_once()
        secret_type.assert_called_once()
        cleanup_type.assert_called_once_with(app)
        self.assertIs(cleanup, cleanup_type.return_value)
        self.assertIsNotNone(checker)

    def test_empty_allowlist_keeps_private_installation_catalog_as_authority(self):
        settings = SimpleNamespace(allowed_repositories=())
        with (
            patch.object(github_app_runtime, "ManagedIdentityCredential"),
            patch.object(github_app_runtime, "KeyVaultSecretReader") as secret_type,
            patch.object(github_app_runtime, "GitHubAppRunnerBootstrap") as app_type,
            patch.object(github_app_runtime, "GitHubRunnerCleanup"),
        ):
            secret_type.return_value.get_secret.return_value = "private-key-material"
            github_app_runtime.build_github_app_runtime(settings, environment())
        self.assertEqual(app_type.call_args.args[3], ())

    def test_partial_runtime_configuration_fails_closed(self):
        settings = SimpleNamespace(allowed_repositories=("owner/private-repo",))
        env = environment()
        env.pop("DCP_GITHUB_APP_PRIVATE_KEY_SECRET_NAME")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            github_app_runtime.build_github_app_runtime(settings, env)


if __name__ == "__main__":
    unittest.main()
