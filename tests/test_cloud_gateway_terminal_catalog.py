"""Tests for Terminal Studio's inert, curated command catalog."""
import unittest

from tools.cloud_gateway.terminal_catalog import list_templates, preview_template


class TerminalCatalogTests(unittest.TestCase):
    def test_catalog_contains_only_curated_read_only_templates(self):
        rows = list_templates()
        self.assertEqual(
            {row["id"] for row in rows},
            {"git_status", "git_diff", "git_log", "git_show_commit", "git_diff_commit", "python_version", "node_version"},
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


    def test_visual_builder_git_log_limit_is_typed_and_bounded(self):
        default = preview_template("git_log")
        self.assertEqual(default["argv"], ["log", "-5", "--oneline", "--decorate"])
        custom = preview_template("git_log", {"limit": 20})
        self.assertEqual(custom["argv"], ["log", "-20", "--oneline", "--decorate"])
        self.assertEqual(custom["parameter_values"], {"limit": "20"})
        for value in (0, 51, True, "-1", "1;whoami", "1.5", []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preview_template("git_log", {"limit": value})
        with self.assertRaisesRegex(ValueError, "unknown command parameter"):
            preview_template("git_log", {"limit": 5, "shell": "whoami"})

    def test_visual_builder_commit_inputs_require_exact_full_sha(self):
        sha = "a" * 40
        show = preview_template("git_show_commit", {"commit_sha": sha})
        self.assertEqual(show["argv"], ["show", "--no-ext-diff", "--stat", "--oneline", sha])
        diff = preview_template("git_diff_commit", {"commit_sha": sha})
        self.assertEqual(diff["argv"], ["diff", "--no-ext-diff", "--no-color", sha, "--"])
        self.assertEqual(show["network"], "denied")
        self.assertFalse(show["execution_enabled"])
        for value in ("a" * 39, "a" * 41, "a" * 39 + "g", "a" * 39 + " "):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preview_template("git_show_commit", {"commit_sha": value})
        with self.assertRaisesRegex(ValueError, "missing required parameter"):
            preview_template("git_show_commit")
        with self.assertRaisesRegex(ValueError, "parameters must be an object"):
            preview_template("git_show_commit", [])


    def test_callers_cannot_mutate_shared_catalog(self):
        first = list_templates()
        first[0]["argv"].append("injected")
        first[0]["environment_allowlist"].append("SECRET")
        second = list_templates()
        self.assertNotIn("injected", second[0]["argv"])
        self.assertNotIn("SECRET", second[0]["environment_allowlist"])


if __name__ == "__main__":
    unittest.main()
