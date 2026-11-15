"""Hardlink containment across Local Runner copy, snapshot, and artifact paths."""
import errno
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from tools.local_runner_agent.artifacts import ArtifactPackageError, FlutterArtifactPackager
from tools.local_runner_agent.checkout import CheckoutError, LocalProjectCheckout
from tools.local_runner_agent.execution import ExecutionError
from tools.local_runner_agent.file_safety import open_verified_regular_file
from tools.local_runner_agent.local_project import LocalProjectError, LocalProjectRegistry
from tools.local_runner_agent.web_build import WebArtifactPackager, WebBuildExecutor
from tools.local_runner_agent.workspace import WorkspaceManager


class HardlinkTestSupport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspaces = WorkspaceManager(self.root / "workspaces")
        self.job_id = str(uuid.uuid4())
        self.worker_id = "hardlink-containment-test"
        self.workspace = self.workspaces.create(self.job_id, self.worker_id)
        self.source = self.workspace / "source"
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def hardlink(self, original: Path, linked: Path):
        try:
            os.link(original, linked)
        except (NotImplementedError, OSError) as exc:
            unsupported = {
                errno.ENOSYS,
                getattr(errno, "ENOTSUP", errno.EINVAL),
                getattr(errno, "EOPNOTSUPP", errno.EINVAL),
            }
            if getattr(exc, "errno", None) in unsupported or getattr(exc, "winerror", None) in (1, 50):
                self.skipTest("the test filesystem explicitly does not support hardlinks")
            raise


class FileSafetyHardlinkRaceTests(HardlinkTestSupport):
    def test_rejects_hardlink_created_while_source_handle_is_open(self):
        source = self.root / "source.txt"
        source.write_text("sensitive", encoding="utf-8")
        external_alias = self.root / "external-alias.txt"
        with self.assertRaisesRegex(ExecutionError, "hardlinked"):
            with open_verified_regular_file(source, ExecutionError, "test source") as handle:
                self.hardlink(source, external_alias)
                self.assertEqual(handle.read(), b"sensitive")


class FlutterArtifactHardlinkContainmentTests(HardlinkTestSupport):
    def test_rejects_hardlinked_single_file_artifact(self):
        output = self.source / "build" / "app" / "outputs" / "flutter-apk"
        output.mkdir(parents=True)
        outside = self.root / "outside.apk"
        outside.write_bytes(b"private host content")
        self.hardlink(outside, output / "app-release.apk")
        with self.assertRaisesRegex(ArtifactPackageError, "hardlinked"):
            FlutterArtifactPackager(self.workspaces).package(
                self.job_id, self.worker_id, "build_android"
            )

    def test_rejects_hardlinked_file_inside_flutter_archive(self):
        output = self.source / "build" / "web"
        output.mkdir(parents=True)
        outside = self.root / "outside-secret.txt"
        outside.write_text("must never be uploaded", encoding="utf-8")
        self.hardlink(outside, output / "index.html")
        with self.assertRaisesRegex(ArtifactPackageError, "hardlinked"):
            FlutterArtifactPackager(self.workspaces).package(
                self.job_id, self.worker_id, "build_web"
            )


class WebBuildHardlinkContainmentTests(HardlinkTestSupport):
    def test_static_copy_rejects_hardlink_before_copying_external_content(self):
        (self.source / "index.html").write_text("<h1>site</h1>", encoding="utf-8")
        outside = self.root / "outside-public.txt"
        outside.write_text("must never enter dist", encoding="utf-8")
        self.hardlink(outside, self.source / "public.txt")
        executor = WebBuildExecutor(self.workspaces, enabled=True)
        with self.assertRaisesRegex(ExecutionError, "hardlinked"):
            executor.run(self.job_id, self.worker_id, "build_static_web")
        self.assertFalse((self.source / "dist" / "public.txt").exists())

    def test_web_zip_rejects_hardlink_added_after_build(self):
        output = self.source / "dist"
        output.mkdir()
        (output / "index.html").write_text("<h1>built</h1>", encoding="utf-8")
        outside = self.root / "outside-after-build.txt"
        outside.write_text("must never be packaged", encoding="utf-8")
        self.hardlink(outside, output / "late-link.txt")
        with self.assertRaisesRegex(ExecutionError, "hardlinked"):
            WebArtifactPackager(self.workspaces).package(
                self.job_id, self.worker_id, "build_static_web"
            )
        self.assertFalse((self.workspace / ".dcp-artifacts" / "web-build.zip").exists())


class LocalProjectHardlinkContainmentTests(HardlinkTestSupport):
    def _registered_project(self):
        approved = self.root / "approved"
        project = approved / "project"
        project.mkdir(parents=True)
        (project / "app.py").write_text("print('safe')\n", encoding="utf-8")
        registry = LocalProjectRegistry(self.root / "state" / "projects.json")
        root = registry.enroll_root(approved)
        record = registry.register_project(root["root_id"], project)
        return registry, project, record

    def test_registration_fingerprint_rejects_hardlinked_file(self):
        approved = self.root / "approved"
        project = approved / "project"
        project.mkdir(parents=True)
        outside = self.root / "outside.py"
        outside.write_text("private", encoding="utf-8")
        self.hardlink(outside, project / "linked.py")
        registry = LocalProjectRegistry(self.root / "state" / "projects.json")
        root = registry.enroll_root(approved)
        with self.assertRaisesRegex(LocalProjectError, "hardlinked"):
            registry.register_project(root["root_id"], project)

    def test_materialization_rejects_hardlink_added_after_registration(self):
        registry, project, record = self._registered_project()
        outside = self.root / "outside.py"
        outside.write_text("private", encoding="utf-8")
        self.hardlink(outside, project / "late-link.py")
        with self.assertRaisesRegex(LocalProjectError, "hardlinked"):
            registry.materialize_project(
                record["project_id"], self.workspace / "snapshot",
                record["snapshot_sha256"],
            )
        self.assertFalse((self.workspace / "snapshot").exists())

    def test_ignored_secret_hardlink_is_still_rejected(self):
        approved = self.root / "approved"
        project = approved / "project"
        project.mkdir(parents=True)
        outside = self.root / "outside-env"
        outside.write_text("SECRET=value", encoding="utf-8")
        self.hardlink(outside, project / ".env")
        registry = LocalProjectRegistry(self.root / "state" / "projects.json")
        root = registry.enroll_root(approved)
        with self.assertRaisesRegex(LocalProjectError, "hardlinked"):
            registry.register_project(root["root_id"], project)

    def test_local_runner_checkout_rejects_hardlinked_snapshot_file(self):
        snapshot = self.workspace / "manual-snapshot"
        snapshot.mkdir()
        outside = self.root / "outside-checkout.py"
        outside.write_text("private", encoding="utf-8")
        self.hardlink(outside, snapshot / "linked.py")
        checkout = LocalProjectCheckout(
            self.workspaces,
            LocalProjectRegistry(self.root / "state" / "unused-projects.json"),
        )
        with self.assertRaisesRegex(CheckoutError, "hardlinked"):
            checkout._copy_snapshot(snapshot, self.workspace / "source-copy")
        self.assertFalse((self.workspace / "source-copy" / "linked.py").exists())


if __name__ == "__main__":
    unittest.main()
