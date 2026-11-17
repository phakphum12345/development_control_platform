from __future__ import annotations

import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.windows_psec_acl import WindowsPsecAclError
from tools.local_runner_agent.windows_psec_acl_handles import (
    FILE_ATTRIBUTE_DIRECTORY,
    FILE_ATTRIBUTE_REPARSE_POINT,
    FILE_DELETE_CHILD,
    DirectoryEntry,
    HandleEntry,
    WindowsPsecHandleAclManager,
)


_PACKAGE_SID = "S-1-15-2-123-456-789"


class FakeHandleAclApi:
    def __init__(self):
        self.sddl: dict[str, str] = {}
        self.closed: list[str] = []
        self.restored: list[str] = []
        self.writes: list[str] = []
        self.identity_checks: dict[str, int] = {}
        self.fail_verify_after: dict[str, int] = {}
        self.streams: dict[str, list[str]] = {}
        self.fail_on_write: int | None = None
        self.swap_name: str | None = None

    def _entry(self, path: Path) -> HandleEntry:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            attributes = FILE_ATTRIBUTE_REPARSE_POINT
            is_directory = False
        elif stat.S_ISDIR(info.st_mode):
            attributes = FILE_ATTRIBUTE_DIRECTORY
            is_directory = True
        elif stat.S_ISREG(info.st_mode):
            attributes = 0
            is_directory = False
        else:
            raise WindowsPsecAclError(f"unsupported fake object: {path}")
        return HandleEntry(
            handle=path,
            path=str(path),
            is_directory=is_directory,
            volume_serial=1,
            file_id=int(info.st_ino),
            attributes=attributes,
            link_count=int(info.st_nlink),
        )

    def open_ancestor_chain(self, directory):
        return [self._entry(Path(directory))]

    def enumerate_directory(self, directory: HandleEntry):
        entries = []
        with os.scandir(directory.path) as iterator:
            for entry in iterator:
                path = Path(entry.path)
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    attributes = FILE_ATTRIBUTE_REPARSE_POINT
                elif stat.S_ISDIR(info.st_mode):
                    attributes = FILE_ATTRIBUTE_DIRECTORY
                else:
                    attributes = 0
                entries.append(DirectoryEntry(
                    entry.name, attributes, int(info.st_ino)
                ))
        return entries

    def open_child(
        self, parent, name, *, is_directory, expected_file_id, write_dac=True
    ):
        path = Path(parent.path) / name
        item = self._entry(path)
        if item.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise WindowsPsecAclError("fake relative open encountered reparse point")
        if item.is_directory != is_directory:
            raise WindowsPsecAclError("fake relative open type mismatch")
        if name == self.swap_name:
            item.file_id += 1
        if item.file_id != expected_file_id:
            raise WindowsPsecAclError("fake file identity changed after enumeration")
        return item

    def verify_identity(self, item):
        count = self.identity_checks.get(item.path, 0) + 1
        self.identity_checks[item.path] = count
        if self.fail_verify_after.get(item.path) == count:
            raise WindowsPsecAclError(
                f"filesystem object identity or type changed before ACL mutation: {item.path}"
            )
        current = os.lstat(item.path)
        if (
            stat.S_ISLNK(current.st_mode)
            or stat.S_ISDIR(current.st_mode) != item.is_directory
            or current.st_ino != item.file_id
            or current.st_nlink != item.link_count
            or (not item.is_directory and current.st_nlink != 1)
        ):
            raise WindowsPsecAclError(
                f"filesystem object identity or type changed before ACL mutation: {item.path}"
            )

    def enumerate_streams(self, item):
        return self.streams.get(item.path, ["::$DATA"])

    def read_sddl(self, item):
        return self.sddl.setdefault(item.path, "D:")

    def snapshot_dacl(self, item):
        return self.read_sddl(item)

    def restore_dacl(self, item, snapshot):
        self.restored.append(item.path)
        self.sddl[item.path] = snapshot

    def add_allow_ace(self, item, package_sid, mask, inheritance):
        if self.fail_on_write == len(self.writes) + 1:
            raise WindowsPsecAclError("injected DACL write failure")
        flags = ""
        if inheritance & 0x01:
            flags += "OI"
        if inheritance & 0x02:
            flags += "CI"
        ace = f"(A;{flags};0x{mask:08x};;;{package_sid})"
        self.sddl[item.path] = self.read_sddl(item) + ace
        self.writes.append(item.path)

    def close_handle(self, handle):
        self.closed.append(str(handle))


class WindowsPsecHandleAclManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.parent = Path(self.temporary.name) / "private-parent"
        self.parent.mkdir()
        self.job_root = Path(tempfile.mkdtemp(
            prefix="dcp-psec-job-", dir=str(self.parent)
        ))
        self.workspace = self.job_root / "workspace"
        self.scratch = self.job_root / "scratch"
        self.workspace.mkdir()
        self.scratch.mkdir()
        (self.workspace / "read.txt").write_text("read-only", encoding="utf-8")
        (self.workspace / "nested").mkdir()
        (self.workspace / "nested" / "more.txt").write_text(
            "nested", encoding="utf-8"
        )
        (self.scratch / "scratch.txt").write_text("scratch", encoding="utf-8")
        self.api = FakeHandleAclApi()
        self.manager = WindowsPsecHandleAclManager(api=self.api)

    def tearDown(self):
        shutil.rmtree(self.job_root, ignore_errors=True)
        self.temporary.cleanup()

    def test_handle_relative_apply_verifies_exact_targets_and_parent_unchanged(self):
        parent_before = self.api.read_sddl(self.api._entry(self.parent))
        authorization = self.manager.apply(
            self.workspace, self.scratch, _PACKAGE_SID
        )
        self.assertEqual(authorization.evidence["state"], "DACL_VERIFIED")
        self.assertTrue(authorization.evidence["handle_relative"])
        self.assertTrue(authorization.evidence["shared_parent_sddl_unchanged"])
        self.assertTrue(authorization.evidence["shared_ancestor_sddl_unchanged"])
        self.assertEqual(authorization.evidence["workspace_targets"], 4)
        self.assertEqual(authorization.evidence["scratch_targets"], 2)
        self.assertEqual(FILE_DELETE_CHILD, 0x40)
        scratch_root_sddl = self.api.read_sddl(self.api._entry(self.scratch))
        self.assertIn("0x001301bf", scratch_root_sddl)
        self.assertIn("0x00000040", scratch_root_sddl)
        scratch_file_sddl = self.api.read_sddl(
            self.api._entry(self.scratch / "scratch.txt")
        )
        self.assertIn("0x001301bf", scratch_file_sddl)
        self.assertNotIn("0x00000040", scratch_file_sddl)
        self.assertEqual(
            self.api.read_sddl(self.api._entry(self.parent)), parent_before
        )
        self.assertTrue(self.api.writes)
        authorization.close()
        self.assertGreaterEqual(len(self.api.closed), 1)

    def test_alternate_data_stream_is_rejected_before_any_dacl_write(self):
        target = str(self.workspace / "read.txt")
        self.api.streams[target] = ["::$DATA", ":hidden:$DATA"]

        with self.assertRaisesRegex(WindowsPsecAclError, "alternate or unsupported data stream"):
            WindowsPsecHandleAclManager(self.api).apply(
                self.workspace, self.scratch, "S-1-15-2-123-456"
            )

        self.assertEqual(self.api.writes, [])
        self.assertTrue(self.api.closed)

    def test_identity_change_before_acl_mutation_rolls_back_prior_targets(self):
        target = str(self.workspace / "read.txt")
        self.api.fail_verify_after[target] = 3

        with self.assertRaisesRegex(WindowsPsecAclError, "identity or type changed"):
            WindowsPsecHandleAclManager(self.api).apply(
                self.workspace, self.scratch, "S-1-15-2-123-456"
            )

        self.assertGreater(len(self.api.writes), 0)
        self.assertEqual(self.api.read_sddl(self.api._entry(self.job_root)), "D:")
        self.assertEqual(self.api.read_sddl(self.api._entry(self.workspace)), "D:")
        self.assertTrue(self.api.restored)
        self.assertTrue(self.api.closed)

    def test_reapplying_verified_acl_is_idempotent(self):
        first = self.manager.apply(self.workspace, self.scratch, _PACKAGE_SID)
        first.close()
        first_write_count = len(self.api.writes)

        second = self.manager.apply(self.workspace, self.scratch, _PACKAGE_SID)
        self.assertEqual(len(self.api.writes), first_write_count)
        self.assertEqual(second.evidence["state"], "DACL_VERIFIED")
        second.close()

    def test_partial_acl_failure_rolls_back_every_changed_target(self):
        self.api.fail_on_write = 4
        with self.assertRaisesRegex(WindowsPsecAclError, "rollback=VERIFIED"):
            self.manager.apply(self.workspace, self.scratch, _PACKAGE_SID)
        self.assertEqual(self.api.read_sddl(self.api._entry(self.job_root)), "D:")
        self.assertEqual(self.api.read_sddl(self.api._entry(self.workspace)), "D:")
        self.assertEqual(
            self.api.restored,
            [str(self.job_root), str(self.workspace), str(self.workspace / "nested"),
             str(self.workspace / "read.txt")],
        )
        self.assertTrue(self.api.closed)

    def test_identity_swap_between_enumeration_and_relative_open_fails_before_write(self):
        self.api.swap_name = "read.txt"
        with self.assertRaisesRegex(WindowsPsecAclError, "identity changed"):
            self.manager.apply(self.workspace, self.scratch, _PACKAGE_SID)
        self.assertEqual(self.api.writes, [])
        self.assertTrue(self.api.closed)

    def test_reparse_point_is_rejected_before_any_acl_write(self):
        link = self.workspace / "reparse-link"
        try:
            link.symlink_to(self.scratch, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this host")
        with self.assertRaisesRegex(WindowsPsecAclError, "reparse point"):
            self.manager.apply(self.workspace, self.scratch, _PACKAGE_SID)
        self.assertEqual(self.api.writes, [])

    def test_non_package_sid_is_rejected(self):
        with self.assertRaisesRegex(WindowsPsecAclError, "Package SID is invalid"):
            self.manager.apply(self.workspace, self.scratch, "S-1-5-21-1-2-3")


@unittest.skipUnless(
    os.name == "nt" and os.environ.get("DCP_PSEC_HANDLE_ACL_TEST") == "1",
    "requires opt-in real Windows NTFS handle-relative ACL acceptance",
)
class WindowsPsecHandleAclRealHostTests(unittest.TestCase):
    def test_real_ntfs_handle_relative_acl_round_trip(self):
        parent_value = os.environ.get("DCP_PSEC_ACCEPTANCE_PARENT")
        package_sid = os.environ.get("DCP_PSEC_HANDLE_ACL_PACKAGE_SID")
        if not parent_value or not package_sid:
            self.fail("DCP_PSEC_ACCEPTANCE_PARENT and package SID are required")
        parent = Path(parent_value).resolve(strict=True)
        job_root = Path(tempfile.mkdtemp(prefix="dcp-psec-job-", dir=str(parent)))
        workspace = job_root / "workspace"
        scratch = job_root / "scratch"
        authorization = None
        try:
            workspace.mkdir()
            scratch.mkdir()
            (workspace / "read.txt").write_text("read-only", encoding="utf-8")
            (workspace / "nested").mkdir()
            (workspace / "nested" / "more.txt").write_text(
                "nested", encoding="utf-8"
            )
            (scratch / "scratch.txt").write_text("scratch", encoding="utf-8")
            authorization = WindowsPsecHandleAclManager().apply(
                workspace, scratch, package_sid
            )
            self.assertEqual(authorization.evidence["state"], "DACL_VERIFIED")
            self.assertTrue(authorization.evidence["handle_relative"])
            self.assertTrue(
                authorization.evidence["shared_parent_sddl_unchanged"]
            )
            self.assertTrue(
                authorization.evidence["shared_ancestor_sddl_unchanged"]
            )
            self.assertEqual(authorization.evidence["filesystem"], "NTFS")
        finally:
            if authorization is not None:
                authorization.close()
            shutil.rmtree(job_root)


if __name__ == "__main__":
    unittest.main()
