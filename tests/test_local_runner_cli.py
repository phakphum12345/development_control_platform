"""Unified local Runner CLI tests; no repository code is executed."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tools.local_runner_agent import __main__ as cli


TOKEN = "unified-local-runner-cli-test-token-long-enough"


class LocalRunnerCliTests(unittest.TestCase):
    def _base_env(self):
        return {
            "DCP_GATEWAY_URL": "http://127.0.0.1:18790",
            "DCP_RUNNER_WORKER_ID": "windows-ci-runner",
            "DCP_RUNNER_TOKEN": TOKEN,
        }

    @patch.object(cli, "collect_preflight")
    @patch.object(cli, "resolve_capabilities", return_value=["flutter", "windows"])
    @patch.object(cli.platform, "system", return_value="Windows")
    @patch.object(cli, "GatewayClient")
    def test_enroll_only_registers_offline_without_execution_opt_in(
        self, client_type, _host, _capabilities, preflight
    ):
        preflight.return_value = {
            "host_os": "windows",
            "minimum_agent_prerequisites_met": True,
            "detected_capabilities": ["flutter", "windows"],
        }
        client = client_type.return_value
        client.health.return_value = {"status": "ok"}
        client.enroll.return_value = {
            "worker_id": "windows-ci-runner", "host_os": "windows",
            "capabilities": ["flutter", "windows"], "state": "offline",
        }
        with patch.dict(os.environ, self._base_env(), clear=True):
            self.assertEqual(cli.main(["--enroll-only"]), 0)
        client.enroll.assert_called_once_with("windows", ["flutter", "windows"])
        client.register.assert_not_called()
        client.claim.assert_not_called()

    @patch.object(cli, "collect_preflight")
    @patch.object(cli, "resolve_capabilities", return_value=["flutter", "windows"])
    @patch.object(cli.platform, "system", return_value="Windows")
    @patch.object(cli, "GatewayClient")
    def test_serve_refuses_to_start_without_explicit_execution_opt_in(
        self, client_type, _host, _capabilities, preflight
    ):
        preflight.return_value = {
            "host_os": "windows",
            "minimum_agent_prerequisites_met": True,
            "detected_capabilities": ["flutter", "windows"],
        }
        client_type.return_value.health.return_value = {"status": "ok"}
        with patch.dict(os.environ, self._base_env(), clear=True):
            self.assertEqual(cli.main(["--serve"]), 1)

    @patch.object(cli, "collect_preflight")
    @patch.object(cli, "resolve_capabilities", return_value=["flutter", "windows"])
    @patch.object(cli.platform, "system", return_value="Windows")
    @patch.object(cli, "GatewayClient")
    def test_terminal_opt_in_requires_an_explicit_trusted_local_project(
        self, client_type, _host, _capabilities, preflight
    ):
        preflight.return_value = {
            "host_os": "windows",
            "minimum_agent_prerequisites_met": True,
            "detected_capabilities": ["flutter", "windows"],
        }
        client_type.return_value.health.return_value = {"status": "ok"}
        with tempfile.TemporaryDirectory() as temp:
            env = self._base_env()
            env.update({
                "DCP_RUNNER_EXECUTION_ENABLED": "1",
                "DCP_RUNNER_TERMINAL_ENABLED": "1",
                "DCP_RUNNER_TRUSTED_REPOSITORIES": json.dumps(["owner/repo"]),
                "DCP_RUNNER_TRUSTED_LOCAL_PROJECTS": "[]",
                "DCP_RUNNER_WORKSPACE_ROOT": temp,
            })
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(cli.main(["--serve"]), 1)
        client_type.return_value.register.assert_not_called()
        client_type.return_value.claim.assert_not_called()

    @patch.object(cli.signal, "getsignal", return_value=None)
    @patch.object(cli.signal, "signal")
    @patch.object(cli, "RunnerAgentService")
    @patch.object(cli, "RunnerPipeline")
    @patch.object(cli, "WebBuildExecutor")
    @patch.object(cli, "FlutterBuildExecutor")
    @patch.object(cli, "GitHubCommitCheckout")
    @patch.object(cli, "WorkspaceManager")
    @patch.object(cli, "collect_preflight")
    @patch.object(cli, "resolve_capabilities", return_value=["flutter", "windows"])
    @patch.object(cli.platform, "system", return_value="Windows")
    @patch.object(cli, "GatewayClient")
    def test_serve_uses_unified_pipeline_and_installs_shutdown_handlers(
        self, client_type, _host, _capabilities, preflight, workspace_type,
        _checkout, _flutter, _web, pipeline_type, service_type, _signal, _getsignal
    ):
        preflight.return_value = {
            "host_os": "windows",
            "minimum_agent_prerequisites_met": True,
            "detected_capabilities": ["flutter", "windows"],
        }
        client_type.return_value.health.return_value = {"status": "ok"}
        pipeline = pipeline_type.return_value
        service = service_type.return_value
        service.run.return_value = {
            "stopped": True, "reason": "stop_requested", "cycles": 0,
            "jobs_processed": 0, "idle_polls": 0, "gateway_errors": 0,
            "outcomes": {"succeeded": 0, "failed": 0, "cancelled": 0, "unconfirmed": 0},
        }
        with tempfile.TemporaryDirectory() as temp:
            env = self._base_env()
            env.update({
                "DCP_RUNNER_EXECUTION_ENABLED": "1",
                "DCP_RUNNER_TRUSTED_REPOSITORIES": json.dumps(["owner/repo"]),
                "DCP_RUNNER_TRUSTED_LOCAL_PROJECTS": "[]",
                "DCP_RUNNER_WORKSPACE_ROOT": temp,
            })
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(cli.main(["--serve"]), 0)
        service_type.assert_called_once_with(
            pipeline, poll_interval_seconds=5, max_backoff_seconds=60
        )
        service.run.assert_called_once()
        self.assertEqual(service.run.call_args.args[0].__class__.__name__, "Event")


if __name__ == "__main__":
    unittest.main()
