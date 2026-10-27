"""Contract tests for the DCP-owned MCP engine core."""
import tempfile
import unittest
from pathlib import Path

from tools.mcp_engine.engine import (
    EngineError, copy_apply, copy_preview, diff_files, inspect_file,
)


class NativeEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.src = self.base / "src"
        self.dst = self.base / "dst"
        self.src.mkdir()
        self.dst.mkdir()
        (self.src / "hello.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        (self.dst / "hello.txt").write_text("alpha\ngamma\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspect_reports_sha_and_read_only(self):
        result = inspect_file(self.src, "hello.txt")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["sha256"]), 64)
        self.assertEqual(result["operation"], "READ_ONLY")

    def test_diff_reports_unified_changes(self):
        result = diff_files(self.src, "hello.txt", self.dst, "hello.txt")
        self.assertFalse(result["equal"])
        self.assertEqual(result["diff_type"], "unified")
        self.assertIn("-beta", result["diff"])
        self.assertIn("+gamma", result["diff"])

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(EngineError):
            inspect_file(self.src, "../dst/hello.txt")

    def test_absolute_path_is_rejected(self):
        with self.assertRaises(EngineError):
            inspect_file(self.src, str(self.src / "hello.txt"))

    def test_copy_preview_never_writes(self):
        result = copy_preview(self.src, "hello.txt", self.dst, "copy.txt")
        self.assertFalse(result["writes_performed"])
        self.assertFalse((self.dst / "copy.txt").exists())

    def test_copy_apply_creates_new_file_and_verifies_hash(self):
        result = copy_apply(self.src, "hello.txt", self.dst, "copy.txt")
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["writes_performed"])
        self.assertEqual(result["source_sha256"], result["destination_sha256"])
        self.assertEqual((self.dst / "copy.txt").read_text(encoding="utf-8"), "alpha\nbeta\n")

    def test_existing_destination_is_never_overwritten(self):
        before = (self.dst / "hello.txt").read_bytes()
        with self.assertRaises(EngineError):
            copy_apply(self.src, "hello.txt", self.dst, "hello.txt")
        self.assertEqual((self.dst / "hello.txt").read_bytes(), before)

    def test_destination_traversal_is_rejected(self):
        with self.assertRaises(EngineError):
            copy_preview(self.src, "hello.txt", self.dst, "../escape.txt")

    def test_binary_diff_returns_metadata_not_garbled_text(self):
        (self.src / "blob.bin").write_bytes(b"\x00\xff")
        (self.dst / "blob.bin").write_bytes(b"\x00\xfe")
        result = diff_files(self.src, "blob.bin", self.dst, "blob.bin")
        self.assertEqual(result["diff_type"], "binary")
        self.assertIsNone(result["diff"])

    def test_oversized_files_are_rejected(self):
        import tools.mcp_engine.engine as engine
        original_limit = engine.MAX_FILE_BYTES
        try:
            engine.MAX_FILE_BYTES = 2
            with self.assertRaises(EngineError):
                inspect_file(self.src, "hello.txt")
        finally:
            engine.MAX_FILE_BYTES = original_limit


if __name__ == "__main__":
    unittest.main()
