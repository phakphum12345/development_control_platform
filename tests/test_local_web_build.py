"""Tests for the local-first static and Vite build adapters."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.workspace import WorkspaceManager, WorkspaceError
from tools.local_runner_agent.web_build import WebBuildExecutor, WebArtifactPackager
from tools.local_runner_agent.execution import ExecutionError


class WebBuildExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job = "00000000-0000-4000-8000-000000000001"
        self.worker = "web-test"
        self.manager = WorkspaceManager(self.root / "workspaces")
        self.workspace = self.manager.create(self.job, self.worker)
        self.source = self.workspace / "source"
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_static_html_build_copies_real_files_without_execution(self):
        (self.source / "index.html").write_text("<h1>DCP</h1>", encoding="utf-8")
        (self.source / "app.js").write_text("window.test = true", encoding="utf-8")
        (self.source / ".env").write_text("TOKEN=must-not-ship", encoding="utf-8")
        executor = WebBuildExecutor(self.manager, enabled=True)
        result = executor.run(self.job, self.worker, "build_static_web")
        self.assertEqual(result.outcome, "succeeded")
        self.assertEqual(result.return_code, 0)
        self.assertEqual((self.source / "dist" / "index.html").read_text(), "<h1>DCP</h1>")
        self.assertEqual((self.source / "dist" / "app.js").read_text(), "window.test = true")
        self.assertFalse((self.source / "dist" / ".env").exists())

    def test_static_build_rejects_symlink_sources(self):
        (self.source / "index.html").write_text("ok", encoding="utf-8")
        target = self.root / "outside.txt"
        target.write_text("outside", encoding="utf-8")
        try:
            (self.source / "outside.txt").symlink_to(target)
        except OSError:
            self.skipTest("Symlink creation is unavailable on this host")
        with self.assertRaises((ExecutionError, WorkspaceError)):
            WebBuildExecutor(self.manager, enabled=True).run(self.job, self.worker, "build_static_web")

    def test_execution_is_disabled_by_default(self):
        (self.source / "index.html").write_text("ok", encoding="utf-8")
        with self.assertRaises(ExecutionError):
            WebBuildExecutor(self.manager).run(self.job, self.worker, "build_static_web")

    def test_vite_requires_local_cli_and_supported_framework(self):
        (self.source / "package.json").write_text(json.dumps({
            "dependencies": {"react": "^19"}, "devDependencies": {"vite": "^7"}
        }), encoding="utf-8")
        with self.assertRaises(ExecutionError):
            WebBuildExecutor.command_for("build_vite", self.source)
        cli = self.source / "node_modules" / "vite" / "bin"
        cli.mkdir(parents=True)
        (cli / "vite.js").write_text("process.exit(0)", encoding="utf-8")
        command = WebBuildExecutor.command_for("build_vite", self.source)
        self.assertEqual(command[1:], (str(cli / "vite.js"), "build"))

    @unittest.skipIf(os.name == "nt", "POSIX fixture executable used for deterministic Node process test")
    def test_vite_build_runs_fixed_local_cli_and_captures_output(self):
        (self.source / "package.json").write_text(json.dumps({
            "dependencies": {"vue": "^3"}, "devDependencies": {"vite": "^7"}
        }), encoding="utf-8")
        cli = self.source / "node_modules" / "vite" / "bin"
        cli.mkdir(parents=True)
        (cli / "vite.js").write_text("", encoding="utf-8")
        bindir = self.root / "bin"
        bindir.mkdir()
        node = bindir / "node"
        node.write_text("#!/bin/sh\nprintf 'vite-build-ok\\n'\nmkdir -p dist\nprintf '<h1>built</h1>' > dist/index.html\n")
        node.chmod(0o700)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bindir) + os.pathsep + old_path
        try:
            logs = []
            executor = WebBuildExecutor(self.manager, enabled=True, log=lambda s, m: logs.append((s, m)))
            result = executor.run(self.job, self.worker, "build_vite")
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(result.outcome, "succeeded")
        self.assertEqual(result.return_code, 0)
        self.assertTrue(any("vite-build-ok" in message for _, message in logs))
        packaged = WebArtifactPackager(self.manager).package(self.job, self.worker, "build_vite")
        self.assertEqual(packaged[1], "web-build.zip")
        self.assertTrue(packaged[0].is_file())


    def test_next_requires_preinstalled_local_cli_and_react(self):
        (self.source / "package.json").write_text(json.dumps({
            "dependencies": {"next": "^15", "react": "^19"}
        }), encoding="utf-8")
        with self.assertRaises(ExecutionError):
            WebBuildExecutor.command_for("build_next", self.source)
        cli = self.source / "node_modules" / "next" / "dist" / "bin"
        cli.mkdir(parents=True)
        (cli / "next").write_text("", encoding="utf-8")
        command = WebBuildExecutor.command_for("build_next", self.source)
        self.assertEqual(command[1:], (str(cli / "next"), "build"))

    def test_angular_requires_one_application_and_forces_workspace_dist_output(self):
        (self.source / "package.json").write_text(json.dumps({
            "dependencies": {"@angular/core": "^20"},
            "devDependencies": {"@angular/cli": "^20"},
        }), encoding="utf-8")
        (self.source / "angular.json").write_text(json.dumps({
            "projects": {
                "sample-app": {
                    "projectType": "application",
                    "architect": {"build": {"builder": "@angular/build:application"}},
                }
            }
        }), encoding="utf-8")
        cli = self.source / "node_modules" / "@angular" / "cli" / "bin"
        cli.mkdir(parents=True)
        (cli / "ng.js").write_text("", encoding="utf-8")
        command = WebBuildExecutor.command_for("build_angular", self.source)
        self.assertEqual(
            command[1:],
            (str(cli / "ng.js"), "build", "sample-app", "--output-path", "dist"),
        )

    def test_angular_rejects_ambiguous_projects_and_symlinked_cli(self):
        (self.source / "package.json").write_text(json.dumps({
            "dependencies": {"@angular/core": "^20"},
            "devDependencies": {"@angular/cli": "^20"},
        }), encoding="utf-8")
        (self.source / "angular.json").write_text(json.dumps({
            "projects": {
                "app-one": {"projectType": "application", "targets": {"build": {}}},
                "app-two": {"projectType": "application", "targets": {"build": {}}},
            }
        }), encoding="utf-8")
        cli = self.source / "node_modules" / "@angular" / "cli" / "bin"
        cli.mkdir(parents=True)
        (cli / "ng.js").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ExecutionError, "exactly one"):
            WebBuildExecutor.command_for("build_angular", self.source)
        (self.source / "angular.json").write_text(json.dumps({
            "defaultProject": "app-one",
            "projects": {
                "app-one": {"projectType": "application", "targets": {"build": {}}},
                "app-two": {"projectType": "application", "targets": {"build": {}}},
            }
        }), encoding="utf-8")
        self.assertEqual(WebBuildExecutor.command_for("build_angular", self.source)[3], "app-one")

    def test_artifact_packager_uses_framework_specific_output_directories(self):
        for target, output_name in (("build_next", ".next"), ("build_angular", "dist")):
            with self.subTest(target=target):
                output = self.source / output_name
                output.mkdir()
                (output / "BUILD_ID").write_text(target, encoding="utf-8")
                artifact, name = WebArtifactPackager(self.manager).package(
                    self.job, self.worker, target
                )
                self.assertEqual(name, "web-build.zip")
                self.assertTrue(artifact.is_file())
                artifact.unlink()
                import shutil
                shutil.rmtree(output)

    def test_vite_requires_node_and_unknown_framework_is_rejected(self):
        (self.source / "package.json").write_text(json.dumps({"dependencies": {"vite": "^7"}}), encoding="utf-8")
        cli = self.source / "node_modules" / "vite" / "bin"
        cli.mkdir(parents=True)
        (cli / "vite.js").write_text("", encoding="utf-8")
        with self.assertRaises(ExecutionError):
            WebBuildExecutor.command_for("build_vite", self.source)


if __name__ == "__main__":
    unittest.main()
