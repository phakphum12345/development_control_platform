"""Local Runner end-to-end tests: authenticated claim, checkout, Flutter process, finish."""
import os
import tempfile
import threading
import unittest
import uuid
from contextlib import ExitStack
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from pathlib import Path

from tools.cloud_gateway.job_control import JobStore
from tools.cloud_gateway.terminal_grants import TerminalGrantStore
from tools.cloud_gateway.terminal_catalog import preview_template
from tools.cloud_gateway.terminal_execution_contract import template_version_digest
from tools.cloud_gateway.artifacts import ArtifactStore
from tools.cloud_gateway.runner_registry import RunnerRegistry
from tools.cloud_gateway.server import make_handler
from tools.local_runner_agent.client import GatewayClient, RunnerAgentConfig
from tools.local_runner_agent.execution import FlutterBuildExecutor
from tools.local_runner_agent.pipeline import RunnerPipeline
from tools.local_runner_agent.service import RunnerAgentService
from tools.local_runner_agent.workspace import WorkspaceManager
from tools.local_runner_agent.local_project import LocalProjectRegistry
from tools.local_runner_agent.checkout import LocalProjectCheckout
from tools.local_runner_agent.terminal_executor import TerminalScriptExecutor
from tools.local_runner_agent.terminal_isolation import IsolationAssessment


TOKEN = "runner-pipeline-e2e-token-which-is-long-enough"


class _Service:
    def __init__(self, jobs, artifacts=None, registry=None):
        self.job_store = jobs
        self.artifact_store = artifacts
        self.runner_registry = registry
        self.terminal_grant_store = None


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


class _TestOnlyTerminalSandboxCommand:
    """Process test stub; deliberately provides no OS isolation."""

    def __init__(self, executable, argv):
        self.argv = (executable, *argv)
        self._fd = tempfile.TemporaryFile(mode="w+b")

    @property
    def seccomp_fd(self):
        return self._fd.fileno()

    def close(self):
        self._fd.close()


class _TestOnlyTerminalLauncher:
    def build(self, *, executable, argv, workspace, scratch, environment=None):
        return _TestOnlyTerminalSandboxCommand(executable, argv)


class RunnerPipelineEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.jobs = JobStore(str(self.root / "jobs.sqlite3"))
        self.artifacts = ArtifactStore(self.root / "artifacts")
        self.registry = RunnerRegistry(self.root / "runners.sqlite3")
        self.grants = TerminalGrantStore(self.root / "terminal-grants.sqlite3")
        service = _Service(self.jobs, self.artifacts, self.registry)
        service.terminal_grant_store = self.grants
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(service, "internal-gateway-token", runner_tokens={
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

    def test_unified_client_enrolls_offline_then_registers_for_claims(self):
        job, _ = self.jobs.create({
            "repository": "owner/mobile-app",
            "commit_sha": "d" * 40,
            "target": "test",
        }, "runner-unified-enroll-001")

        offline = self.client.enroll("linux", ["flutter", "linux"])
        self.assertEqual(offline["worker_id"], "runner-e2e")
        self.assertEqual(offline["state"], "offline")
        self.assertEqual(self.registry.allowed_targets("runner-e2e"), [])
        from tools.local_runner_agent.client import RunnerGatewayError
        with self.assertRaises(RunnerGatewayError) as error:
            self.client.claim(30)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.jobs.get(job["id"])["state"], "queued")

        live = self.client.register("linux", ["flutter", "linux"])
        self.assertEqual(live["state"], "online")
        claimed = self.client.claim(30)
        self.assertEqual(claimed["id"], job["id"])
        self.assertEqual(claimed["state"], "running")

    def test_supervisor_polls_idle_gateway_until_shutdown_without_claiming_code(self):
        stop = threading.Event()
        waits = []

        def wait(seconds):
            waits.append(seconds)
            if len(waits) == 2:
                stop.set()

        host_os = "windows" if os.name == "nt" else "linux"
        pipeline = RunnerPipeline(
            self.client, self.manager, _FixtureCheckout(self.manager),
            FlutterBuildExecutor(self.manager, enabled=False),
            trusted_repositories={"owner/mobile-app"},
            worker_os=host_os,
            capabilities={"flutter", host_os, "android"},
        )
        result = RunnerAgentService(
            pipeline, poll_interval_seconds=1, wait=wait
        ).run(stop)

        self.assertTrue(result["stopped"])
        self.assertEqual(result["reason"], "stop_requested")
        self.assertEqual(result["idle_polls"], 2)
        self.assertEqual(result["jobs_processed"], 0)
        self.assertEqual(waits, [1, 1])
        self.assertEqual(self.registry.get("runner-e2e")["state"], "online")

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
        saved_job = self.jobs.get(job["id"])
        self.assertEqual(saved_job["checkpoint"]["step"], "ready-to-finish")
        self.assertTrue(saved_job["checkpoint"]["safe_to_resume"])
        self.assertEqual(saved_job["checkpoint_seq"], 2)
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
        self.assertEqual(self.jobs.get(job["id"])["checkpoint"]["step"], "cancelled-ready-to-finish")
        self.assertFalse(self.jobs.get(job["id"])["checkpoint"]["safe_to_resume"])
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


    @unittest.skipIf(os.name == "nt", "POSIX fixture executable used for deterministic process tests")
    def test_lost_finish_response_replays_terminal_checkpoint_without_rebuilding(self):
        job, _ = self.jobs.create({
            "repository": "owner/mobile-app",
            "commit_sha": "7" * 40,
            "target": "test",
        }, "runner-finish-replay-0001")
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self._fake_flutter(
            "#!/bin/sh\nprintf 'checkpoint-replay-build\n'\nexit 0\n"
        )

        class DropFinishOnce:
            def __init__(self, client):
                self.client = client
                self.drop = True
            def __getattr__(self, name):
                return getattr(self.client, name)
            def finish(self, *args, **kwargs):
                if self.drop:
                    self.drop = False
                    raise OSError("simulated lost finish response")
                return self.client.finish(*args, **kwargs)

        class NeverCheckout:
            def checkout(self, *args, **kwargs):
                raise AssertionError("safe terminal checkpoint must not rebuild or checkout")

        try:
            first_pipeline = RunnerPipeline(
                DropFinishOnce(self.client), self.manager, _FixtureCheckout(self.manager),
                FlutterBuildExecutor(self.manager, enabled=True, timeout_seconds=10),
                trusted_repositories={"owner/mobile-app"},
                capabilities={"flutter", "linux", "android"},
            )
            first = first_pipeline.run_once()
        finally:
            os.environ["PATH"] = old_path

        self.assertEqual(first["outcome"], "unconfirmed")
        stored = self.jobs.get(job["id"])
        self.assertEqual(stored["state"], "running")
        self.assertEqual(stored["checkpoint"]["step"], "ready-to-finish")
        self.assertTrue(stored["checkpoint"]["safe_to_resume"])
        self.assertFalse((self.root / "workspaces" / job["id"]).exists())

        with self.jobs.db() as db:
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?",
                       ("2000-01-01T00:00:00+00:00", job["id"]))
        recovered = self.jobs.recover_expired_leases()
        self.assertEqual(recovered[0]["state"], "retry_wait")
        with self.jobs.db() as db:
            db.execute("UPDATE jobs SET retry_after=? WHERE id=?",
                       ("2000-01-01T00:00:00+00:00", job["id"]))

        second_pipeline = RunnerPipeline(
            self.client, self.manager, NeverCheckout(),
            FlutterBuildExecutor(self.manager, enabled=False),
            trusted_repositories={"owner/mobile-app"},
            capabilities={"flutter", "linux", "android"},
        )
        second = second_pipeline.run_once()
        self.assertEqual(second["outcome"], "succeeded")
        self.assertTrue(second["resumed_from_checkpoint"])
        self.assertEqual(second["job"]["state"], "succeeded")
        self.assertEqual(second["job"]["attempt_count"], 2)
        self.assertEqual(second["result"]["command"][0], "flutter")

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
                checkpoint = self.jobs.get(job["id"])["checkpoint"]
                self.assertEqual(checkpoint["step"], "workspace-not-transferable")
                self.assertFalse(checkpoint["safe_to_resume"])
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
        checkpoint = self.jobs.get(job["id"])["checkpoint"]
        self.assertEqual(checkpoint["step"], "workspace-not-transferable")
        self.assertFalse(checkpoint["safe_to_resume"])
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


    def test_terminal_template_runs_only_after_grant_in_the_actual_registered_project_workspace(self):
        project_root = self.root / "approved-project-root"
        project_root.mkdir()
        project_path = project_root / "sample-project"
        project_path.mkdir()
        readme = project_path / "README.md"
        readme.write_text("unchanged project workspace\n", encoding="utf-8")
        registry = LocalProjectRegistry(self.root / "terminal-projects.json")
        approved_root = registry.enroll_root(project_root)
        project = registry.register_project(approved_root["root_id"], project_path)

        template = preview_template("python_version", {})
        template["execution_enabled"] = True
        with patch("tools.cloud_gateway.terminal_execution_contract.preview_template", return_value=template):
            digest = template_version_digest("python_version", {})
        parameters_sha256 = self.grants.parameters_digest(template["parameter_values"])
        grant = self.grants.issue(
            subject="owner@example.test", session_id="owner_session_token_123456",
            project_id=project["project_id"], workspace_id=project["workspace_id"],
            snapshot_sha256=project["snapshot_sha256"], template_id="python_version",
            template_digest=digest, parameters_sha256=parameters_sha256,
        )
        payload = {
            "source_type": "terminal_script",
            "project_id": project["project_id"],
            "workspace_id": project["workspace_id"],
            "snapshot_sha256": project["snapshot_sha256"],
            "target": "terminal_script",
            "template_id": "python_version",
            "parameters": template["parameter_values"],
            "authorization_id": grant["authorization_id"],
            "template_digest": digest,
            "parameters_sha256": parameters_sha256,
        }
        with patch("tools.cloud_gateway.job_control.preview_template", return_value=template), \
             patch("tools.cloud_gateway.terminal_execution_contract.preview_template", return_value=template):
            job, created = self.jobs.create(payload, "terminal-pipeline-e2e-0001")
        self.assertTrue(created)
        self.grants.reserve_job(grant["authorization_id"], job_id=job["id"])

        host_os = "windows" if os.name == "nt" else "linux"
        pipeline = RunnerPipeline(
            self.client, self.manager, _FixtureCheckout(self.manager),
            FlutterBuildExecutor(self.manager, enabled=False),
            trusted_repositories=frozenset(),
            worker_os=host_os,
            capabilities=frozenset({"flutter", host_os, "terminal"}),
            local_project_checkout=LocalProjectCheckout(self.manager, registry),
            trusted_local_projects=frozenset({project["project_id"]}),
            terminal_executor=TerminalScriptExecutor(enabled=True),
        )
        # This test validates the authorization/grant/workspace pipeline, not an OS
        # sandbox. Inject a test-only verifier result so it can exercise the process
        # path without weakening the production fail-closed isolation assessment.
        test_verified_isolation = IsolationAssessment(
            platform="linux" if os.name != "nt" else "windows",
            backend="test-only-injected-verifier",
            state="VERIFIED",
            available=True,
            network_isolated=True,
            filesystem_isolated=True,
            process_tree_contained=True,
            reason="test-only fixture; not production isolation evidence",
        )
        with ExitStack() as stack:
            stack.enter_context(patch(
                "tools.local_runner_agent.terminal_executor.preview_template",
                return_value=template,
            ))
            stack.enter_context(patch(
                "tools.cloud_gateway.terminal_execution_contract.preview_template",
                return_value=template,
            ))
            stack.enter_context(patch(
                "tools.local_runner_agent.terminal_executor.assess_isolation_backend",
                return_value=test_verified_isolation,
            ))
            if os.name != "nt":
                # This test covers grant/workspace wiring, not kernel isolation.
                stack.enter_context(patch(
                    "tools.local_runner_agent.terminal_executor.LinuxBubblewrapLauncher",
                    _TestOnlyTerminalLauncher,
                ))
            result = pipeline.run_once()

        if os.name == "nt":
            # Windows AppContainer/LPAC is not implemented. Even a test-injected
            # VERIFIED assessment must not permit a direct host-process fallback.
            self.assertEqual(result["outcome"], "failed", result)
            self.assertEqual(result["job"]["state"], "failed")
            self.assertEqual(result["job"]["error_code"], "RUNNER_POLICY_OR_BUILD_ERROR")
            self.assertEqual(readme.read_text(encoding="utf-8"), "unchanged project workspace\n")
            self.assertEqual(sorted(item.name for item in project_path.iterdir()), ["README.md"])
            return

        self.assertEqual(result["outcome"], "succeeded", result)
        self.assertEqual(result["job"]["id"], job["id"])
        self.assertEqual(result["job"]["state"], "succeeded")
        self.assertEqual(result["result"]["source_type"], "terminal_script")
        self.assertEqual(result["result"]["project_workspace_id"], project["workspace_id"])
        self.assertEqual(result["result"]["template_id"], "python_version")
        self.assertEqual(result["result"]["return_code"], 0)
        self.assertGreater(result["result"]["output_bytes"], 0)
        self.assertEqual(readme.read_text(encoding="utf-8"), "unchanged project workspace\n")
        self.assertEqual(sorted(item.name for item in project_path.iterdir()), ["README.md"])
        self.assertFalse((self.root / "workspaces" / job["id"]).exists())
        with self.grants.db() as db:
            grant_row = db.execute(
                "SELECT job_id,worker_id,consumed_at FROM terminal_grants WHERE grant_id=?",
                (grant["authorization_id"],),
            ).fetchone()
        self.assertEqual(grant_row["job_id"], job["id"])
        self.assertEqual(grant_row["worker_id"], "runner-e2e")
        self.assertIsNotNone(grant_row["consumed_at"])

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
