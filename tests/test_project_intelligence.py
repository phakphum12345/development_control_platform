import json
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


    def test_detects_react_vite_node_requirements_and_scripts_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({
                "dependencies": {"react": "^19", "react-dom": "^19"},
                "devDependencies": {"vite": "^7"},
                "scripts": {"build": "vite build", "test": "vitest"},
                "engines": {"node": ">=20"},
            }), encoding="utf-8")
            (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            result = discover_project(root)
        detected = result["inventory"]["framework_detection"]
        self.assertEqual(detected["framework"], "React + Vite")
        self.assertEqual(detected["package_manager"], "pnpm")
        self.assertEqual(detected["toolchain_requirements"]["node"], ">=20")
        self.assertEqual(detected["build_scripts"], ["build"])
        self.assertEqual(detected["test_scripts"], ["test"])
        self.assertFalse(detected["execution_performed"])
        self.assertEqual(detected["toolchain_readiness"], "NOT_CHECKED")

    def test_detects_vue_nextjs_and_angular(self):
        cases = [
            ({"dependencies": {"vue": "^3", "vite": "^6"}}, "Vue + Vite"),
            ({"dependencies": {"next": "^15", "react": "^19"}}, "Next.js"),
            ({"devDependencies": {"@angular/core": "^20"}}, "Angular"),
        ]
        for package, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
                self.assertEqual(discover_project(root)["inventory"]["framework_detection"]["framework"], expected)

    def test_detects_flutter_python_and_static_web(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pubspec.yaml").write_text(
                "name: sample\ndependencies:\n  flutter:\n    sdk: flutter\n"
                "environment:\n  sdk: '>=3.4.0 <4.0.0'\n", encoding="utf-8"
            )
            self.assertEqual(discover_project(root)["inventory"]["framework_detection"]["framework"], "Flutter")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                '[project]\nrequires-python = ">=3.11"\ndependencies = ["fastapi>=0.100"]\n',
                encoding="utf-8"
            )
            detected = discover_project(root)["inventory"]["framework_detection"]
            self.assertEqual(detected["framework"], "FastAPI")
            self.assertEqual(detected["toolchain_requirements"]["python"], ">=3.11")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<h1>static</h1>", encoding="utf-8")
            self.assertEqual(discover_project(root)["inventory"]["framework_detection"]["framework"], "Static HTML/CSS/JS")

    def test_inventory_excludes_secret_and_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<h1>safe</h1>", encoding="utf-8")
            (root / ".env").write_text("TOKEN=never-index", encoding="utf-8")
            (root / ".env.local").write_text("PASSWORD=never-index", encoding="utf-8")
            (root / "id_rsa").write_text("PRIVATE KEY", encoding="utf-8")
            (root / "service-account-prod.json").write_text('{"private_key":"never-index"}', encoding="utf-8")
            (root / ".env.example").write_text("API_URL=https://example.invalid", encoding="utf-8")
            result = discover_project(root)
            samples = result["inventory"]["sample_files"]
            self.assertIn(".env.example", samples)
            self.assertNotIn(".env", samples)
            self.assertNotIn(".env.local", samples)
            self.assertNotIn("id_rsa", samples)
            self.assertNotIn("service-account-prod.json", samples)
            self.assertEqual(result["inventory"]["file_count"], 2)

    def test_framework_detection_reports_unknown_and_does_not_infer_toolchain_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("unknown project", encoding="utf-8")
            detected = discover_project(root)["inventory"]["framework_detection"]
        self.assertEqual(detected["framework"], "UNKNOWN")
        self.assertEqual(detected["confidence"], "unknown")
        self.assertEqual(detected["toolchain_readiness"], "NOT_CHECKED")


    def test_framework_detection_does_not_follow_symlinked_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "external-angular.json"
            target.write_text("{}", encoding="utf-8")
            (root / "angular.json").symlink_to(target)
            detected = discover_project(root)["inventory"]["framework_detection"]
        self.assertEqual(detected["framework"], "UNKNOWN")
        self.assertNotIn("angular.json", detected["evidence"])

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
