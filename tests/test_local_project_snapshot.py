"""Immutable-by-fingerprint Local Folder snapshot materialization tests."""
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from tools.local_runner_agent.checkout import CheckoutError, LocalProjectCheckout
from tools.local_runner_agent.workspace import WorkspaceManager
from tools.local_runner_agent.local_project import (
    LocalProjectError,
    LocalProjectRegistry,
)


class LocalProjectSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.allowed = self.base / "approved"
        self.project = self.allowed / "web-app"
        (self.project / "src").mkdir(parents=True)
        (self.project / "index.html").write_text("<h1>snapshot</h1>\n", encoding="utf-8")
        (self.project / "src" / "app.js").write_text("console.log('snapshot');\n", encoding="utf-8")
        self.registry = LocalProjectRegistry(self.base / "state" / "projects.json")
        self.root = self.registry.enroll_root(self.allowed)
        self.project_record = self.registry.register_project(self.root["root_id"], self.project)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.workspaces = WorkspaceManager(self.base / "workspaces")
        self.job_id = str(uuid.uuid4())
        self.worker_id = "local-project-runner"
        self.workspaces.create(self.job_id, self.worker_id)

    def tearDown(self):
        self.temp.cleanup()

    def test_materializes_verified_copy_with_matching_fingerprint(self):
        destination = self.workspace / "source-snapshot"
        result = self.registry.materialize_project(
            self.project_record["project_id"],
            destination,
            self.project_record["snapshot_sha256"],
        )
        self.assertEqual(result["snapshot_sha256"], self.project_record["snapshot_sha256"])
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["total_bytes"], self.project_record["total_bytes"])
        self.assertTrue(result["read_only_permissions_applied"])
        self.assertFalse(result["os_sandbox"])
        self.assertEqual(
            (destination / "index.html").read_text(encoding="utf-8"),
            (self.project / "index.html").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (destination / "src" / "app.js").read_text(encoding="utf-8"),
            (self.project / "src" / "app.js").read_text(encoding="utf-8"),
        )
        if os.name != "nt":
            self.assertEqual((destination / "index.html").stat().st_mode & 0o777, 0o400)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o500)

    def test_snapshot_is_independent_from_later_source_edits(self):
        destination = self.workspace / "source-snapshot"
        self.registry.materialize_project(
            self.project_record["project_id"],
            destination,
            self.project_record["snapshot_sha256"],
        )
        (self.project / "index.html").write_text("<h1>changed after snapshot</h1>\n", encoding="utf-8")
        self.assertEqual((destination / "index.html").read_text(encoding="utf-8"), "<h1>snapshot</h1>\n")
        self.assertNotEqual(
            self.registry._fingerprint(self.project)[0],
            self.registry._fingerprint(destination)[0],
        )

    def test_local_checkout_preserves_read_only_snapshot_and_creates_writable_build_copy(self):
        checkout = LocalProjectCheckout(self.workspaces, self.registry)
        source, metadata = checkout.checkout(
            self.job_id, self.worker_id, self.project_record["project_id"],
            self.project_record["snapshot_sha256"],
        )
        snapshot = self.workspaces.get(self.job_id, self.worker_id) / "source-snapshot"
        self.assertEqual(metadata["snapshot_sha256"], self.project_record["snapshot_sha256"])
        self.assertEqual(self.registry._fingerprint(source)[0], self.project_record["snapshot_sha256"])
        self.assertEqual((source / "index.html").read_text(encoding="utf-8").strip(), "<h1>snapshot</h1>")
        (source / "index.html").write_text("<h1>built copy</h1>", encoding="utf-8")
        self.assertEqual((snapshot / "index.html").read_text(encoding="utf-8").strip(), "<h1>snapshot</h1>")

    def test_local_checkout_refuses_changed_source_before_build_copy(self):
        (self.project / "index.html").write_text("changed", encoding="utf-8")
        checkout = LocalProjectCheckout(self.workspaces, self.registry)
        with self.assertRaises(CheckoutError):
            checkout.checkout(
                self.job_id, self.worker_id, self.project_record["project_id"],
                self.project_record["snapshot_sha256"],
            )
        workspace = self.workspaces.get(self.job_id, self.worker_id)
        self.assertFalse((workspace / "source").exists())

    def test_refuses_source_changed_after_registration(self):
        (self.project / "index.html").write_text("edited", encoding="utf-8")
        destination = self.workspace / "must-not-exist"
        with self.assertRaisesRegex(LocalProjectError, "changed after it was registered"):
            self.registry.materialize_project(
                self.project_record["project_id"],
                destination,
                self.project_record["snapshot_sha256"],
            )
        self.assertFalse(destination.exists())

    def test_refuses_wrong_expected_fingerprint(self):
        destination = self.workspace / "must-not-exist"
        with self.assertRaisesRegex(LocalProjectError, "no longer matches"):
            self.registry.materialize_project(
                self.project_record["project_id"], destination, "0" * 64
            )
        self.assertFalse(destination.exists())

    def test_refuses_existing_destination_without_overwriting(self):
        destination = self.workspace / "existing"
        destination.mkdir()
        marker = destination / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(LocalProjectError, "already exists"):
            self.registry.materialize_project(
                self.project_record["project_id"],
                destination,
                self.project_record["snapshot_sha256"],
            )
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_refuses_symlink_in_source_and_cleans_partial_snapshot(self):
        outside = self.base / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.project / "linked.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        destination = self.workspace / "must-be-cleaned"
        with self.assertRaises(LocalProjectError):
            self.registry.materialize_project(
                self.project_record["project_id"],
                destination,
                self.project_record["snapshot_sha256"],
            )
        self.assertFalse(destination.exists())

    def test_refuses_symlink_destination_parent(self):
        outside = self.base / "outside"
        outside.mkdir()
        link = self.workspace / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        destination = link / "snapshot"
        with self.assertRaises(LocalProjectError):
            self.registry.materialize_project(
                self.project_record["project_id"],
                destination,
                self.project_record["snapshot_sha256"],
            )
        self.assertFalse((outside / "snapshot").exists())


if __name__ == "__main__":
    unittest.main()
