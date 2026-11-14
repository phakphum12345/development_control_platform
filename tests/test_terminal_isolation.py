import unittest

from tools.local_runner_agent.terminal_isolation import (
    IsolationAssessment,
    assess_isolation_backend,
    require_verified_isolation,
)


class TerminalIsolationContractTests(unittest.TestCase):
    def test_linux_without_bubblewrap_is_blocked(self):
        result = assess_isolation_backend("linux", executable_lookup=lambda _name: None)
        self.assertEqual(result.platform, "linux")
        self.assertEqual(result.backend, "bubblewrap-namespaces-seccomp")
        self.assertEqual(result.state, "BLOCKED")
        self.assertFalse(result.available)
        self.assertFalse(result.network_isolated)
        self.assertFalse(result.filesystem_isolated)
        self.assertFalse(result.process_tree_contained)

    def test_linux_with_bubblewrap_is_only_ready_for_acceptance(self):
        result = assess_isolation_backend(
            "linux", executable_lookup=lambda _name: "/usr/bin/bwrap"
        )
        self.assertEqual(result.state, "READY_FOR_ACCEPTANCE")
        self.assertTrue(result.available)
        self.assertFalse(result.network_isolated)
        self.assertFalse(result.filesystem_isolated)
        self.assertFalse(result.process_tree_contained)
        with self.assertRaisesRegex(RuntimeError, "execution is blocked"):
            require_verified_isolation(result)

    def test_windows_requires_native_appcontainer_launcher(self):
        result = assess_isolation_backend("windows")
        self.assertEqual(result.backend, "appcontainer-lpac")
        self.assertEqual(result.state, "BLOCKED")
        self.assertFalse(result.available)

    def test_macos_requires_signed_sandbox_helper(self):
        result = assess_isolation_backend("macos")
        self.assertEqual(result.backend, "signed-app-sandbox-helper")
        self.assertEqual(result.state, "BLOCKED")
        self.assertFalse(result.available)

    def test_verified_state_requires_all_enforcement_claims(self):
        incomplete = IsolationAssessment(
            platform="linux",
            backend="bubblewrap-namespaces-seccomp",
            state="VERIFIED",
            available=True,
            network_isolated=True,
            filesystem_isolated=True,
            process_tree_contained=False,
            reason="missing process containment",
        )
        with self.assertRaises(RuntimeError):
            require_verified_isolation(incomplete)

    def test_unknown_platform_is_blocked(self):
        result = assess_isolation_backend("plan9")
        self.assertEqual(result.platform, "unsupported")
        self.assertEqual(result.state, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
