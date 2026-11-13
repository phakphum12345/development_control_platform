"""Tests for owner-approved Gateway document writes."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.document_workflow.gateway import DocumentWorkflowError, DocumentWorkflowStore
from tools.local_runner_agent.local_project import LocalProjectRegistry


class DocumentWorkflowStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.approved = self.base / "approved"
        self.project = self.approved / "sample"
        (self.project / "docs").mkdir(parents=True)
        (self.project / "src").mkdir()
        (self.project / "docs" / "README.md").write_text("# old\n", encoding="utf-8")
        self.registry = LocalProjectRegistry(self.base / "registry" / "projects.json")
        root = self.registry.enroll_root(self.approved)
        registered = self.registry.register_project(root["root_id"], self.project)
        self.project_id = registered["project_id"]
        self.store = DocumentWorkflowStore(
            self.base / "state" / "workflow.sqlite3",
            self.registry,
            self.base / "state" / "writer.sqlite3",
        )

    def tearDown(self):
        self.temp.cleanup()

    def grant(self, paths=("docs",)):
        return self.store.grant_scope(
            self.project_id, list(paths), "owner@example.test",
            "GRANT DOCUMENT WRITE SCOPE",
        )

    def propose(self, *, path="docs/ROADMAP.md", content="# Roadmap\n", expected=None, key="document-operation-0001"):
        return self.store.propose(
            project_id=self.project_id, relative_path=path, content=content,
            expected_sha256=expected, idempotency_key=key, actor="owner@example.test",
        )

    def test_scope_is_disabled_until_owner_grants_it(self):
        with self.assertRaises(DocumentWorkflowError) as error:
            self.propose()
        self.assertEqual(error.exception.status_code, 403)

    def test_grant_requires_explicit_confirmation_and_existing_directory(self):
        with self.assertRaises(DocumentWorkflowError):
            self.store.grant_scope(self.project_id, ["docs"], "owner", "yes")
        with self.assertRaises(DocumentWorkflowError):
            self.store.grant_scope(
                self.project_id, ["missing"], "owner", "GRANT DOCUMENT WRITE SCOPE"
            )
        grant = self.grant()
        self.assertEqual(grant["status"], "ACTIVE")
        self.assertEqual(grant["allowed_paths"], ["docs"])

    def test_proposal_approval_writes_and_verifies_exact_bytes(self):
        self.grant()
        content = "# Roadmap\n\n- Phase 1: Gateway approval\n"
        proposal = self.propose(content=content)
        self.assertEqual(proposal["status"], "PENDING")
        self.assertEqual(proposal["content_sha256"], hashlib.sha256(content.encode()).hexdigest())
        result = self.store.approve(
            proposal["proposal_id"], content_sha256=proposal["content_sha256"],
            actor="owner@example.test", confirmation="WRITE DOCUMENT",
        )
        target = self.project / "docs" / "ROADMAP.md"
        self.assertEqual(target.read_text(encoding="utf-8"), content)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["read_back_verified"])
        self.assertEqual(result["sha256"], proposal["content_sha256"])
        self.assertEqual(self.store.get_proposal(proposal["proposal_id"])["status"], "APPLIED")
        self.assertEqual(
            self.store.approve(
                proposal["proposal_id"], content_sha256=proposal["content_sha256"],
                actor="owner@example.test", confirmation="WRITE DOCUMENT",
            ),
            result,
        )

    def test_existing_file_requires_current_expected_sha(self):
        self.grant()
        target = self.project / "docs" / "README.md"
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        proposal = self.propose(
            path="docs/README.md", content="# updated\n", expected=current,
            key="document-operation-0002",
        )
        result = self.store.approve(
            proposal["proposal_id"], content_sha256=proposal["content_sha256"],
            actor="owner", confirmation="WRITE DOCUMENT",
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(target.read_text(encoding="utf-8"), "# updated\n")

    def test_stale_base_is_rejected_before_proposal(self):
        self.grant()
        with self.assertRaises(DocumentWorkflowError) as error:
            self.propose(path="docs/README.md", expected="0" * 64, key="document-operation-0003")
        self.assertEqual(error.exception.status_code, 409)

    def test_scope_does_not_allow_other_project_directories(self):
        self.grant()
        with self.assertRaises(DocumentWorkflowError) as error:
            self.propose(path="src/notes.md", key="document-operation-0004")
        self.assertEqual(error.exception.status_code, 403)

    def test_revoked_grant_blocks_new_proposals_and_pending_approval(self):
        grant = self.grant()
        pending = self.propose(key="document-operation-0005")
        self.store.revoke_grant(
            grant["grant_id"], "owner@example.test", "REVOKE DOCUMENT WRITE SCOPE"
        )
        with self.assertRaises(DocumentWorkflowError) as error:
            self.propose(key="document-operation-0006")
        self.assertEqual(error.exception.status_code, 403)
        with self.assertRaises(DocumentWorkflowError) as error:
            self.store.approve(
                pending["proposal_id"], content_sha256=pending["content_sha256"],
                actor="owner", confirmation="WRITE DOCUMENT",
            )
        self.assertEqual(error.exception.status_code, 403)

    def test_approval_is_bound_to_exact_digest_and_confirmation(self):
        self.grant()
        proposal = self.propose(key="document-operation-0007")
        with self.assertRaises(DocumentWorkflowError):
            self.store.approve(
                proposal["proposal_id"], content_sha256="0" * 64,
                actor="owner", confirmation="WRITE DOCUMENT",
            )
        with self.assertRaises(DocumentWorkflowError):
            self.store.approve(
                proposal["proposal_id"], content_sha256=proposal["content_sha256"],
                actor="owner", confirmation="yes",
            )

    def test_rejects_traversal_hidden_and_unsupported_paths(self):
        self.grant()
        for path in ("../outside.md", ".git/config.txt", ".github/workflows/README.md", "docs/file.json"):
            with self.subTest(path=path), self.assertRaises(DocumentWorkflowError):
                self.propose(path=path, key="document-operation-" + str(abs(hash(path)))[:8])

    def test_idempotency_key_cannot_be_reused_for_different_content(self):
        self.grant()
        self.propose(key="document-operation-0008")
        with self.assertRaises(DocumentWorkflowError) as error:
            self.propose(content="# Different\n", key="document-operation-0008")
        self.assertEqual(error.exception.status_code, 409)

    def test_content_limit_is_enforced_before_storage(self):
        self.grant()
        with self.assertRaises(DocumentWorkflowError) as error:
            self.propose(content="x" * (512 * 1024 + 1), key="document-operation-0009")
        self.assertEqual(error.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
