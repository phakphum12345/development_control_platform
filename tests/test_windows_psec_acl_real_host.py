"""Opt-in real Win32 ACL API smoke test on an isolated disposable NTFS tree.

Run only on a dedicated Windows acceptance host after setting:
  DCP_PSEC_REAL_ACL_TEST=1
  DCP_PSEC_REAL_ACL_PACKAGE_SID=<captured AppContainer Package SID>
  DCP_PSEC_ACCEPTANCE_PARENT=<pre-created, trusted acceptance directory>

The test never changes the acceptance parent's DACL. It creates and removes only
its own child tree. It validates the native Win32 ACL adapter and SDDL
read-back; it does not prove AppContainer effective access or launcher safety.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.windows_psec_acl import (
    WindowsPsecAclManager,
    _WindowsAclApi,
    _valid_package_sid,
)


_REAL_HOST_ENABLED = (
    os.name == "nt"
    and os.environ.get("DCP_PSEC_REAL_ACL_TEST") == "1"
)


@unittest.skipUnless(
    _REAL_HOST_ENABLED,
    "opt-in real Win32 ACL test; requires explicit dedicated-host opt-in",
)
class WindowsPsecAclRealHostTests(unittest.TestCase):
    def test_native_acl_api_round_trip_on_private_ntfs_tree(self):
        acceptance_parent_raw = os.environ.get("DCP_PSEC_ACCEPTANCE_PARENT")
        package_sid = os.environ.get("DCP_PSEC_REAL_ACL_PACKAGE_SID")
        self.assertTrue(acceptance_parent_raw, "DCP_PSEC_ACCEPTANCE_PARENT is required")
        self.assertTrue(package_sid, "DCP_PSEC_REAL_ACL_PACKAGE_SID is required")
        self.assertTrue(_valid_package_sid(package_sid), "Package SID is invalid")

        acceptance_parent = Path(acceptance_parent_raw)
        self.assertTrue(acceptance_parent.is_absolute())
        self.assertTrue(acceptance_parent.is_dir())
        self.assertFalse(acceptance_parent.is_symlink())

        api = _WindowsAclApi()
        acceptance_parent_before = api.read_sddl(acceptance_parent)

        with tempfile.TemporaryDirectory(
            prefix="dcp-psec-acl-real-", dir=str(acceptance_parent)
        ) as temporary_parent_raw:
            temporary_parent = Path(temporary_parent_raw)
            temporary_parent_before = api.read_sddl(temporary_parent)

            job_root = temporary_parent / "dcp-psec-job-real-host"
            workspace = job_root / "workspace"
            scratch = job_root / "scratch"
            (workspace / "nested").mkdir(parents=True)
            scratch.mkdir()
            (workspace / "read.txt").write_text("workspace", encoding="utf-8")
            (workspace / "nested" / "child.txt").write_text("nested", encoding="utf-8")
            (scratch / "scratch.txt").write_text("scratch", encoding="utf-8")

            result = WindowsPsecAclManager(api).apply(
                workspace, scratch, package_sid
            )

            self.assertEqual(result["state"], "VERIFIED")
            self.assertTrue(result["job_root_traverse_only"])
            self.assertTrue(result["shared_parent_sddl_unchanged"])
            self.assertEqual(result["workspace_targets"], 4)
            self.assertEqual(result["scratch_targets"], 2)

            # Confirm the actual Win32 read-back contains the exact Package SID
            # on every intended target, with no ACE on the shared parent.
            for target in result["targets"]:
                self.assertIn(package_sid, target["sddl"])
            self.assertNotIn(package_sid, api.read_sddl(temporary_parent))
            self.assertEqual(temporary_parent_before, api.read_sddl(temporary_parent))

        self.assertEqual(
            acceptance_parent_before, api.read_sddl(acceptance_parent),
            "acceptance parent DACL changed during real-host ACL test",
        )


if __name__ == "__main__":
    unittest.main()
