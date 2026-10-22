import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


class DashboardContractTests(unittest.TestCase):
    def test_all_tool_views_exist(self):
        for view in ("home", "repo", "pr", "user", "evidence", "gates", "checkpoint", "audit", "route-colors", "ui-routes", "ui-simulator"):
            with self.subTest(view=view):
                self.assertIn('id="' + view + '"', HTML)
        for control in ("repo-load", "pr-load", "user-load", "ev-check", "gate-eval", "cp-build", "audit-eval", "route-color-save", "route-color-reset", "route-color-export", "route-add", "route-reset", "route-export", "edge-add", "edge-clear", "sim-run", "sim-reset", "sim-download"):
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

    def test_ui_route_manager_and_sandbox_simulator_contract(self):
        for view in ("ui-routes", "ui-simulator"):
            with self.subTest(view=view):
                self.assertIn('id="' + view + '"', HTML)
        for control in ("route-add", "route-reset", "route-export", "edge-add", "edge-clear", "route-validation", "sim-code", "sim-preview", "sim-run", "sim-reset", "sim-download"):
            with self.subTest(control=control):
                self.assertIn('id="' + control + '"', HTML)
        self.assertIn("ROUTE_DEFAULTS", HTML)
        self.assertIn("validateRouteRegistry", HTML)
        self.assertIn('sandbox="allow-scripts"', HTML)
        self.assertIn("dcp.ui-route-registry.v1", HTML)
        self.assertIn("metadata-only", HTML)

    def test_ui_route_manager_supports_edit_drag_drop_and_registry_simulation(self):
        for contract in (
            'id="route-cancel-edit"',
            'data-route-edit=',
            'function beginRouteEdit(id)',
            'function cancelRouteEdit()',
            'addEventListener("dragstart"',
            'addEventListener("drop"',
            'id="sim-route-select"',
            'id="sim-open-route"',
            'function buildRoutePreviewDocument(routeId)',
            'Route preview generated from current local registry and connections',
            'querySelectorAll(".view")',
            'actual app navigation is unchanged',
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, HTML)

    def test_shared_route_color_manager_is_centralized_and_safe(self):
        for contract in (
            "ROUTE_COLOR_DEFAULTS",
            "ROUTE_COLOR_LABELS",
            "dcp.route-colors.v1",
            "function normalizeRouteColors(candidate)",
            "function applyRouteColors(candidate)",
            "function initRouteColorManager()",
            "validHexColor",
            "localStorage.setItem",
            "localStorage.removeItem",
            "route-color-preview",
            "UNKNOWN",
            "never prove gate status",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, HTML)
        self.assertIn('data-tab="route-colors"', HTML)
        self.assertIn('type="color"', HTML)
        self.assertIn("route_unknown", HTML)
        self.assertIn("status_unknown", HTML)


if __name__ == "__main__":
    unittest.main(verbosity=2)
