from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.windows_psec_projection import (
    ProjectionError,
    ProjectionLimits,
    create_workspace_projection,
)


class WindowsPsecProjectionTests(unittest.TestCase):
    def _roots(self, parent: Path):
        source = parent / "source"
        private = parent / "private"
        source.mkdir()
        private.mkdir()
        return source, private

    def test_projection_copies_files_and_verifies_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            (source / "src").mkdir()
            (source / "src" / "main.py").write_text("print('safe')", encoding="utf-8")
            (source / "README.md").write_text("hello", encoding="utf-8")

            projection = create_workspace_projection(source, private)
            try:
                self.assertEqual(
                    (projection.workspace / "src" / "main.py").read_text(encoding="utf-8"),
                    "print('safe')",
                )
                self.assertEqual(
                    (projection.workspace / "README.md").read_text(encoding="utf-8"),
                    "hello",
                )
                self.assertTrue((projection.scratch).is_dir())
                self.assertEqual(len(projection.manifest), 3)
                self.assertEqual(len(projection.manifest_sha256), 64)
            finally:
                projection.close()
            self.assertFalse(projection.root.exists())

    def test_projection_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            outside = Path(temporary) / "outside.txt"
            outside.write_text("not in workspace", encoding="utf-8")
            try:
                (source / "escape.txt").symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")
            with self.assertRaisesRegex(ProjectionError, "reparse point|symlink"):
                create_workspace_projection(source, private)

    def test_projection_rejects_reserved_names_and_ads(self):
        for name in ("CON", "NUL.txt", "report:stream"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                source, private = self._roots(Path(temporary))
                (source / name).write_text("bad", encoding="utf-8")
                with self.assertRaises(ProjectionError):
                    create_workspace_projection(source, private)

    def test_projection_rejects_case_insensitive_collisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            (source / "Readme.txt").write_text("one", encoding="utf-8")
            (source / "README.txt").write_text("two", encoding="utf-8")
            with self.assertRaisesRegex(ProjectionError, "collision"):
                create_workspace_projection(source, private)

    def test_projection_enforces_file_and_total_byte_limits(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            (source / "large.bin").write_bytes(b"x" * 16)
            with self.assertRaisesRegex(ProjectionError, "per-file"):
                create_workspace_projection(
                    source, private, limits=ProjectionLimits(max_file_bytes=8)
                )
            with self.assertRaisesRegex(ProjectionError, "byte limit"):
                create_workspace_projection(
                    source, private,
                    limits=ProjectionLimits(max_file_bytes=32, max_total_bytes=8),
                )

    def test_projection_bounds_directory_entries_not_only_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            for index in range(4):
                (source / f"directory-{index}").mkdir()
            with self.assertRaisesRegex(ProjectionError, "filesystem-entry limit"):
                create_workspace_projection(
                    source, private,
                    limits=ProjectionLimits(max_entries=3),
                )

    def test_projection_rejects_source_and_private_parent_overlap(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            with self.assertRaisesRegex(ProjectionError, "disjoint"):
                create_workspace_projection(source, source)

    def test_close_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            (source / "file.txt").write_text("value", encoding="utf-8")
            projection = create_workspace_projection(source, private)
            projection.close()
            projection.close()
            self.assertFalse(projection.root.exists())


if __name__ == "__main__":
    unittest.main()
