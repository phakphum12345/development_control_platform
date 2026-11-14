from __future__ import annotations

import ctypes
import os
import tempfile
import unittest
from ctypes import wintypes
from pathlib import Path

from tools.local_runner_agent.windows_psec_security_descriptor_reader import (
    WindowsHandleSecurityReader,
    WindowsSecurityDescriptorReadError,
)
from tools.local_runner_agent.windows_psec_security_descriptor_transaction import (
    DescriptorSnapshot,
)


@unittest.skipUnless(os.name == "nt", "native security descriptor reader requires Windows")
class WindowsSecurityDescriptorReaderRealHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        cls.kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        cls.kernel32.CreateFileW.restype = wintypes.HANDLE
        cls.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        cls.kernel32.CloseHandle.restype = wintypes.BOOL
        cls.reader = WindowsHandleSecurityReader()

    def _open_for_read_control(self, path: Path, *, directory: bool) -> int:
        flags = 0x02000000 if directory else 0
        handle = self.kernel32.CreateFileW(
            str(path),
            0x00020000 | 0x00000080,  # READ_CONTROL | FILE_READ_ATTRIBUTES
            0x1 | 0x2 | 0x4,
            None,
            3,  # OPEN_EXISTING
            flags,
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        if not handle or int(handle) == invalid:
            raise OSError(ctypes.get_last_error(), "CreateFileW failed")
        return int(handle)

    def test_reads_directory_dacl_twice_without_mutating_it(self):
        with tempfile.TemporaryDirectory(prefix="dcp-psec-sd-reader-") as root:
            handle = self._open_for_read_control(Path(root), directory=True)
            try:
                identity_before = self.reader.query_identity(handle)
                first = self.reader.read_dacl(handle)
                second = self.reader.read_dacl(handle)
                identity_after = self.reader.query_identity(handle)

                self.assertIsInstance(first, DescriptorSnapshot)
                first.validate(max_descriptor_bytes=0xFFFF, max_aces=4096)
                self.assertEqual(first, second)
                self.assertEqual(identity_before, identity_after)
                self.assertTrue(identity_before.is_directory)
                self.assertTrue(first.dacl_present)
                self.assertFalse(first.dacl_is_null)
                self.assertGreaterEqual(len(first.dacl_bytes), 8)
            finally:
                if not self.kernel32.CloseHandle(wintypes.HANDLE(handle)):
                    raise OSError(ctypes.get_last_error(), "CloseHandle failed")

    def test_reads_file_dacl_through_its_retained_handle(self):
        with tempfile.TemporaryDirectory(prefix="dcp-psec-sd-reader-") as root:
            path = Path(root) / "probe.bin"
            path.write_bytes(b"read-only descriptor probe")
            handle = self._open_for_read_control(path, directory=False)
            try:
                identity = self.reader.query_identity(handle)
                snapshot = self.reader.read_dacl(handle)
                snapshot.validate(max_descriptor_bytes=0xFFFF, max_aces=4096)
                self.assertFalse(identity.is_directory)
                self.assertTrue(snapshot.dacl_present)
                self.assertFalse(snapshot.dacl_is_null)
            finally:
                if not self.kernel32.CloseHandle(wintypes.HANDLE(handle)):
                    raise OSError(ctypes.get_last_error(), "CloseHandle failed")

    def test_rejects_invalid_handle_before_native_call(self):
        with self.assertRaises(WindowsSecurityDescriptorReadError):
            self.reader.read_dacl(-1)


if __name__ == "__main__":
    unittest.main()
