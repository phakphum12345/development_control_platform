from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.windows_psec_projection import (
    ProjectionError,
    ProjectionLimits,
    create_workspace_projection,
    _ensure_unique_names,
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
        for name in ("CON", "NUL.txt"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                source, private = self._roots(Path(temporary))
                (source / name).write_text("bad", encoding="utf-8")
                with self.assertRaises(ProjectionError):
                    create_workspace_projection(source, private)

        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            base = source / "report"
            base.write_text("ordinary stream", encoding="utf-8")
            if os.name == "nt":
                # On NTFS this creates a named stream attached to "report";
                # it does not create a directory entry named "report:stream".
                Path(str(base) + ":stream").write_text("hidden", encoding="utf-8")
            else:
                # Other filesystems can represent the colon as a filename
                # component, which the Windows path validator must reject.
                (source / "report:stream").write_text("hidden", encoding="utf-8")
            with self.assertRaisesRegex(ProjectionError, "alternate data stream|invalid Windows"):
                create_workspace_projection(source, private)

    def test_projection_rejects_case_insensitive_collisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, private = self._roots(Path(temporary))
            first = source / "Readme.txt"
            second = source / "README.txt"
            first.write_text("one", encoding="utf-8")
            if second.exists():
                # Case-insensitive filesystems cannot materialize both names;
                # exercise the exact directory-name validation independently.
                with self.assertRaisesRegex(ProjectionError, "collision"):
                    _ensure_unique_names(["Readme.txt", "README.txt"])
            else:
                second.write_text("two", encoding="utf-8")
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
