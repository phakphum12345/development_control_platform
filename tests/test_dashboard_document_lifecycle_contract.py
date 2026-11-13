"""Static contract tests for the new dashboard document/lifecycle controls."""
from html.parser import HTMLParser
from pathlib import Path
import unittest


DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard" / "index.html"


class DashboardContractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.tabs = set()
        self.values = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if attrs.get("data-tab"):
            self.tabs.add(attrs["data-tab"])
        if tag == "option" and attrs.get("value"):
            self.values.add(attrs["value"])


class DashboardDocumentLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DASHBOARD.read_text(encoding="utf-8")
        cls.parser = DashboardContractParser()
        cls.parser.feed(cls.source)

    def test_document_generator_controls_exist(self):
        required = {
            "document-generator", "doc-type", "doc-project", "doc-title",
            "doc-purpose", "doc-source", "doc-milestones", "doc-risks",
            "doc-generate", "doc-output", "doc-download", "doc-integrity",
        }
        self.assertTrue(required.issubset(self.parser.ids))
        self.assertIn("document-generator", self.parser.tabs)

    def test_document_formats_and_download_boundary_are_explicit(self):
        self.assertIn('value="markdown"', self.source)
        self.assertIn('value="roadmap"', self.source)
        self.assertIn('value="text"', self.source)
        self.assertIn("browser cannot confirm disk persistence", self.source)
        self.assertIn("Repository write/read-back: UNKNOWN", self.source)

    def test_owner_approved_local_write_controls_and_api_contract_exist(self):
        required = {
            "doc-local-project", "doc-local-path", "doc-scope-prefix",
            "doc-scope-confirm", "doc-local-refresh", "doc-scope-grant",
            "doc-propose-write", "doc-write-proposal", "doc-write-confirm",
            "doc-approve-write", "doc-local-status",
        }
        self.assertTrue(required.issubset(self.parser.ids))
        for route in (
            "/api/local-projects", "/api/document-workflow/grants",
            "/api/document-workflow/target", "/api/document-workflow/proposals",
        ):
            self.assertIn(route, self.source)
        self.assertIn("X-CSRF-Token", self.source)
        self.assertIn("GRANT DOCUMENT WRITE SCOPE", self.source)
        self.assertIn("WRITE DOCUMENT", self.source)
        self.assertIn("read_back_verified", self.source)
        self.assertIn("No blind retry was sent", self.source)

    def test_dashboard_never_treats_download_as_repository_write(self):
        self.assertIn("browser cannot confirm disk persistence", self.source)
        self.assertIn("GitHub write actions:", self.source)
        self.assertIn("LOCAL DOC WRITE GATED", self.source)

    def test_pr_lifecycle_stages_are_all_present(self):
        stages = {
            "before-open", "after-open", "before-merge",
            "after-merge", "before-close", "after-close",
        }
        self.assertTrue(stages.issubset(self.parser.values))
        self.assertIn("pr-lifecycle-verify", self.parser.ids)
        self.assertIn("does not open, merge, or close PRs", self.source)
        self.assertIn("requiredChecksPass", self.source)
        self.assertIn("branch-protection", self.source)

    def test_read_only_network_requests_have_bounded_retries(self):
        self.assertIn("attempt<3", self.source)
        self.assertIn("setTimeout(()=>controller.abort(),12000)", self.source)
        self.assertIn("response.status===429||response.status>=500", self.source)
        self.assertIn("Remote outcome is UNKNOWN", self.source)


if __name__ == "__main__":
    unittest.main()
