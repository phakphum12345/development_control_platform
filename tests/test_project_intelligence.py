import tempfile
import unittest
from pathlib import Path

from tools.project_intelligence import DiscoveryError, discover_project
from tools.universal_runner_factory import RunnerProfileError, generate_runner_profile


class ProjectIntelligenceTests(unittest.TestCase):
    def make_project(self, root: Path):
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "src" / "app.py").write_text("print('hello')", encoding="utf-8")
        (root / "tests" / "test_app.py").write_text("def test_ok(): assert True", encoding="utf-8")
        (root / "pyproject.toml").write_text('[project]\ndependencies = ["fastapi", "pytest"]\n', encoding="utf-8")

    def test_detects_python_stack_frameworks_and_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            result = discover_project(root, "Build API and testing workflow")
        self.assertEqual(result["status"], "pass")
        self.assertIn("python", result["runner_profile"]["required_tools"])
        self.assertIn("fastapi", result["inventory"]["frameworks"])
        self.assertIn("pytest", result["inventory"]["frameworks"])
        self.assertEqual(result["runner_profile"]["test_commands"], [["python", "-m", "pytest", "-q"]])
        self.assertIn("testing", result["task"]["detected_topics"])

    def test_ignores_dependency_and_build_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            ignored = root / "node_modules" / "fake"
            ignored.mkdir(parents=True)
            (ignored / "fake.js").write_text("not part of the project", encoding="utf-8")
            result = discover_project(root)
        self.assertNotIn("javascript", result["inventory"]["languages"])

    def test_scan_limit_is_unknown_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(5):
                (root / f"{index}.py").write_text("pass", encoding="utf-8")
            result = discover_project(root, max_files=2)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["inventory"]["truncated"])

    def test_rejects_file_as_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "file.txt"
            file_path.write_text("x", encoding="utf-8")
            with self.assertRaises(DiscoveryError):
                discover_project(file_path)

    def test_runner_profile_is_deterministic_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            assessment = discover_project(root)
        first = generate_runner_profile(assessment, "windows")
        second = generate_runner_profile(assessment, "windows")
        self.assertEqual(first["profile_id"], second["profile_id"])
        self.assertEqual(first["execution"]["mode"], "dry-run")
        self.assertTrue(first["execution"]["owner_approval_required"])
        self.assertFalse(first["execution"]["shell"])

    def test_runner_profile_rejects_shell_operator_arguments(self):
        assessment = {"schema_version": 1, "runner_profile": {
            "required_tools": [], "build_commands": [["python", "x", "&&", "whoami"]], "test_commands": []
        }}
        with self.assertRaises(RunnerProfileError):
            generate_runner_profile(assessment)


if __name__ == "__main__":
    unittest.main(verbosity=2)
