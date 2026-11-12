"""ArtifactStore tests for ownership, bounded uploads, checksums, and retention."""
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from tools.cloud_gateway.artifacts import ArtifactError, ArtifactStore
from tools.cloud_gateway.job_control import JobStore


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.jobs = JobStore(str(self.root / "jobs.sqlite3"))
        self.artifacts = ArtifactStore(self.root / "artifacts", max_artifact_bytes=2048)
        self.job, _ = self.jobs.create({
            "repository": "owner/repo", "commit_sha": "a" * 40, "target": "build"
        }, "artifact-test-key-001")
        self.claimed = self.jobs.claim("runner-artifact")
        self.assertEqual(self.claimed["id"], self.job["id"])

    def tearDown(self):
        self.temp.cleanup()

    def test_stores_hash_and_returns_immutable_metadata(self):
        payload = b"flutter-build-output"
        metadata = self.artifacts.store(
            self.jobs, self.job["id"], "runner-artifact", "app-release.apk",
            io.BytesIO(payload), len(payload),
        )
        self.assertEqual(metadata["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(metadata["size"], len(payload))
        provenance = metadata["provenance"]
        self.assertEqual(provenance["schema_version"], 1)
        self.assertEqual(provenance["job"]["id"], self.job["id"])
        self.assertEqual(provenance["job"]["target"], "build")
        self.assertEqual(provenance["source"]["type"], "github")
        self.assertEqual(provenance["source"]["repository"], "owner/repo")
        self.assertEqual(provenance["source"]["commit_sha"], "a" * 40)
        self.assertEqual(provenance["artifact"]["sha256"], metadata["sha256"])
        self.assertEqual(len(metadata["provenance_sha256"]), 64)
        listed = self.artifacts.list_for_job(self.job["id"])[0]
        self.assertEqual(listed["provenance"], provenance)
        self.assertEqual(listed["provenance_sha256"], metadata["provenance_sha256"])
        read_metadata, handle = self.artifacts.open(metadata["id"])
        with handle:
            self.assertEqual(handle.read(), payload)
        self.assertEqual(read_metadata["name"], "app-release.apk")

    def test_rejects_path_names_oversize_and_non_owner(self):
        payload = b"payload"
        with self.assertRaises(ArtifactError):
            self.artifacts.store(self.jobs, self.job["id"], "runner-artifact",
                                 "../escape.apk", io.BytesIO(payload), len(payload))
        with self.assertRaises(ArtifactError):
            self.artifacts.store(self.jobs, self.job["id"], "other-runner",
                                 "app.apk", io.BytesIO(payload), len(payload))
        with self.assertRaises(ArtifactError):
            self.artifacts.store(self.jobs, self.job["id"], "runner-artifact",
                                 "huge.bin", io.BytesIO(b"x" * 2049), 2049)

    def test_rejects_truncated_upload_and_does_not_leave_blob(self):
        with self.assertRaises(ArtifactError):
            self.artifacts.store(self.jobs, self.job["id"], "runner-artifact",
                                 "partial.zip", io.BytesIO(b"x"), 10)
        self.assertEqual(self.artifacts.list_for_job(self.job["id"]), [])

    def test_rejects_invalid_artifact_id(self):
        with self.assertRaises(ArtifactError):
            self.artifacts.get("../../metadata.sqlite3")


    def test_download_rejects_blob_tampering(self):
        payload = b"original-build-output"
        metadata = self.artifacts.store(
            self.jobs, self.job["id"], "runner-artifact", "bundle.zip",
            io.BytesIO(payload), len(payload),
        )
        _, path = self.artifacts.get(metadata["id"])
        path.write_bytes(b"tampered-build-output")
        with self.assertRaises(ArtifactError):
            self.artifacts.open(metadata["id"])


    def test_local_folder_provenance_binds_snapshot_sha256(self):
        project_id = str(uuid.uuid4())
        snapshot_sha = "b" * 64
        job, created = self.jobs.create({
            "source_type": "local_folder",
            "project_id": project_id,
            "snapshot_sha256": snapshot_sha,
            "target": "build_static_web",
        }, "local-artifact-test-001")
        self.assertTrue(created)
        claimed = self.jobs.claim("runner-local-artifact")
        self.assertEqual(claimed["id"], job["id"])
        payload = b"local-static-output"
        metadata = self.artifacts.store(
            self.jobs, job["id"], "runner-local-artifact", "site.zip",
            io.BytesIO(payload), len(payload),
        )
        source = metadata["provenance"]["source"]
        self.assertEqual(source, {
            "type": "local_folder",
            "project_id": project_id,
            "snapshot_sha256": snapshot_sha,
        })
        self.assertNotIn("commit_sha", source)

    def test_provenance_manifest_tampering_is_rejected(self):
        payload = b"provenance-integrity"
        metadata = self.artifacts.store(
            self.jobs, self.job["id"], "runner-artifact", "manifest.zip",
            io.BytesIO(payload), len(payload),
        )
        with self.artifacts._db() as db:
            db.execute(
                "UPDATE artifacts SET provenance_json=? WHERE id=?",
                (json.dumps({"schema_version": 1, "source": {"type": "forged"}}), metadata["id"]),
            )
        with self.assertRaisesRegex(ArtifactError, "provenance integrity"):
            self.artifacts.get(metadata["id"])

    def test_existing_artifact_database_gets_additive_provenance_migration(self):
        legacy_root = self.root / "legacy-artifacts"
        legacy_root.mkdir()
        connection = sqlite3.connect(legacy_root / "metadata.sqlite3")
        try:
            connection.execute("""
                CREATE TABLE artifacts (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, worker_id TEXT NOT NULL,
                    name TEXT NOT NULL, storage_key TEXT NOT NULL UNIQUE,
                    size INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL
                )
            """)
            connection.commit()
        finally:
            connection.close()
        ArtifactStore(legacy_root, max_artifact_bytes=2048)
        connection = sqlite3.connect(legacy_root / "metadata.sqlite3")
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(artifacts)")}
        finally:
            connection.close()
        self.assertIn("provenance_json", columns)
        self.assertIn("provenance_sha256", columns)


if __name__ == "__main__":
    unittest.main()
