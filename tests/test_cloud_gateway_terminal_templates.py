"""Tests for persistent, inert Terminal Studio command-pack imports."""
import tempfile
import unittest
from pathlib import Path

from tools.cloud_gateway.terminal_templates import (
    TerminalTemplateConflict, TerminalTemplateError, TerminalTemplateStore,
    validate_command_pack,
)


def pack(template_id="custom-inspect-git"):
    return {
        "schema_version": 1,
        "templates": [{
            "id": template_id,
            "name": "Inspect Git",
            "description": "Read-only inspection template imported for review.",
            "category": "Git",
            "executable_id": "git",
            "argv": ["status", "--short"],
            "platforms": ["windows", "linux"],
            "timeout_seconds": 15,
            "max_output_bytes": 65536,
            "network": "denied",
            "mutation_class": "read-only",
        }],
    }


class TerminalTemplateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "terminal.sqlite"
        self.store = TerminalTemplateStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_imported_templates_are_persisted_disabled_and_audited(self):
        result = self.store.import_pack(pack(), "owner@example.test")
        self.assertEqual(len(result["imported"]), 1)
        row = result["imported"][0]
        self.assertFalse(row["enabled"])
        self.assertFalse(row["execution_enabled"])
        self.assertEqual(row["approval_status"], "pending_review")
        self.assertEqual(row["network"], "denied")
        self.assertEqual(len(result["source_sha256"]), 64)

        reopened = TerminalTemplateStore(self.path)
        saved = reopened.get_imported("custom-inspect-git")
        self.assertFalse(saved["execution_enabled"])
        self.assertEqual(saved["approval_status"], "pending_review")
        events = reopened.events("custom-inspect-git")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "imported_pending_review")
        self.assertEqual(events[0]["actor"], "owner@example.test")

    def test_duplicate_id_rejected_without_partial_import(self):
        self.store.import_pack(pack(), "owner@example.test")
        with self.assertRaisesRegex(TerminalTemplateError, "already exists"):
            self.store.import_pack({
                "schema_version": 1,
                "templates": [pack("custom-second")["templates"][0], pack()["templates"][0]],
            }, "owner@example.test")
        self.assertEqual(
            [row["id"] for row in self.store.list_imported()],
            ["custom-inspect-git"],
        )

    def test_rejects_unknown_fields_shell_metacharacters_and_network(self):
        cases = []
        bad = pack()
        bad["command"] = "git status"
        cases.append(bad)
        bad = pack()
        bad["templates"][0]["argv"] = ["status", "&&", "whoami"]
        cases.append(bad)
        bad = pack()
        bad["templates"][0]["network"] = "allowed"
        cases.append(bad)
        bad = pack()
        bad["templates"][0]["environment"] = {"TOKEN": "secret"}
        cases.append(bad)
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(TerminalTemplateError):
                validate_command_pack(candidate)

    def test_rejects_unsafe_executable_code_flags_and_invalid_limits(self):
        for argv in (["-c", "print(1)"], ["--eval", "alert(1)"], ["status", "; whoami"]):
            candidate = pack()
            candidate["templates"][0]["executable_id"] = "python" if argv[0] == "-c" else "node" if argv[0] == "--eval" else "git"
            candidate["templates"][0]["argv"] = argv
            with self.subTest(argv=argv), self.assertRaises(TerminalTemplateError):
                validate_command_pack(candidate)
        candidate = pack()
        candidate["templates"][0]["timeout_seconds"] = True
        with self.assertRaises(TerminalTemplateError):
            validate_command_pack(candidate)
        candidate = pack()
        candidate["templates"][0]["max_output_bytes"] = 1024 * 1024 + 1
        with self.assertRaises(TerminalTemplateError):
            validate_command_pack(candidate)

    def test_malformed_unhashable_fields_fail_as_validation_errors(self):
        for field, value in (
            ("category", {}),
            ("executable_id", []),
            ("platforms", [[]]),
            ("mutation_class", {}),
        ):
            candidate = pack()
            candidate["templates"][0][field] = value
            with self.subTest(field=field), self.assertRaises(TerminalTemplateError):
                validate_command_pack(candidate)

    def test_pack_requires_exact_version_and_bounded_template_count(self):
        candidate = pack()
        candidate["schema_version"] = 2
        with self.assertRaises(TerminalTemplateError):
            validate_command_pack(candidate)
        with self.assertRaises(TerminalTemplateError):
            validate_command_pack({"schema_version": 1, "templates": []})


    def test_owner_review_approval_keeps_template_non_executable_and_audited(self):
        imported = self.store.import_pack(pack(), "owner@example.test")
        digest = imported["source_sha256"]
        approved = self.store.review(
            "custom-inspect-git", "approve", "owner@example.test",
            "APPROVE TEMPLATE custom-inspect-git", digest,
        )
        self.assertEqual(approved["approval_status"], "approved")
        self.assertFalse(approved["enabled"])
        self.assertFalse(approved["execution_enabled"])
        events = self.store.events("custom-inspect-git")
        self.assertEqual([event["event"] for event in events], [
            "imported_pending_review", "approved_not_executable"
        ])

    def test_owner_review_rejects_bad_confirmation_stale_hash_and_repeat(self):
        imported = self.store.import_pack(pack(), "owner@example.test")
        digest = imported["source_sha256"]
        with self.assertRaisesRegex(TerminalTemplateError, "confirmation"):
            self.store.review(
                "custom-inspect-git", "approve", "owner@example.test",
                "yes", digest,
            )
        with self.assertRaisesRegex(TerminalTemplateConflict, "SHA-256 changed"):
            self.store.review(
                "custom-inspect-git", "approve", "owner@example.test",
                "APPROVE TEMPLATE custom-inspect-git", "0" * 64,
            )
        rejected = self.store.review(
            "custom-inspect-git", "reject", "owner@example.test",
            "REJECT TEMPLATE custom-inspect-git", digest,
        )
        self.assertEqual(rejected["approval_status"], "rejected")
        self.assertFalse(rejected["execution_enabled"])
        with self.assertRaisesRegex(TerminalTemplateConflict, "no longer pending"):
            self.store.review(
                "custom-inspect-git", "approve", "owner@example.test",
                "APPROVE TEMPLATE custom-inspect-git", digest,
            )


if __name__ == "__main__":
    unittest.main()
