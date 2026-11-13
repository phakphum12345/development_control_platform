"""Tests for the strict Terminal Studio execution-intent contract."""
import unittest
import uuid

from tools.cloud_gateway.terminal_execution_contract import (
    TerminalContractError,
    validate_terminal_request,
)


class TerminalExecutionContractTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "project_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
            "snapshot_sha256": "a" * 64,
            "template_id": "git_status",
            "parameters": {},
            "authorization_id": str(uuid.uuid4()),
        }

    def test_valid_request_is_canonical_intent_not_authorization(self):
        result = validate_terminal_request(self.payload)
        self.assertEqual(result["request"]["project_id"], self.payload["project_id"])
        self.assertEqual(result["request"]["workspace_id"], self.payload["workspace_id"])
        self.assertEqual(result["request"]["template_id"], "git_status")
        self.assertEqual(len(result["request_sha256"]), 64)
        self.assertEqual(len(result["template_version_digest"]), 64)
        self.assertFalse(result["execution_enabled"])
        self.assertEqual(result["status"], "VALIDATED_INTENT_NOT_AUTHORIZED")

    def test_arbitrary_shell_and_runner_fields_are_rejected(self):
        forbidden = (
            "command", "shell", "executable", "argv", "cwd", "working_directory",
            "env", "environment", "runner_id", "role", "approved", "permission",
        )
        for field in forbidden:
            with self.subTest(field=field):
                payload = dict(self.payload)
                payload[field] = "attacker-controlled"
                with self.assertRaises(TerminalContractError):
                    validate_terminal_request(payload)

    def test_unknown_template_and_untyped_parameters_are_rejected(self):
        payload = dict(self.payload, template_id="python -c")
        with self.assertRaises(TerminalContractError):
            validate_terminal_request(payload)
        payload = dict(self.payload, template_id="git_log", parameters={"limit": "1;whoami"})
        with self.assertRaises(TerminalContractError):
            validate_terminal_request(payload)

    def test_invalid_project_workspace_or_authorization_ids_fail_closed(self):
        for field in ("project_id", "workspace_id", "authorization_id"):
            with self.subTest(field=field):
                payload = dict(self.payload)
                payload[field] = "../other-project"
                with self.assertRaises(TerminalContractError):
                    validate_terminal_request(payload)

    def test_snapshot_digest_must_be_exact_sha256(self):
        for value in ("", "A" * 64, "a" * 63, "a" * 65, "../workspace"):
            with self.subTest(value=value):
                payload = dict(self.payload, snapshot_sha256=value)
                with self.assertRaises(TerminalContractError):
                    validate_terminal_request(payload)

    def test_parameter_normalization_is_stable(self):
        payload = dict(self.payload, template_id="git_log", parameters={"limit": 5})
        result = validate_terminal_request(payload)
        self.assertEqual(result["request"]["parameters"], {"limit": "5"})
        self.assertEqual(
            result["request_sha256"],
            validate_terminal_request(payload)["request_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
