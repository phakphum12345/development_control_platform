import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


class DashboardContractTests(unittest.TestCase):
    def test_all_tool_views_exist(self):
        for view in ("home", "repo", "pr", "user", "evidence", "gates", "checkpoint", "audit"):
            with self.subTest(view=view):
                self.assertIn('id="' + view + '"', HTML)
        for control in ("repo-load", "pr-load", "user-load", "ev-check", "gate-eval", "cp-build", "audit-eval"):
            with self.subTest(control=control):
                self.assertIn('id="' + control + '"', HTML)

    def test_github_requests_are_public_read_only(self):
        self.assertIn("https://api.github.com", HTML)
        self.assertIn("PUBLIC API", HTML)
        self.assertIn("No token", HTML)
        self.assertIn("private repository access", HTML.lower())
        self.assertIn("does not prove", HTML)

    def test_evidence_requires_full_sha_and_url_for_pass(self):
        self.assertIn("40 hex characters", HTML)
        self.assertIn('r.status==="pass"&&!r.evidence_url', HTML)
        self.assertIn("external result remains unverified", HTML)
        self.assertIn("Readiness UNKNOWN", HTML)

    def test_safe_external_links_and_input_escaping(self):
        self.assertIn('rel="noopener noreferrer"', HTML)
        self.assertIn("const $=id=>document.getElementById(id),esc=", HTML)

    def test_exports_and_checkpoint_tools_exist(self):
        for feature in ("quality-gates.json", "CHECKPOINT.md", "audit-checklist.json", "function checkpoint()", "function gateResult()", "function auditResult()"):
            with self.subTest(feature=feature):
                self.assertIn(feature, HTML)

    def test_registry_remains_empty_and_write_actions_disabled(self):
        self.assertIn("Registered projects", HTML)
        self.assertIn("Registry remains opt-in and empty", HTML)
        self.assertIn("Write actions", HTML)
        self.assertIn("Disabled", HTML)

    def test_unknown_is_default_for_gate_results(self):
        self.assertIn("<option>unknown</option>", HTML)
        self.assertIn("Readiness UNKNOWN", HTML)
        self.assertIn("Missing, stale, mismatched or unverifiable results remain UNKNOWN", HTML)


if __name__ == "__main__":
    unittest.main(verbosity=2)
