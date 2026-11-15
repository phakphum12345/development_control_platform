"""Artifact packaging must never turn a host hardlink into an upload."""
import errno
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
import uuid
from pathlib import Path

from tools.local_runner_agent.artifacts import ArtifactPackageError, FlutterArtifactPackager
from tools.local_runner_agent.execution import ExecutionError
from tools.local_runner_agent.file_safety import open_verified_regular_file
from tools.local_runner_agent.workspace import WorkspaceManager


class FlutterArtifactHardlinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job_id = str(uuid.uuid4())
        self.worker_id = "artifact-hardlink-test"
        self.workspaces = WorkspaceManager(self.root / "workspaces")
        self.workspace = self.workspaces.create(self.job_id, self.worker_id)
        self.source = self.workspace / "source"
        self.source.mkdir()
        self.packager = FlutterArtifactPackager(self.workspaces)

    def tearDown(self):
        self.temp.cleanup()

    def _hardlink(self, source: Path, destination: Path):
        try:
            os.link(source, destination)
        except (OSError, NotImplementedError) as exc:
            unsupported = {
                errno.ENOSYS,
                getattr(errno, "ENOTSUP", errno.EINVAL),
                getattr(errno, "EOPNOTSUPP", errno.EINVAL),
            }
            if isinstance(exc, NotImplementedError) or getattr(exc, "errno", None) in unsupported or getattr(exc, "winerror", None) in (1, 50):
                self.skipTest("the test filesystem explicitly does not support hardlinks")
            raise

    def test_web_archive_rejects_hardlinked_host_file(self):
        output = self.source / "build" / "web"
        output.mkdir(parents=True)
        outside = self.root / "outside-secret.txt"
        outside.write_text("must-not-be-uploaded", encoding="utf-8")
        self._hardlink(outside, output / "index.html")
        with self.assertRaisesRegex(ArtifactPackageError, "hardlinked"):
            self.packager.package(self.job_id, self.worker_id, "build_web")

    def test_zip_packager_rejects_hardlink_added_after_scan(self):
        output = self.source / "build" / "web"
        output.mkdir(parents=True)
        artifact = output / "index.html"
        artifact.write_text("<h1>built</h1>", encoding="utf-8")
        external = self.root / "external-alias.html"
        original_open = open_verified_regular_file

        @contextmanager
        def inject_link_after_open(path, error_type, label):
            with original_open(path, error_type, label) as handle:
                if Path(path) == artifact:
                    self._hardlink(artifact, external)
                yield handle

        with patch("tools.local_runner_agent.artifacts.open_verified_regular_file", inject_link_after_open):
            with self.assertRaisesRegex(ArtifactPackageError, "hardlinked"):
                self.packager.package(self.job_id, self.worker_id, "build_web")
        self.assertFalse((self.workspace / ".dcp-artifacts" / "flutter-web-build.zip").exists())

    def test_single_file_copy_rejects_hardlink_added_after_precheck(self):
        output = self.source / "build" / "app" / "outputs" / "flutter-apk"
        output.mkdir(parents=True)
        artifact = output / "app-release.apk"
        artifact.write_bytes(b"private artifact bytes")
        external = self.root / "external-alias.apk"
        original_open = open_verified_regular_file

        @contextmanager
        def inject_link_after_open(path, error_type, label):
            with original_open(path, error_type, label) as handle:
                if Path(path) == artifact:
                    self._hardlink(artifact, external)
                yield handle

        with patch("tools.local_runner_agent.file_safety.open_verified_regular_file", inject_link_after_open):
            with self.assertRaisesRegex(ArtifactPackageError, "hardlinked"):
                self.packager.package(self.job_id, self.worker_id, "build_android")
        self.assertFalse((self.workspace / ".dcp-artifacts" / "app-release.apk").exists())

    def test_single_file_artifact_rejects_hardlinked_host_file(self):
        output = self.source / "build" / "app" / "outputs" / "flutter-apk"
        output.mkdir(parents=True)
        outside = self.root / "outside-secret.apk"
        outside.write_bytes(b"must-not-be-uploaded")
        self._hardlink(outside, output / "app-release.apk")
        with self.assertRaisesRegex(ArtifactPackageError, "hardlinked"):
            self.packager.package(self.job_id, self.worker_id, "build_android")


if __name__ == "__main__":
    unittest.main()
