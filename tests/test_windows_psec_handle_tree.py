from __future__ import annotations

import ctypes
import unittest

from tools.local_runner_agent.windows_psec_handle_tree import (
    FILE_ID_EXTD_DIR_INFO,
    FILE_ID_EXTD_DIRECTORY_INFO_CLASS,
    FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
    FILE_ATTRIBUTE_DIRECTORY,
    FILE_ATTRIBUTE_REPARSE_POINT,
    NativeHandleAclError,
    OpenedDirectoryChain,
    OpenedObject,
    HandleIdentity,
    parse_drive_absolute_path,
    parse_extended_directory_buffer,
)


def make_directory_record(name: str, file_id: bytes, *, attributes: int = 0, next_offset: int = 0) -> bytes:
    record = FILE_ID_EXTD_DIR_INFO()
    record.NextEntryOffset = next_offset
    record.FileAttributes = attributes
    encoded = name.encode("utf-16-le")
    record.FileNameLength = len(encoded)
    for index, value in enumerate(file_id):
        record.FileId.Identifier[index] = value
    header_size = FILE_ID_EXTD_DIR_INFO.FileName.offset
    raw = ctypes.string_at(ctypes.byref(record), header_size) + encoded
    return raw.ljust(max(ctypes.sizeof(FILE_ID_EXTD_DIR_INFO), len(raw)), b"\x00")


class HandleTreeContractTests(unittest.TestCase):
    def test_drive_absolute_path_is_split_without_path_resolution(self):
        self.assertEqual(parse_drive_absolute_path("c:\\work\\job"), ("C", ("work", "job")))
        self.assertEqual(parse_drive_absolute_path("D:\\"), ("D", ()))

    def test_rejects_unc_device_relative_and_normalized_paths(self):
        invalid = (
            "", "C:relative", "\\\\server\\share", "\\\\?\\C:\\work",
            "\\\\.\\PhysicalDrive0", "C:/work", "C:\\work\\..\\escape",
            "C:\\work\\name:stream", "C:\\work\\\\child",
        )
        for path in invalid:
            with self.subTest(path=path), self.assertRaises(NativeHandleAclError):
                parse_drive_absolute_path(path)

    def test_parses_extended_directory_entry_with_full_128_bit_id(self):
        identifier = bytes.fromhex("00112233445566778899aabbccddeeff")
        payload = make_directory_record("workspace.txt", identifier)
        entries = parse_extended_directory_buffer(payload)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "workspace.txt")
        self.assertEqual(entries[0].file_id, identifier.hex())
        self.assertFalse(entries[0].is_directory)

    def test_parses_directory_type_and_reparse_metadata(self):
        identifier = bytes.fromhex("ffeeddccbbaa99887766554433221100")
        payload = make_directory_record(
            "child", identifier,
            attributes=FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT,
        )
        entry = parse_extended_directory_buffer(payload)[0]
        self.assertTrue(entry.is_directory)
        self.assertTrue(entry.attributes & FILE_ATTRIBUTE_REPARSE_POINT)

    def test_rejects_truncated_and_invalid_utf16_records(self):
        with self.assertRaises(NativeHandleAclError):
            parse_extended_directory_buffer(b"\x00" * (FILE_ID_EXTD_DIR_INFO.FileName.offset - 1))
        record = FILE_ID_EXTD_DIR_INFO()
        record.FileNameLength = 1
        malformed = ctypes.string_at(ctypes.byref(record), ctypes.sizeof(record))
        with self.assertRaises(NativeHandleAclError):
            parse_extended_directory_buffer(malformed)

    def test_rejects_invalid_next_entry_offset(self):
        identifier = bytes.fromhex("00112233445566778899aabbccddeeff")
        payload = bytearray(make_directory_record("first", identifier, next_offset=1))
        with self.assertRaisesRegex(NativeHandleAclError, "next-entry offset"):
            parse_extended_directory_buffer(bytes(payload))

    def test_directory_chain_closes_handles_in_reverse_order(self):
        identity = HandleIdentity(1, "00" * 16, True, FILE_ATTRIBUTE_DIRECTORY, 0)
        chain = OpenedDirectoryChain(
            api=type("Api", (), {"close": lambda self, handle: calls.append(handle) or True})(),
            objects=[
                OpenedObject(10, identity, "C:\\"),
                OpenedObject(11, identity, "job"),
                OpenedObject(12, identity, "workspace"),
            ],
        )
        calls = []
        chain.close()
        self.assertEqual(calls, [12, 11, 10])

    def test_directory_info_class_uses_extended_128_bit_records(self):
        self.assertEqual(FILE_ID_EXTD_DIRECTORY_INFO_CLASS, 19)
        self.assertEqual(FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS, 20)
        self.assertEqual(len(FILE_ID_EXTD_DIR_INFO.FileId.offset.to_bytes(2, "little")), 2)


if __name__ == "__main__":
    unittest.main()
