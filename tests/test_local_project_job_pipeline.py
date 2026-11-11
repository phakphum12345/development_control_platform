"""End-to-end Runner execution from an explicitly approved Local Project snapshot."""
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from tools.cloud_gateway.artifacts import ArtifactStore
from tools.cloud_gateway.job_control import JobStore
from tools.cloud_gateway.runner_registry import RunnerRegistry
from tools.cloud_gateway.server import make_handler
from tools.local_runner_agent.client import GatewayClient, RunnerAgentConfig
from tools.local_runner_agent.execution import FlutterBuildExecutor
from tools.local_runner_agent.local_project import LocalProjectRegistry
from tools.local_runner_agent.pipeline import RunnerPipeline
from tools.local_runner_agent.workspace import WorkspaceManager


TOKEN = "local-project-pipeline-token-which-is-long-enough"


class _Service:
    def __init__(self, jobs, artifacts, runners):
        self.job_store = jobs
        self.artifact_store = artifacts
        self.runner_registry = runners


class LocalProjectRunnerPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.jobs = JobStore(str(self.base / "jobs.sqlite"))
        self.artifacts = ArtifactStore(self.base / "artifacts")
        self.runners = RunnerRegistry(self.base / "runners.sqlite")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(
                _Service(self.jobs, self.artifacts, self.runners),
                "unused-gateway-token",
                runner_tokens={"local-runner": TOKEN},
            ),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = GatewayClient(RunnerAgentConfig(
            gateway_url="http://127.0.0.1:" + str(self.server.server_port),
            worker_id="local-runner",
            token=TOKEN,
        ))
        self.workspaces = WorkspaceManager(self.base / "workspaces")
        approved = self.base / "approved"
        self.project = approved / "flutter-app"
        (self.project / "lib").mkdir(parents=True)
        (self.project / "pubspec.yaml").write_text("name: local_fixture\n", encoding="utf-8")
        (self.project / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
        self.local_projects = LocalProjectRegistry(self.base / "local-projects.json")
        root = self.local_projects.enroll_root(approved)
        self.project_record = self.local_projects.register_project(root["root_id"], self.project)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def _fake_flutter_path(self):
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        executable = bin_dir / "flutter"
        executable.write_text("#!/bin/sh\nprintf 'local-flutter-test-ok\\n'\nexit 0\n", encoding="utf-8")
        executable.chmod(0o700)
        return str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

    def _create_job(self, key):
        return self.jobs.create({
            "source_type": "local",
            "local_project_id": self.project_record["project_id"],
            "snapshot_sha256": self.project_record["snapshot_sha256"],
            "target": "test",
            "execution_approved": True,
        }, key)

    @unittest.skipIf(os.name == "nt", "POSIX fixture executable used for deterministic process tests")
    def test_approved_local_project_runs_from_verified_snapshot_to_terminal_job(self):
        job, created = self._create_job("local-runner-e2e-0001")
        self.assertTrue(created)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self._fake_flutter_path()
        try:
            executor = FlutterBuildExecutor(self.workspaces, enabled=True, timeout_seconds=10)
            pipeline = RunnerPipeline(
                self.client, self.workspaces, checkout=object(), executor=executor,
                trusted_repositories=set(),
                capabilities={"flutter", "linux", "android"},
                local_projects=self.local_projects,
            )
            result = pipeline.run_once()
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(result["outcome"], "succeeded")
        self.assertEqual(result["job"]["state"], "succeeded")
        self.assertEqual(result["result"]["source_type"], "local")
        self.assertEqual(result["result"]["local_project_id"], self.project_record["project_id"])
        self.assertEqual(result["result"]["snapshot_sha256"], self.project_record["snapshot_sha256"])
        self.assertFalse((self.base / "workspaces" / job["id"]).exists())
        self.assertTrue(any(
            "local-flutter-test-ok" in row["message"] for row in self.jobs.logs(job["id"])
        ))
        self.assertTrue(any(
            row["message"] == "Workspace cleaned" for row in self.jobs.logs(job["id"])
        ))

    @unittest.skipIf(os.name == "nt", "POSIX fixture executable used for deterministic process tests")
    def test_source_change_after_queue_fails_before_flutter_execution_and_cleans_workspace(self):
        job, _ = self._create_job("local-runner-e2e-stale-0001")
        (self.project / "pubspec.yaml").write_text("name: changed_after_queue\n", encoding="utf-8")
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self._fake_flutter_path()
        try:
            executor = FlutterBuildExecutor(self.workspaces, enabled=True, timeout_seconds=10)
            pipeline = RunnerPipeline(
                self.client, self.workspaces, checkout=object(), executor=executor,
                trusted_repositories=set(),
                capabilities={"flutter", "linux", "android"},
                local_projects=self.local_projects,
            )
            result = pipeline.run_once()
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["job"]["state"], "failed")
        self.assertEqual(result["result"]["error"], "LocalProjectError")
        self.assertFalse((self.base / "workspaces" / job["id"]).exists())


if __name__ == "__main__":
    unittest.main()
