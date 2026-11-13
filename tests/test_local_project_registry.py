"""Tests for explicit Local Folder enrollment and source fingerprints."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.local_project import (
    LocalProjectError,
    LocalProjectRegistry,
)


class LocalProjectRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.approved = self.base / "approved"
        self.approved.mkdir()
        self.project = self.approved / "web-app"
        self.project.mkdir()
        (self.project / "index.html").write_text("<h1>hello</h1>\n", encoding="utf-8")
        (self.project / "src").mkdir()
        (self.project / "src" / "app.js").write_text("console.log('hello');\n", encoding="utf-8")
        self.registry_path = self.base / "state" / "projects.json"
        self.registry = LocalProjectRegistry(self.registry_path)
        self.root = self.registry.enroll_root(self.approved)

    def tearDown(self):
        self.temp.cleanup()

    def test_enrolls_root_and_registers_project_without_executing_source(self):
        registered = self.registry.register_project(self.root["root_id"], self.project)
        self.assertEqual(registered["relative_path"], "web-app")
        self.assertEqual(len(registered["workspace_id"]), 36)
        self.assertEqual(registered["file_count"], 2)
        self.assertEqual(registered["total_bytes"], len(
            (self.project / "index.html").read_bytes()
            + (self.project / "src" / "app.js").read_bytes()
        ))
        self.assertEqual(len(registered["snapshot_sha256"]), 64)
        self.assertEqual(self.registry.get_project(registered["project_id"]), registered)

    def test_duplicate_root_and_project_registration_are_idempotent(self):
        duplicate_root = self.registry.enroll_root(self.approved)
        self.assertEqual(duplicate_root["root_id"], self.root["root_id"])
        first = self.registry.register_project(self.root["root_id"], self.project)
        second = self.registry.register_project(self.root["root_id"], self.project)
        self.assertEqual(first["project_id"], second["project_id"])
        self.assertEqual(first["workspace_id"], second["workspace_id"])

    def test_registry_persists_roots_and_projects(self):
        project = self.registry.register_project(self.root["root_id"], self.project)
        loaded = LocalProjectRegistry(self.registry_path)
        self.assertEqual(loaded.get_project(project["project_id"]), project)
        if os.name != "nt":
            self.assertEqual(self.registry_path.stat().st_mode & 0o777, 0o600)

    def test_legacy_project_record_is_migrated_to_stable_workspace_id(self):
        project = self.registry.register_project(self.root["root_id"], self.project)
        legacy = dict(project)
        legacy.pop("project_id")
        legacy.pop("workspace_id")
        self.registry_path.write_text(json.dumps({
            "version": 1,
            "roots": {self.root["root_id"]: self.registry._data["roots"][self.root["root_id"]]},
            "projects": {project["project_id"]: legacy},
        }), encoding="utf-8")
        loaded = LocalProjectRegistry(self.registry_path)
        migrated = loaded.get_project(project["project_id"])
        self.assertEqual(len(migrated["workspace_id"]), 36)
        persisted = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["projects"][project["project_id"]]["workspace_id"], migrated["workspace_id"])

    def test_rejects_unenrolled_root_and_project_outside_root(self):
        with self.assertRaises(LocalProjectError):
            self.registry.register_project("missing-root", self.project)
        outside = self.base / "outside"
        outside.mkdir()
        with self.assertRaises(LocalProjectError):
            self.registry.register_project(self.root["root_id"], outside)

    def test_requires_project_beneath_root_not_the_root_itself(self):
        with self.assertRaises(LocalProjectError):
            self.registry.register_project(self.root["root_id"], self.approved)

    def test_refresh_changes_fingerprint_when_source_changes(self):
        first = self.registry.register_project(self.root["root_id"], self.project)
        (self.project / "index.html").write_text("<h1>changed</h1>\n", encoding="utf-8")
        refreshed = self.registry.refresh_project(first["project_id"])
        self.assertEqual(refreshed["project_id"], first["project_id"])
        self.assertEqual(refreshed["workspace_id"], first["workspace_id"])
        self.assertNotEqual(refreshed["snapshot_sha256"], first["snapshot_sha256"])

    def test_ignores_known_generated_directories(self):
        ignored = self.project / "node_modules"
        ignored.mkdir()
        (ignored / "large.bin").write_bytes(b"x" * 100)
        first = self.registry.register_project(self.root["root_id"], self.project)
        (ignored / "large.bin").write_bytes(b"y" * 100)
        refreshed = self.registry.refresh_project(first["project_id"])
        self.assertEqual(first["snapshot_sha256"], refreshed["snapshot_sha256"])

    def test_rejects_nested_symlinks_and_special_entries(self):
        target = self.base / "outside.txt"
        target.write_text("outside")
        link = self.project / "linked.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        with self.assertRaises(LocalProjectError):
            self.registry.register_project(self.root["root_id"], self.project)

    def test_enforces_file_and_byte_limits(self):
        limited = LocalProjectRegistry(self.base / "limited.json", max_files=1, max_bytes=16)
        root = limited.enroll_root(self.approved)
        with self.assertRaises(LocalProjectError):
            limited.register_project(root["root_id"], self.project)

    def test_rejects_symlink_registry_and_selected_project(self):
        link = self.base / "project-link"
        try:
            link.symlink_to(self.project, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        with self.assertRaises(LocalProjectError):
            self.registry.register_project(self.root["root_id"], link)
        registry_link = self.base / "registry-link.json"
        registry_link.symlink_to(self.registry_path)
        with self.assertRaises(LocalProjectError):
            LocalProjectRegistry(registry_link)

    def test_rejects_corrupt_registry(self):
        self.registry_path.write_text(json.dumps({"version": 99}), encoding="utf-8")
        with self.assertRaises(LocalProjectError):
            LocalProjectRegistry(self.registry_path)


if __name__ == "__main__":
    unittest.main()
