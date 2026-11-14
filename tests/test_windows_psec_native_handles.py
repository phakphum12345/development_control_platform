from __future__ import annotations

import unittest

from tools.local_runner_agent.windows_psec_native_handles import (
    FILE_ATTRIBUTE_DIRECTORY,
    FILE_ATTRIBUTE_REPARSE_POINT,
    HandleIdentity,
    NativeHandleAclError,
    OpenedObject,
    validate_relative_component,
)


class NativeHandlePreflightTests(unittest.TestCase):
    def test_accepts_single_plain_component(self):
        self.assertEqual(validate_relative_component("notes.txt"), "notes.txt")
        self.assertEqual(validate_relative_component("nested-folder"), "nested-folder")

    def test_rejects_empty_dot_and_parent_components(self):
        for value in ("", ".", ".."):
            with self.subTest(value=value), self.assertRaises(NativeHandleAclError):
                validate_relative_component(value)

    def test_rejects_path_and_stream_syntax(self):
        for value in ("a/b", r"a\b", "file:stream", "C:relative"):
            with self.subTest(value=value), self.assertRaises(NativeHandleAclError):
                validate_relative_component(value)

    def test_rejects_win32_normalized_suffixes_and_controls(self):
        for value in ("trailing.", "trailing ", "bad\nname"):
            with self.subTest(value=value), self.assertRaises(NativeHandleAclError):
                validate_relative_component(value)

    def test_rejects_component_over_nt_limit(self):
        with self.assertRaises(NativeHandleAclError):
            validate_relative_component("x" * 256)

    def test_identity_captures_full_file_id_and_object_kind(self):
        identity = HandleIdentity(
            volume_serial=7,
            file_id="00112233445566778899aabbccddeeff",
            is_directory=True,
            attributes=FILE_ATTRIBUTE_DIRECTORY,
            reparse_tag=0,
        )
        self.assertEqual(len(identity.file_id), 32)
        self.assertTrue(identity.is_directory)
        self.assertFalse(identity.attributes & FILE_ATTRIBUTE_REPARSE_POINT)

    def test_opened_object_close_is_idempotent(self):
        identity = HandleIdentity(7, "00" * 16, False, 0, 0)
        opened = OpenedObject(123, identity, "file.txt")
        closed = []

        def close_handle(handle):
            closed.append(handle)
            return True

        opened.close(close_handle)
        opened.close(close_handle)
        self.assertEqual(closed, [123])
        self.assertEqual(opened.handle, 0)

    def test_close_failure_is_reported(self):
        identity = HandleIdentity(7, "00" * 16, False, 0, 0)
        opened = OpenedObject(123, identity, "file.txt")
        with self.assertRaisesRegex(NativeHandleAclError, "CloseHandle"):
            opened.close(lambda _handle: False)
        self.assertEqual(opened.handle, 0)


if __name__ == "__main__":
    unittest.main()
