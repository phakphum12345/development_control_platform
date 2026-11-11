"""Local Runner end-to-end tests: authenticated claim, checkout, Flutter process, finish."""
import os
import tempfile
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

from tools.cloud_gateway.job_control import JobStore
from tools.cloud_gateway.artifacts import ArtifactStore
from tools.cloud_gateway.runner_registry import RunnerRegistry
from tools.cloud_gateway.server import make_handler
from tools.local_runner_agent.client import GatewayClient, RunnerAgentConfig
from tools.local_runner_agent.execution import FlutterBuildExecutor
from tools.local_runner_agent.pipeline import RunnerPipeline
from tools.local_runner_agent.workspace import WorkspaceManager
from tools.local_runner_agent.local_project import LocalProjectRegistry
from tools.local_runner_agent.checkout import LocalProjectCheckout


TOKEN = "runner-pipeline-e2e-token-which-is-long-enough"


class _Service:
    def __init__(self, jobs, artifacts=None, registry=None):
        self.job_store = jobs
        self.artifact_store = artifacts
        self.runner_registry = registry


class _FixtureCheckout:
    def __init__(self, manager, cancel_job=None):
        self.manager = manager
        self.cancel_job = cancel_job

    def checkout(self, job_id, worker_id, repository, commit_sha):
        source = self.manager.get(job_id, worker_id) / "source"
        source.mkdir()
        (source / "pubspec.yaml").write_text("name: fixture_app\n")
        (source / "lib").mkdir()
        (source / "lib" / "main.dart").write_text("void main() {}\n")
        if self.cancel_job:
            self.cancel_job(job_id)
        return source


class RunnerPipelineEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.jobs = JobStore(str(self.root / "jobs.sqlite3"))
        self.artifacts = ArtifactStore(self.root / "artifacts")
        self.registry = RunnerRegistry(self.root / "runners.sqlite3")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(_Service(self.jobs, self.artifacts, self.registry), "internal-gateway-token", runner_tokens={
                "runner-e2e": TOKEN,
            }),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        config = RunnerAgentConfig(
            gateway_url=f"http://127.0.0.1:{self.server.server_port}",
            worker_id="runner-e2e", token=TOKEN,
        )
        self.client = GatewayClient(config)
        self.manager = WorkspaceManager(self.root / "workspaces")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def _fake_flutter(self, script):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        executable = bin_dir / "flutter"
        executable.write_text(script)
        executable.chmod(0o700)
        return str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

    @unittest.skipIf(os.name == "nt", "POSIX fixture executable used for deterministic process tests")
    def test_job_runs_from_claim_through_checkout_flutter_and_terminal_state(self):
        job, created = self.jobs.create({
            "repository": "owner/mobile-app",
            "commit_sha": "a" * 40,
            "target": "test",
        }, "runner-pipeline-success-001")
        self.assertTrue(created)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self._fake_flutter(
            "#!/bin/sh\nprintf 'fixture-flutter-build-ok\n'\nexit 0\n"
        )
        logs = []
        try:
            executor = FlutterBuildExecutor(
                self.manager, enabled=True, timeout_seconds=10,
                log=lambda stream, message: logs.append((stream, message)),
            )
            pipeline = RunnerPipeline(
                self.client, self.manager, _FixtureCheckout(self.manager), executor,
                trusted_repositories={"owner/mobile-app"},
                capabilities={"flutter", "linux", "android"},
            )
            result = pipeline.run_once()
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(result["outcome"], "succeeded", result)
        self.assertEqual(result["job"]["state"], "succeeded")
        self.assertTrue(any("fixture-flutter-build-ok" in row["message"] for row in self.jobs.logs(job["id"])))
        self.assertFalse((self.root / "workspaces" / job["id"]).exists())
        events = self.jobs.events(job["id"])
        self.assertIn("running", [event["event"] for event in events])
        self.assertIn("succeeded", [event["event"] for event in events])
        self.assertTrue(any(row["message"] == "Workspace cleaned" for row in self.jobs.logs(job["id"])))

    @unittest.skipIf(os.name == "nt", "POSIX fixture executable used for deterministic process tests")
    def test_cancel_requested_during_build_stops_process_and_finishes_cancelled(self):
        job, _ = self.jobs.create({
            "repository": "owner/mobile-app",
            "commit_sha": "b" * 40,
            "target": "test",
        }, "runner-pipeline-cancel-001")
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self._fake_flutter("#!/bin/sh\nsleep 5\n")
        try:
            executor = FlutterBuildExecutor(
                self.manager, enabled=True, timeout_seconds=10,
            )
            checkout = _FixtureCheckout(self.manager, cancel_job=lambda job_id: self.jobs.cancel(job_id))
            pipeline = RunnerPipeline(self.client, self.manager, checkout, executor,
                                      trusted_repositories={"owner/mobile-app"})
            result = pipeline.run_once()
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(result["job"]["state"], "cancelled")
        self.assertFalse((self.root / "workspaces" / job["id"]).exists())


    @unittest.skipIf(os.name == "nt", "POSIX fixture executable used for deterministic process tests")
    def test_flutter_build_artifact_is_uploaded_hashed_and_available_after_job_finishes(self):
        job, _ = self.jobs.create({
            "repository": "owner/mobile-app",
            "commit_sha": "c" * 40,
            "target": "build_android",
        }, "runner-pipeline-artifact-001")
        old_path = os.environ.get("PATH", "")
        script = (
            "#!/bin/sh\n"
            "mkdir -p build/app/outputs/flutter-apk\n"
            "printf 'fixture-apk-bytes' > build/app/outputs/flutter-apk/app-release.apk\n"
            "exit 0\n"
        )
        os.environ["PATH"] = self._fake_flutter(script)
        try:
            executor = FlutterBuildExecutor(self.manager, enabled=True, timeout_seconds=10)
            pipeline = RunnerPipeline(
                self.client, self.manager, _FixtureCheckout(self.manager), executor,
                trusted_repositories={"owner/mobile-app"},
                capabilities={"flutter", "linux", "android"},
            )
            result = pipeline.run_once()
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(result["outcome"], "succeeded")
        artifact = result["result"]["artifact"]
        self.assertEqual(artifact["name"], "app-release.apk")
        metadata, handle = self.artifacts.open(artifact["id"])
        with handle:
            self.assertEqual(handle.read(), b"fixture-apk-bytes")
        self.assertEqual(metadata["sha256"], artifact["sha256"])
        self.assertFalse((self.root / "workspaces" / job["id"]).exists())


    def test_local_folder_static_build_uses_immutable_snapshot_and_trusted_project_allowlist(self):
        approved = self.root / "approved"
        project = approved / "static-local-app"
        project.mkdir(parents=True)
        (project / "index.html").write_text("<h1>Local snapshot</h1>", encoding="utf-8")
        (project / "app.js").write_text("window.localSnapshot=true;", encoding="utf-8")
        local_registry = LocalProjectRegistry(self.root / "local-projects.json")
        root = local_registry.enroll_root(approved)
        registered = local_registry.register_project(root["root_id"], project)
        job, created = self.jobs.create({
            "source_type": "local_folder",
            "project_id": registered["project_id"],
            "snapshot_sha256": registered["snapshot_sha256"],
            "target": "test_static_web",
        }, "runner-local-folder-static-001")
        self.assertTrue(created)
        from tools.local_runner_agent.web_build import WebBuildExecutor
        class DiagnosticWebBuildExecutor(WebBuildExecutor):
            def run(self, *args, **kwargs):
                try:
                    return super().run(*args, **kwargs)
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    raise
        web_executor = DiagnosticWebBuildExecutor(self.manager, enabled=True)
        class BrowserTestFixture:
            def __init__(self, manager):
                self.manager = manager
            def run(self, job_id, worker_id):
                evidence = self.manager.get(job_id, worker_id) / ".dcp-artifacts" / "web-test-results.zip"
                evidence.parent.mkdir(mode=0o700, exist_ok=True)
                evidence.write_bytes(b"local-folder-playwright-evidence")
                return {
                    "status": "PASS", "duration_seconds": 0.1,
                    "screenshots": ["viewport-mobile.png", "viewport-tablet.png", "viewport-desktop.png"],
                    "accessibility_issue_count": 0, "blocked_external_request_count": 0,
                    "console_error_count": 0, "page_error_count": 0,
                    "report_path": "source/.dcp-test-results/report.json",
                    "artifact_path": evidence, "artifact_name": "web-test-results.zip",
                }
        host_os = "windows" if os.name == "nt" else "linux"
        pipeline = RunnerPipeline(
            self.client, self.manager, _FixtureCheckout(self.manager),
            FlutterBuildExecutor(self.manager, enabled=False),
            trusted_repositories=set(),
            trusted_local_projects={registered["project_id"]},
            local_project_checkout=LocalProjectCheckout(self.manager, local_registry),
            worker_os=host_os,
            capabilities={"web", "playwright", host_os},
            web_executor=web_executor,
            browser_test_executor=BrowserTestFixture(self.manager),
        )
        result = pipeline.run_once()
        self.assertEqual(
            result["outcome"], "succeeded",
            {"pipeline": result, "web_build_error": getattr(web_executor, "last_error", None)},
        )
        self.assertEqual(result["job"]["state"], "succeeded")
        self.assertEqual(result["result"]["source_type"], "local_folder")
        self.assertEqual(result["result"]["source_sha256"], registered["snapshot_sha256"])
        workspace = self.manager.get(job["id"], "runner-e2e")
        self.assertTrue((workspace / "source-snapshot" / "index.html").is_file())
        self.assertTrue((workspace / "source" / "dist" / "index.html").is_file())
        self.assertEqual(result["result"]["browser_test"]["status"], "PASS")
        test_artifact = result["result"]["test_artifact"]
        metadata, handle = self.artifacts.open(test_artifact["id"])
        with handle:
            self.assertEqual(handle.read(), b"local-folder-playwright-evidence")
        self.assertEqual(metadata["sha256"], test_artifact["sha256"])
        self.assertTrue((workspace / ".dcp-preview-retention.json").is_file())

    def test_local_folder_job_fails_closed_without_explicit_project_trust(self):
        approved = self.root / "approved-untrusted"
        project = approved / "untrusted-app"
        project.mkdir(parents=True)
        (project / "index.html").write_text("<h1>Do not execute by default</h1>", encoding="utf-8")
        local_registry = LocalProjectRegistry(self.root / "untrusted-projects.json")
        root = local_registry.enroll_root(approved)
        registered = local_registry.register_project(root["root_id"], project)
        job, _ = self.jobs.create({
            "source_type": "local_folder",
            "project_id": registered["project_id"],
            "snapshot_sha256": registered["snapshot_sha256"],
            "target": "build_static_web",
        }, "runner-local-folder-untrusted-001")
        from tools.local_runner_agent.web_build import WebBuildExecutor
        host_os = "windows" if os.name == "nt" else "linux"
        pipeline = RunnerPipeline(
            self.client, self.manager, _FixtureCheckout(self.manager),
            FlutterBuildExecutor(self.manager, enabled=False),
            trusted_repositories=set(),
            trusted_local_projects=set(),
            local_project_checkout=LocalProjectCheckout(self.manager, local_registry),
            worker_os=host_os,
            capabilities={"web", host_os},
            web_executor=WebBuildExecutor(self.manager, enabled=True),
        )
        result = pipeline.run_once()
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["job"]["state"], "failed")
        self.assertFalse((self.root / "workspaces" / job["id"]).exists())

    def test_static_web_playwright_pipeline_uploads_evidence_and_fails_closed(self):
        from tools.local_runner_agent.web_build import WebBuildExecutor

        class StaticCheckout:
            def __init__(self, manager):
                self.manager = manager
            def checkout(self, job_id, worker_id, repository, commit_sha):
                source = self.manager.get(job_id, worker_id) / "source"
                source.mkdir()
                (source / "index.html").write_text(
                    '<!doctype html><html lang="en"><head><title>Fixture</title></head><body><h1>Ready</h1></body></html>',
                    encoding="utf-8",
                )
                return source

        class BrowserTestFixture:
            def __init__(self, manager, status):
                self.manager = manager
                self.status = status
            def run(self, job_id, worker_id):
                workspace = self.manager.get(job_id, worker_id)
                evidence = workspace / ".dcp-artifacts" / "web-test-results.zip"
                evidence.parent.mkdir(mode=0o700, exist_ok=True)
                evidence.write_bytes(b"fixture-playwright-evidence")
                return {
                    "status": self.status,
                    "duration_seconds": 0.25,
                    "screenshots": ["viewport-mobile.png", "viewport-tablet.png", "viewport-desktop.png"],
                    "accessibility_issue_count": 0 if self.status == "PASS" else 1,
                    "blocked_external_request_count": 0,
                    "console_error_count": 0,
                    "page_error_count": 0,
                    "report_path": "source/.dcp-test-results/report.json",
                    "artifact_path": evidence,
                    "artifact_name": "web-test-results.zip",
                }

        for status, expected_outcome in (("PASS", "succeeded"), ("FAIL", "failed")):
            with self.subTest(status=status):
                job, created = self.jobs.create({
                    "repository": "owner/static-playwright-site",
                    "commit_sha": ("f" if status == "PASS" else "9") * 40,
                    "target": "test_static_web",
                }, "playwright-pipeline-" + status.lower() + "-001")
                self.assertTrue(created)
                pipeline = RunnerPipeline(
                    self.client, self.manager, StaticCheckout(self.manager),
                    FlutterBuildExecutor(self.manager, enabled=False),
                    trusted_repositories={"owner/static-playwright-site"},
                    worker_os="windows" if os.name == "nt" else "linux",
                    capabilities={"web", "playwright", "windows" if os.name == "nt" else "linux"},
                    web_executor=WebBuildExecutor(self.manager, enabled=True),
                    browser_test_executor=BrowserTestFixture(self.manager, status),
                )
                result = pipeline.run_once()
                self.assertEqual(result["outcome"], expected_outcome)
                self.assertEqual(result["job"]["state"], expected_outcome)
                self.assertEqual(result["result"]["browser_test"]["status"], status)
                test_artifact = result["result"]["test_artifact"]
                metadata, handle = self.artifacts.open(test_artifact["id"])
                with handle:
                    self.assertEqual(handle.read(), b"fixture-playwright-evidence")
                self.assertEqual(metadata["sha256"], test_artifact["sha256"])
                self.assertTrue(result["result"]["workspace_retained_for_preview"])

    def test_static_web_job_runs_through_scheduler_and_uploads_artifact(self):
        job, created = self.jobs.create({
            "repository": "owner/static-site",
            "commit_sha": "e" * 40,
            "target": "build_static_web",
        }, "runner-static-web-e2e-001")
        self.assertTrue(created)

        class StaticCheckout:
            def __init__(self, manager):
                self.manager = manager
            def checkout(self, job_id, worker_id, repository, commit_sha):
                source = self.manager.get(job_id, worker_id) / "source"
                source.mkdir()
                (source / "index.html").write_text("<h1>Real static build</h1>", encoding="utf-8")
                (source / "assets").mkdir()
                (source / "assets" / "app.js").write_text("window.ready=true", encoding="utf-8")
                return source

        flutter_executor = FlutterBuildExecutor(self.manager, enabled=False)
        from tools.local_runner_agent.web_build import WebBuildExecutor
        host_os = "windows" if os.name == "nt" else "linux"
        pipeline = RunnerPipeline(
            self.client, self.manager, StaticCheckout(self.manager), flutter_executor,
            trusted_repositories={"owner/static-site"},
            worker_os=host_os,
            capabilities={"web", host_os},
            web_executor=WebBuildExecutor(self.manager, enabled=True),
        )
        result = pipeline.run_once()
        self.assertEqual(result["outcome"], "succeeded")
        self.assertEqual(result["job"]["state"], "succeeded")
        artifact = result["result"]["artifact"]
        self.assertEqual(artifact["name"], "web-build.zip")
        metadata, handle = self.artifacts.open(artifact["id"])
        with handle:
            payload = handle.read()
        self.assertIn(b"index.html", payload)
        self.assertEqual(metadata["sha256"], artifact["sha256"])
        self.assertTrue(result["result"]["workspace_retained_for_preview"])
        retained_workspace = self.manager.get(job["id"], "runner-e2e")
        self.assertTrue((retained_workspace / "source" / "dist" / "index.html").is_file())
        self.assertTrue((retained_workspace / ".dcp-preview-retention.json").is_file())


@unittest.skipUnless(os.name == "nt", "Requires the real Windows cmd.exe batch-file launcher")
class WindowsRunnerPipelineAcceptanceTests(RunnerPipelineEndToEndTests):
    def test_windows_cmd_flutter_build_runs_through_gateway_and_artifact_pipeline(self):
        job, created = self.jobs.create({
            "repository": "owner/mobile-app",
            "commit_sha": "d" * 40,
            "target": "build_android",
        }, "runner-windows-full-e2e-001")
        self.assertTrue(created)

        bin_dir = self.root / "Flutter SDK" / "bin"
        bin_dir.mkdir(parents=True)
        flutter_cmd = bin_dir / "flutter.cmd"
        flutter_cmd.write_text(
            "@echo off\r\n"
            "if /I \"%1\"==\"build\" if /I \"%2\"==\"apk\" (\r\n"
            "  if not exist \"build\\app\\outputs\\flutter-apk\" mkdir \"build\\app\\outputs\\flutter-apk\"\r\n"
            "  > \"build\\app\\outputs\\flutter-apk\\app-release.apk\" echo dcp-fixture-apk\r\n"
            "  exit /b 0\r\n"
            ")\r\n"
            "exit /b 91\r\n",
            encoding="utf-8",
        )

        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bin_dir) + os.pathsep + old_path
        try:
            executor = FlutterBuildExecutor(
                self.manager, enabled=True, timeout_seconds=30,
                max_output_bytes=1024 * 1024,
            )
            pipeline = RunnerPipeline(
                self.client, self.manager, _FixtureCheckout(self.manager), executor,
                trusted_repositories={"owner/mobile-app"},
                worker_os="windows",
                capabilities={"flutter", "windows", "android"},
            )
            result = pipeline.run_once()
        finally:
            os.environ["PATH"] = old_path

        self.assertEqual(result["outcome"], "succeeded")
        self.assertEqual(result["job"]["id"], job["id"])
        self.assertEqual(result["job"]["state"], "succeeded")
        artifact = result["result"]["artifact"]
        self.assertEqual(artifact["name"], "app-release.apk")
        metadata, handle = self.artifacts.open(artifact["id"])
        with handle:
            self.assertEqual(handle.read().strip(), b"dcp-fixture-apk")
        self.assertEqual(metadata["sha256"], artifact["sha256"])
        self.assertFalse((self.root / "workspaces" / job["id"]).exists())
        self.assertTrue(any(
            row["message"] == "Workspace cleaned" for row in self.jobs.logs(job["id"])
        ))


if __name__ == "__main__":
    unittest.main()
