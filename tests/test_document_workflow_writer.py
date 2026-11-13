"""Security and recovery tests for the controlled local document writer."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.document_workflow.writer import DocumentWriteError, write_document


class DocumentWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "docs").mkdir()
        self.journal = self.base / "state" / "operations.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, **overrides):
        args = {
            "workspace_root": self.workspace,
            "journal_path": self.journal,
            "project_id": "project-alpha",
            "relative_path": "docs/PLAN.md",
            "content": "# Plan\n\n- Status: UNKNOWN\n",
            "operation_key": "operation-00000001",
            "allowed_paths": ["docs"],
        }
        args.update(overrides)
        return write_document(**args)

    def test_create_and_read_back_verify_digest(self):
        result = self.write()
        target = self.workspace / "docs" / "PLAN.md"
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["read_back_verified"])
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), result["sha256"])
        self.assertEqual(result["line_count"], 4)

    def test_reconcile_file_written_before_journal_commit(self):
        content = "# Recovered\\n"
        target = self.workspace / "docs" / "PLAN.md"
        target.write_text(content, encoding="utf-8")
        result = self.write(content=content, operation_key="operation-recovery-01")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["operation"], "DOCUMENT_WRITE_RECOVERED")
        self.assertTrue(result["read_back_verified"])

    def test_idempotent_retry_does_not_create_duplicate_operation(self):
        first = self.write()
        second = self.write()
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(second["operation"], "DOCUMENT_WRITE_RECONCILED")

    def test_update_requires_exact_existing_digest(self):
        target = self.workspace / "docs" / "PLAN.md"
        target.write_text("old\n", encoding="utf-8")
        old_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        result = self.write(content="new\n", expected_sha256=old_sha)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(target.read_text(encoding="utf-8"), "new\n")

    def test_stale_base_is_rejected_without_modifying_file(self):
        target = self.workspace / "docs" / "PLAN.md"
        target.write_text("old\n", encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaises(DocumentWriteError):
            self.write(content="new\n", expected_sha256="0" * 64)
        self.assertEqual(target.read_bytes(), before)

    def test_scope_escape_is_rejected(self):
        with self.assertRaises(DocumentWriteError):
            self.write(relative_path="outside/PLAN.md")

    def test_path_traversal_and_absolute_paths_are_rejected(self):
        for path in ("../PLAN.md", str(self.workspace / "docs" / "PLAN.md")):
            with self.subTest(path=path), self.assertRaises(DocumentWriteError):
                self.write(relative_path=path)

    def test_symlink_target_is_rejected(self):
        outside = self.base / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        link = self.workspace / "docs" / "LINK.md"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are unavailable on this platform.")
        with self.assertRaises(DocumentWriteError):
            self.write(relative_path="docs/LINK.md")

    def test_only_markdown_and_text_are_allowed(self):
        with self.assertRaises(DocumentWriteError):
            self.write(relative_path="docs/code.py")

    def test_operation_key_cannot_be_reused_for_different_content(self):
        self.write()
        with self.assertRaises(DocumentWriteError):
            self.write(content="# Different plan")

    def test_journal_must_be_outside_workspace(self):
        with self.assertRaises(DocumentWriteError):
            self.write(journal_path=self.workspace / ".dcp-state.sqlite3")


if __name__ == "__main__":
    unittest.main()
