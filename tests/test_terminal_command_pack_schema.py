"""Machine-readable JSON Schema contract for imported Terminal command packs."""
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "terminal-command-pack.schema.json").read_text(encoding="utf-8")
)


class TerminalCommandPackSchemaTests(unittest.TestCase):
    def test_schema_is_valid_and_accepts_a_bounded_inert_pack(self):
        Draft202012Validator.check_schema(SCHEMA)
        candidate = {
            "schema_version": 1,
            "templates": [{
                "id": "custom-git-status",
                "name": "Git status",
                "description": "Inspect current changes.",
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
        Draft202012Validator(SCHEMA).validate(candidate)

    def test_schema_rejects_unknown_fields_unbounded_values_and_network(self):
        validator = Draft202012Validator(SCHEMA)
        candidate = {
            "schema_version": 1,
            "templates": [{
                "id": "custom-git-status",
                "name": "Git status",
                "description": "Inspect current changes.",
                "category": "Git",
                "executable_id": "git",
                "argv": ["status"],
                "platforms": ["windows"],
                "timeout_seconds": 301,
                "max_output_bytes": 65536,
                "network": "allowed",
                "mutation_class": "read-only",
                "shell": True,
            }],
        }
        self.assertGreater(len(list(validator.iter_errors(candidate))), 0)


if __name__ == "__main__":
    unittest.main()
