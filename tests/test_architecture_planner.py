import tempfile
import unittest
from pathlib import Path

from tools.project_intelligence import discover_project
from tools.architecture_planner import PlanningError, plan_implementation


class ArchitecturePlannerTests(unittest.TestCase):
    def test_creates_task_specific_plan_with_review_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "api.py").write_text("pass", encoding="utf-8")
            (root / "tests" / "test_api.py").write_text("pass", encoding="utf-8")
            (root / "requirements.txt").write_text("fastapi\npytest\n", encoding="utf-8")
            assessment = discover_project(root)
        plan = plan_implementation(assessment, "Add secure API runner tests")
        self.assertEqual(plan["status"], "proposed")
        self.assertIn("security", plan["detected_topics"])
        self.assertIn("api", plan["detected_topics"])
        self.assertIn("runner", plan["detected_topics"])
        self.assertEqual(plan["steps"][-1]["gate"], "owner-review")
        self.assertEqual(plan["approval_boundaries"]["merge_deploy"], "human-only")

    def test_rejects_missing_task(self):
        with self.assertRaises(PlanningError):
            plan_implementation({"schema_version": 1, "inventory": {}, "runner_profile": {}}, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
