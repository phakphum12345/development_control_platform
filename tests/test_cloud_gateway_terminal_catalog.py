"""Tests for Terminal Studio's inert, curated command catalog."""
import unittest

from tools.cloud_gateway.terminal_catalog import list_templates, preview_template


class TerminalCatalogTests(unittest.TestCase):
    def test_catalog_contains_only_curated_read_only_templates(self):
        rows = list_templates()
        self.assertEqual(
            {row["id"] for row in rows},
            {"git_status", "git_diff", "git_log", "python_version", "node_version"},
        )
        for row in rows:
            with self.subTest(template=row["id"]):
                self.assertIn(row["mutation_class"], {"read-only"})
                self.assertEqual(row["network"], "denied")
                self.assertFalse(row["approval_required"])
                self.assertFalse(row["execution_enabled"])
                self.assertEqual(row["working_directory_policy"], "assigned_workspace_required")
                self.assertIsInstance(row["argv"], list)
                self.assertTrue(row["executable"])

    def test_preview_returns_exact_argv_without_shell_or_execution(self):
        result = preview_template("git_status")
        self.assertEqual(result["command_preview"], ["git", "status", "--short"])
        self.assertEqual(result["status"], "PREVIEW_ONLY")
        self.assertFalse(result["execution_enabled"])
        self.assertNotIn("shell", result)
        self.assertNotIn("cwd", result)
        self.assertNotIn("environment", result)

    def test_unknown_or_untrusted_template_ids_are_rejected(self):
        for value in ("", "../git_status", "git status", "python -c", None, ["git_status"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preview_template(value)

    def test_callers_cannot_mutate_shared_catalog(self):
        first = list_templates()
        first[0]["argv"].append("injected")
        first[0]["environment_allowlist"].append("SECRET")
        second = list_templates()
        self.assertNotIn("injected", second[0]["argv"])
        self.assertNotIn("SECRET", second[0]["environment_allowlist"])


if __name__ == "__main__":
    unittest.main()
