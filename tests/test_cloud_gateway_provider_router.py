"""Provider router contract tests; all providers are in-memory fakes."""
import unittest

from tools.cloud_gateway.policy import PROFILES
from tools.cloud_gateway.provider_router import ProviderRouter
from tools.runner_backend.provider import RunnerInstance


class Fake:
    def __init__(self, ready=True):
        self.ready = ready
        self.calls = []

    def readiness(self, os_name):
        self.calls.append(("readiness", os_name))
        return {"ready": self.ready, "message": "fake"}

    def provision(self, payload):
        self.calls.append(("provision", payload["target_os"]))
        return RunnerInstance("dcp-12-abcdef12", "provisioning", "runner")

    def status(self, provider_id):
        self.calls.append(("status", provider_id))
        return RunnerInstance(provider_id, "online", "runner")

    def terminate(self, provider_id):
        self.calls.append(("terminate", provider_id))
        return RunnerInstance(provider_id, "terminating", "runner")


class ProviderRouterTests(unittest.TestCase):
    def setUp(self):
        self.azure = Fake()
        self.orka = Fake()
        self.router = ProviderRouter(self.azure, self.orka)

    def test_routes_linux_and_windows_to_azure(self):
        for os_name in ("linux", "windows"):
            with self.subTest(os_name=os_name):
                instance = self.router.provision({"target_os": os_name})
                self.assertTrue(instance.provider_id.startswith("azure:"))
        self.assertEqual([c for c in self.azure.calls if c[0] == "provision"],
                         [("provision", "linux"), ("provision", "windows")])
        self.assertFalse(any(c[0] == "provision" for c in self.orka.calls))

    def test_routes_macos_to_orka(self):
        instance = self.router.provision({"target_os": "macos"})
        self.assertTrue(instance.provider_id.startswith("orka:"))
        self.assertEqual(self.orka.calls[-1], ("provision", "macos"))

    def test_status_and_terminate_unwrap_namespaced_ids(self):
        self.router.status("azure:dcp-12-abcdef12")
        self.router.terminate("orka:dcp-12-abcdef12")
        self.assertIn(("status", "dcp-12-abcdef12"), self.azure.calls)
        self.assertIn(("terminate", "dcp-12-abcdef12"), self.orka.calls)

    def test_provider_namespace_survives_restart(self):
        first = self.router.provision({"target_os": "macos"})
        restarted = ProviderRouter(self.azure, self.orka)
        self.assertEqual(restarted.status(first.provider_id).state, "online")

    def test_unconfigured_or_unready_provider_fails_closed(self):
        router = ProviderRouter(None, self.orka)
        self.assertFalse(router.readiness("linux")["ready"])
        with self.assertRaises(RuntimeError):
            router.provision({"target_os": "linux"})
        self.azure.ready = False
        with self.assertRaises(RuntimeError):
            self.router.provision({"target_os": "linux"})

    def test_unknown_provider_id_is_rejected(self):
        with self.assertRaises(ValueError):
            self.router.status("dcp-12-abcdef12")


if __name__ == "__main__":
    unittest.main()
