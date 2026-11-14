from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tools.local_runner_agent.windows_psec_native_handles import WindowsNativeHandleApi
from tools.local_runner_agent.windows_psec_handle_tree import WindowsNativeHandleTree


@unittest.skipUnless(os.name == "nt", "native handle tree acceptance requires Windows")
class WindowsNativeHandleTreeRealHostTests(unittest.TestCase):
    def test_drive_root_traversal_and_extended_id_enumeration(self):
        with tempfile.TemporaryDirectory(prefix="dcp-psec-handle-tree-") as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            (root / "payload.txt").write_text("read-only enumeration fixture", encoding="utf-8")
            api = WindowsNativeHandleApi()
            tree = WindowsNativeHandleTree(api)
            chain = None
            children = []
            try:
                chain = tree.open_directory_chain(str(root))
                self.assertTrue(chain.leaf.identity.is_directory)
                children = tree.enumerate_open_children(chain.leaf, max_entries=32)
                found = {child.relative_name: child for child in children}
                self.assertEqual(set(found), {"nested", "payload.txt"})
                self.assertTrue(found["nested"].identity.is_directory)
                self.assertFalse(found["payload.txt"].identity.is_directory)
                self.assertEqual(len(found["nested"].identity.file_id), 32)
                self.assertEqual(len(found["payload.txt"].identity.file_id), 32)
            finally:
                for child in reversed(children):
                    child.close(api.close)
                if chain is not None:
                    chain.close()


if __name__ == "__main__":
    unittest.main()
