import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


class DashboardContractTests(unittest.TestCase):
    def test_all_tool_views_exist(self):
        for view in ("home", "repo", "pr", "user", "workspace", "evidence", "gates", "checkpoint", "audit", "route-colors", "ui-routes", "ui-simulator", "dev-tools", "code-navigator"):
            with self.subTest(view=view):
                self.assertIn('id="' + view + '"', HTML)
        for control in ("repo-load", "pr-load", "user-load", "ws-load", "ws-repo", "ws-branch", "ws-permission", "ws-branches", "ev-check", "gate-eval", "cp-build", "audit-eval", "route-color-save", "route-color-reset", "route-color-export", "route-add", "route-reset", "route-export", "edge-add", "edge-clear", "sim-run", "sim-reset", "sim-download", "dev-tools-copy-status", "code-nav-search", "code-nav-filter", "code-nav-trace-ui", "code-nav-trace-calls", "code-nav-show-ui", "code-nav-compare", "code-nav-run-checks", "code-nav-checkpoint", "code-nav-route-list", "code-nav-mapping", "code-nav-evidence"):
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
            'Actual app navigation is unchanged',
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, HTML)

    def test_route_validation_detects_parent_cycles_duplicate_edges_and_disabled_targets(self):
        for contract in (
            "const errors=[],warnings=[]",
            "Parent cycle detected:",
            "Duplicate connection:",
            "Connection leads to disabled route:",
            "errors,warnings",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, HTML)


    def test_code_navigator_mapping_is_explicit_safe_and_route_aware(self):
        for expected in (
            'id="code-navigator"', 'data-tab="code-navigator"',
            'CODE_NAV_MAPPINGS', 'function codeNavTraceUI()',
            'function codeNavTraceCalls()', 'function codeNavShowUI()',
            'function codeNavCompare()', 'function codeNavRunChecks()',
            'function codeNavCheckpoint()', 'dcp.ui-route-registry.v1',
            'dcp.route-colors.v1', 'Unmapped dynamic call edges: UNKNOWN',
            'CI / deployment evidence: UNKNOWN',
            'sandbox', 'Trace Calls', 'Run Checks', 'Impact / Dependencies',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, HTML)

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



    def test_google_oauth_sync_reuses_existing_endpoints_and_fails_closed(self):
        for expected in (
            'id="ros-api-sync"', 'Sync Google OAuth',
            'function rosApiStartOAuthSync()',
            '"/v1/auth/google/start"', '"/v1/auth/google/handoff"',
            '"/v1/auth/signout"', 'event.origin !== expectedOrigin',
            'event.data.type !== "research-os-oauth-complete"',
            'authorizationUrl.protocol !== "https:"',
            'authorizationUrl.hostname !== "accounts.google.com"',
            'Session is memory-only',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, HTML)
        self.assertNotIn('localStorage.setItem("rosApiSession"', HTML)
        self.assertNotIn('sessionStorage.setItem("rosApiSession"', HTML)

    def test_pwa_shell_and_password_auth_fail_closed(self):
        import json
        manifest = json.loads((ROOT / "dashboard" / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["scope"], "./")
        self.assertTrue((ROOT / "dashboard" / "sw.js").is_file())
        self.assertTrue((ROOT / "dashboard" / "icons" / "dcp.svg").is_file())
        for expected in (
            'rel="manifest" href="./manifest.webmanifest"',
            'name="apple-mobile-web-app-capable" content="yes"',
            'id="account"', 'id="auth-login-form"',
            './api/auth/session', './api/auth/login', './api/auth/logout',
            'credentials:"same-origin"', 'X-CSRF-Token', 'csrfToken=null', 'data.csrfToken', 'Sign-in blocked: missing server-issued CSRF token', 'type="password"',
            'GitHub Pages is static hosting',
            'No password login will be simulated',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, HTML)
        self.assertNotIn("localStorage.setItem(\"auth", HTML)
        self.assertNotIn("sessionStorage.setItem(\"auth", HTML)
        worker = (ROOT / "dashboard" / "sw.js").read_text(encoding="utf-8")
        self.assertIn("Authentication/API requests are always network-only", worker)
        self.assertIn('request.method !== "GET"', worker)
        self.assertIn("url.pathname.startsWith(apiPrefix)", worker)

class DevEnvironmentDashboardContractTests(unittest.TestCase):
    def test_local_tooling_view_is_honest_and_actionable(self):
        for expected in (
            'id="dev-tools"', 'data-tab="dev-tools"',
            'python tools/dev_environment.py status', 'python tools/dev_environment.py devices',
            'python tools/dev_environment.py avds',
            'python tools/dev_environment.py launch-avd --name YOUR_AVD_NAME',
            'A browser cannot inspect or launch processes on your computer',
            'not automatically uploaded or treated as CI evidence', 'data-copy-command',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, HTML)

    def test_environment_helper_contract_and_safety(self):
        helper = (ROOT / "tools" / "dev_environment.py").read_text(encoding="utf-8")
        for expected in ("def status()", "def devices()", "def avds()", "def launch_avd(name: str)",
                         "shell=False", '"status": "unknown"', "AVD name is not in the installed AVD list"):
            with self.subTest(expected=expected):
                self.assertIn(expected, helper)

    def test_vscode_tasks_are_workspace_scoped_and_do_not_install_sdks(self):
        import json
        tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
        labels = {task["label"] for task in tasks["tasks"]}
        for label in ("DCP: Check local development environment", "DCP: List Android AVDs",
                      "DCP: Launch Android AVD", "DCP: Python contract tests",
                      "DCP: Dashboard browser smoke tests"):
            self.assertIn(label, labels)
        self.assertTrue(all(task["type"] == "process" for task in tasks["tasks"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
