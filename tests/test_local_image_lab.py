import json
import tempfile
import unittest
from pathlib import Path

from tools.local_image_lab.backend import load_blueprint, run_mock_build


class LocalImageLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.blueprint = self.root / "blueprint.json"
        self.blueprint.write_text(json.dumps({
            "schema_version": 1,
            "build_mode": "mock",
            "image_name": "dcp/test",
            "tag": "test",
            "base_image": "python:3.14-slim",
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_mock_run_writes_sha_bound_evidence(self):
        result = run_mock_build(self.blueprint, self.root / "evidence", "a" * 40)
        self.assertEqual(result["status"], "SIMULATED_PASS")
        self.assertEqual(result["source_sha"], "a" * 40)
        self.assertEqual(len(result["blueprint_sha256"]), 64)
        self.assertTrue(Path(result["evidence_path"]).is_file())
        saved = json.loads(Path(result["evidence_path"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["contract"], "dcp.local-image-lab.evidence.v1")

    def test_loads_utf8_bom_blueprint(self):
        content = self.blueprint.read_text(encoding="utf-8")
        self.blueprint.write_bytes(bytes.fromhex("efbbbf") + content.encode("utf-8"))

        blueprint, digest = load_blueprint(self.blueprint)

        self.assertEqual(blueprint["build_mode"], "mock")
        self.assertEqual(len(digest), 64)

    def test_mock_never_claims_real_image_or_docker(self):
        result = run_mock_build(self.blueprint, self.root / "evidence", "b" * 40)
        execution = result["execution"]
        self.assertFalse(execution["docker_invoked"])
        self.assertFalse(execution["image_built"])
        self.assertFalse(execution["network_used"])
        self.assertFalse(execution["cloud_provider_used"])
        self.assertFalse(execution["vm_created"])

    def test_rejects_short_source_sha(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            run_mock_build(self.blueprint, self.root / "evidence", "abc")

    def test_rejects_non_mock_build_mode(self):
        data = json.loads(self.blueprint.read_text(encoding="utf-8"))
        data["build_mode"] = "docker"
        self.blueprint.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "only build_mode=mock"):
            load_blueprint(self.blueprint)

    def test_rejects_invalid_image_name(self):
        data = json.loads(self.blueprint.read_text(encoding="utf-8"))
        data["image_name"] = "../escape"
        self.blueprint.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "image_name"):
            load_blueprint(self.blueprint)

    def test_rejects_unknown_schema(self):
        data = json.loads(self.blueprint.read_text(encoding="utf-8"))
        data["schema_version"] = 99
        self.blueprint.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "schema_version"):
            load_blueprint(self.blueprint)


if __name__ == "__main__":
    unittest.main()
