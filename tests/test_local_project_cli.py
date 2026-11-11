"""CLI tests for explicit Local Folder enrollment; no Gateway or execution involved."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.local_runner_agent.__main__ import main


class LocalProjectCLITests(unittest.TestCase):
    def test_enroll_register_and_list_are_local_only(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            allowed = base / "allowed"
            project = allowed / "demo"
            project.mkdir(parents=True)
            (project / "index.html").write_text("hello", encoding="utf-8")
            registry_path = base / "state" / "projects.json"
            env = {"DCP_LOCAL_PROJECT_REGISTRY": str(registry_path)}
            output = io.StringIO()
            with patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(output):
                self.assertEqual(main(["--enroll-root", str(allowed)]), 0)
                root = json.loads(output.getvalue())
                output.seek(0)
                output.truncate(0)
                self.assertEqual(main(["--register-project", root["root_id"], str(project)]), 0)
                registered = json.loads(output.getvalue())
                output.seek(0)
                output.truncate(0)
                self.assertEqual(main(["--list-projects"]), 0)
                listed = json.loads(output.getvalue())

            self.assertEqual(registered["project_id"], listed["projects"][0]["project_id"])
            self.assertEqual(listed["roots"][0]["root_id"], root["root_id"])
            self.assertTrue(registry_path.is_file())

    def test_invalid_project_path_fails_without_gateway_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            registry_path = Path(temp) / "projects.json"
            with patch.dict(os.environ, {"DCP_LOCAL_PROJECT_REGISTRY": str(registry_path)}, clear=False):
                self.assertEqual(main(["--register-project", "missing-root", str(Path(temp))]), 1)


if __name__ == "__main__":
    unittest.main()
