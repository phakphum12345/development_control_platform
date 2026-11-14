from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.windows_psec_acl import (
    FILE_TRAVERSE,
    MODIFY,
    READ_EXECUTE,
    WindowsPsecAclError,
    WindowsPsecAclManager,
    _valid_package_sid,
)


PACKAGE_SID = "S-1-15-2-123-456-789"


class FakeAclApi:
    def __init__(self):
        self.entries = {}

    def read_sddl(self, path):
        return "D:" + "".join(self.entries.get(str(path), []))

    def add_allow_ace(self, path, package_sid, mask, inheritance):
        flags = "OICI" if inheritance == 3 else ""
        self.entries.setdefault(str(path), []).append(
            f"(A;{flags};0x{mask:08x};;;{package_sid})"
        )


class WindowsPsecAclManagerTests(unittest.TestCase):
    def _job_tree(self, parent):
        job = Path(parent) / "dcp-psec-job-test"
        work = job / "workspace"
        scratch = job / "scratch"
        (work / "nested").mkdir(parents=True)
        scratch.mkdir()
        (work / "read.txt").write_text("read", encoding="utf-8")
        (work / "nested" / "child.txt").write_text("child", encoding="utf-8")
        (scratch / "existing.tmp").write_text("scratch", encoding="utf-8")
        return job, work, scratch

    def test_package_sid_validation_is_strict(self):
        self.assertTrue(_valid_package_sid(PACKAGE_SID))
        self.assertFalse(_valid_package_sid("S-1-5-21-1"))
        self.assertFalse(_valid_package_sid("S-1-15-2-4294967296"))
        self.assertFalse(_valid_package_sid("S-1-15-2-1-not-a-number"))

    def test_applies_exact_grants_to_private_tree_and_leaves_parent_unchanged(self):
        with tempfile.TemporaryDirectory() as parent:
            job, work, scratch = self._job_tree(parent)
            api = FakeAclApi()
            result = WindowsPsecAclManager(api).apply(work, scratch, PACKAGE_SID)

        self.assertEqual(result["state"], "VERIFIED")
        self.assertTrue(result["job_root_traverse_only"])
        self.assertTrue(result["shared_parent_sddl_unchanged"])
        self.assertEqual(result["workspace_targets"], 4)
        self.assertEqual(result["scratch_targets"], 2)
        self.assertIn(f"(A;;0x{FILE_TRAVERSE:08x};;;{PACKAGE_SID})", api.read_sddl(job))
        self.assertIn(f"(A;OICI;0x{READ_EXECUTE:08x};;;{PACKAGE_SID})", api.read_sddl(work))
        self.assertIn(f"(A;OICI;0x{MODIFY:08x};;;{PACKAGE_SID})", api.read_sddl(scratch))
        self.assertEqual(api.read_sddl(Path(parent)), "D:")

    def test_rejects_non_job_private_layout_before_any_acl_write(self):
        with tempfile.TemporaryDirectory() as parent:
            work = Path(parent) / "workspace"
            scratch = Path(parent) / "scratch"
            work.mkdir()
            scratch.mkdir()
            api = FakeAclApi()
            with self.assertRaisesRegex(WindowsPsecAclError, "dcp-psec-job"):
                WindowsPsecAclManager(api).apply(work, scratch, PACKAGE_SID)
            self.assertEqual(api.entries, {})

    def test_rejects_workspace_scratch_overlap(self):
        with tempfile.TemporaryDirectory() as parent:
            job = Path(parent) / "dcp-psec-job-overlap"
            work = job / "workspace"
            scratch = work / "scratch"
            scratch.mkdir(parents=True)
            api = FakeAclApi()
            with self.assertRaises(WindowsPsecAclError):
                WindowsPsecAclManager(api).apply(work, scratch, PACKAGE_SID)
            self.assertEqual(api.entries, {})

    def test_rejects_reparse_point_before_acl_mutation(self):
        with tempfile.TemporaryDirectory() as parent, tempfile.TemporaryDirectory() as outside:
            job, work, scratch = self._job_tree(parent)
            (work / "linked").symlink_to(Path(outside), target_is_directory=True)
            api = FakeAclApi()
            with self.assertRaisesRegex(WindowsPsecAclError, "reparse"):
                WindowsPsecAclManager(api).apply(work, scratch, PACKAGE_SID)
            self.assertEqual(api.entries, {})

    def test_rejects_overbroad_existing_package_sid_ace(self):
        class OverbroadApi(FakeAclApi):
            def add_allow_ace(self, path, package_sid, mask, inheritance):
                super().add_allow_ace(path, package_sid, mask, inheritance)
                if path.name == "workspace":
                    self.entries[str(path)].append(
                        f"(A;OICI;0x{MODIFY:08x};;;{package_sid})"
                    )

        with tempfile.TemporaryDirectory() as parent:
            _, work, scratch = self._job_tree(parent)
            with self.assertRaisesRegex(WindowsPsecAclError, "overbroad"):
                WindowsPsecAclManager(OverbroadApi()).apply(work, scratch, PACKAGE_SID)


if __name__ == "__main__":
    unittest.main()
