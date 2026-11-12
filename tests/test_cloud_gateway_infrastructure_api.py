"""Authenticated HTTP tests for DCP Infrastructure Manager API.

Uses loopback HTTP, signed local proxy identities, SQLite temp storage and the
fake provider only. No live VM, cloud, Orka, or host provisioning is invoked.
"""
import hashlib
import hmac
import json
import secrets
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.cloud_gateway.infrastructure import (
    FakeInfrastructureProvider, InfrastructureManager, InfrastructureStore,
)
from tools.cloud_gateway.infrastructure_gates import InfrastructureGateStore
from tools.cloud_gateway.policy import GatewaySettings
from tools.cloud_gateway.server import make_handler
from tools.cloud_gateway.service import GatewayService
from tools.cloud_gateway.store import RunnerStore


class NoopProvider:
    def provision(self, payload):
        raise AssertionError("infrastructure API must not call legacy provider")

    def status(self, resource_id):
        raise AssertionError("unexpected legacy provider status")

    def terminate(self, resource_id):
        raise AssertionError("unexpected legacy provider termination")


class InfrastructureApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.secret = "local-infra-api-secret-" + ("x" * 32)
        self.origin = "https://dcp.example.test"
        store = RunnerStore(str(Path(self.temp.name) / "gateway.sqlite"))
        service = GatewayService(GatewaySettings(), store, NoopProvider())
        self.infrastructure_store = InfrastructureStore(
            Path(self.temp.name) / "infra.sqlite"
        )
        self.infrastructure_provider = FakeInfrastructureProvider()
        service.infrastructure_manager = InfrastructureManager(
            self.infrastructure_store, {"fake": self.infrastructure_provider},
        )
        self.gates_path = Path(self.temp.name) / "gates.sqlite"
        service.infrastructure_gate_store = InfrastructureGateStore(self.gates_path)
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(service, "unused-token", self.secret, self.origin),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.subject = "infra-owner@example.test"
        self.session = "infra_session_identifier_123"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def headers(self, method, path, role="owner", csrf=False):
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        canonical = "\n".join((method, path, self.subject, role,
                                  self.session, timestamp, nonce)).encode()
        signature = hmac.new(self.secret.encode(), canonical, hashlib.sha256).hexdigest()
        result = {
            "X-DCP-User": self.subject, "X-DCP-Role": role,
            "X-DCP-Session": self.session, "X-DCP-Auth-Timestamp": timestamp,
            "X-DCP-Auth-Nonce": nonce, "X-DCP-Auth-Signature": signature,
        }
        if csrf:
            result["Origin"] = self.origin
            result["X-CSRF-Token"] = hmac.new(
                self.secret.encode(),
                ("csrf\n" + self.subject + "\n" + self.session).encode(),
                hashlib.sha256,
            ).hexdigest()
        return result

    def request(self, method, path, role="owner", payload=None, extra=None):
        headers = self.headers(method, path, role, csrf=method != "GET")
        headers.update(extra or {})
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def assert_provider_and_inventory_state(self, resource_id, provider_resource_id,
                                             expected_state):
        inventory = self.infrastructure_store.get(resource_id)
        provider = self.infrastructure_provider.resources[provider_resource_id]
        self.assertEqual(inventory["state"], expected_state)
        self.assertEqual(provider["state"], expected_state)

    def test_owner_can_create_list_start_stop_and_delete_fake_resource(self):
        status, created = self.request(
            "POST", "/api/infrastructure",
            payload={"target_os": "linux", "image_id": "dcp-linux-ubuntu-24.04",
                     "template_id": "flutter-linux-small", "provider_id": "fake"},
            extra={"Idempotency-Key": "api-infra-create-0001"},
        )
        self.assertEqual(status, 201)
        resource_id = created["id"]
        # Provider identifiers are intentionally private in the public API response.
        provider_resource_id = self.infrastructure_store.get(resource_id)[
            "provider_resource_id"
        ]
        self.assertEqual(created["state"], "provisioned")
        self.assertEqual(created["provider_id"], "fake")
        self.assert_provider_and_inventory_state(
            resource_id, provider_resource_id, "provisioned"
        )

        status, inventory = self.request("GET", "/api/infrastructure")
        self.assertEqual(status, 200)
        self.assertEqual(inventory["resources"][0]["id"], resource_id)

        status, running = self.request(
            "POST", "/api/infrastructure/" + resource_id + "/start", payload={}
        )
        self.assertEqual(status, 200)
        self.assertEqual(running["state"], "running")
        self.assert_provider_and_inventory_state(
            resource_id, provider_resource_id, "running"
        )

        status, stopped = self.request(
            "POST", "/api/infrastructure/" + resource_id + "/stop", payload={}
        )
        self.assertEqual(status, 200)
        self.assertEqual(stopped["state"], "stopped")
        self.assert_provider_and_inventory_state(
            resource_id, provider_resource_id, "stopped"
        )

        status, deleted = self.request("DELETE", "/api/infrastructure/" + resource_id)
        self.assertEqual(status, 200)
        self.assertEqual(deleted["state"], "deleted")
        self.assert_provider_and_inventory_state(
            resource_id, provider_resource_id, "deleted"
        )

    def test_operator_cannot_delete_resource(self):
        status, created = self.request(
            "POST", "/api/infrastructure",
            payload={"target_os": "linux", "image_id": "dcp-linux-ubuntu-24.04",
                     "template_id": "flutter-linux-small"},
            extra={"Idempotency-Key": "api-infra-create-0002"},
        )
        self.assertEqual(status, 201)
        status, result = self.request(
            "DELETE", "/api/infrastructure/" + created["id"], role="operator"
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "owner role required")

    def test_independent_gates_default_off_and_persist(self):
        status, result = self.request("GET", "/api/infrastructure/gates")
        self.assertEqual(status, 200)
        gates = result["gates"]
        self.assertEqual(set(gates), {"cloud_provisioning", "vm_creation"})
        for gate in gates.values():
            self.assertFalse(gate["enabled"])
            self.assertFalse(gate["effective_enabled"])
            self.assertFalse(gate["ready"])

        reopened = InfrastructureGateStore(self.gates_path)
        persisted = reopened.status({"cloud_provisioning": False, "vm_creation": False})
        self.assertFalse(persisted["cloud_provisioning"]["enabled"])
        self.assertFalse(persisted["vm_creation"]["enabled"])

    def test_gate_enable_requires_owner_confirmation_and_ready_provider(self):
        status, wrong = self.request(
            "POST", "/api/infrastructure/gates/cloud_provisioning",
            payload={"enabled": True, "confirmation": "yes"},
        )
        self.assertEqual(status, 400)
        self.assertIn("confirmation", wrong["error"].lower())

        status, unavailable = self.request(
            "POST", "/api/infrastructure/gates/cloud_provisioning",
            payload={"enabled": True, "confirmation": "ENABLE CLOUD PROVISIONING"},
        )
        self.assertEqual(status, 503)
        self.assertIn("not ready", unavailable["error"])

        status, result = self.request(
            "GET", "/api/infrastructure/gates"
        )
        self.assertEqual(status, 200)
        self.assertFalse(result["gates"]["cloud_provisioning"]["enabled"])

    def test_gate_changes_are_owner_only_and_csrf_protected(self):
        status, denied = self.request(
            "POST", "/api/infrastructure/gates/vm_creation", role="operator",
            payload={"enabled": False},
        )
        self.assertEqual(status, 403)
        self.assertEqual(denied["error"], "owner role required")

        # A valid owner request can explicitly keep a gate OFF and is audited.
        status, result = self.request(
            "POST", "/api/infrastructure/gates/vm_creation",
            payload={"enabled": False},
        )
        self.assertEqual(status, 200)
        self.assertFalse(result["gate"]["enabled"])
        events = InfrastructureGateStore(self.gates_path).events("vm_creation")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["actor"], self.subject)
        self.assertFalse(bool(events[0]["enabled"]))

    def test_unauthenticated_inventory_is_rejected(self):
        request = Request(self.base + "/api/infrastructure")
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        try:
            self.assertEqual(caught.exception.code, 401)
        finally:
            caught.exception.close()


    def test_terminal_catalog_and_preview_are_authenticated_and_inert(self):
        status, catalog = self.request("GET", "/api/terminal/templates")
        self.assertEqual(status, 200)
        self.assertFalse(catalog["execution_enabled"])
        templates = {item["id"]: item for item in catalog["templates"]}
        self.assertIn("git_status", templates)
        self.assertIn("python_version", templates)
        self.assertTrue(all(not item["execution_enabled"] for item in templates.values()))

        status, preview = self.request(
            "POST", "/api/terminal/commands/preview",
            payload={"template_id": "git_status"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            preview["preview"]["command_preview"], ["git", "status", "--short"]
        )
        self.assertEqual(preview["preview"]["status"], "PREVIEW_ONLY")
        self.assertFalse(preview["execution_enabled"])

    def test_terminal_preview_rejects_arbitrary_command_fields_and_unknown_templates(self):
        status, result = self.request(
            "POST", "/api/terminal/commands/preview",
            payload={"template_id": "git_status", "command": "whoami"},
        )
        self.assertEqual(status, 400)
        self.assertIn("only template_id", result["error"])

        status, result = self.request(
            "POST", "/api/terminal/commands/preview",
            payload={"template_id": "python -c"},
        )
        self.assertEqual(status, 400)
        self.assertIn("unknown terminal template", result["error"])

    def test_terminal_catalog_denies_unauthenticated_access(self):
        request = Request(self.base + "/api/terminal/templates")
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        try:
            self.assertEqual(caught.exception.code, 401)
        finally:
            caught.exception.close()


if __name__ == "__main__":
    unittest.main()
