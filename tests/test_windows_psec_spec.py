from __future__ import annotations

import struct
import unittest

from tools.local_runner_agent.windows_psec_spec import (
    PsecSpecError,
    build_psec_spec,
)


def _field_position(buffer: bytes, table_position: int, slot: int):
    vtable_delta = struct.unpack_from("<i", buffer, table_position)[0]
    vtable_position = table_position - vtable_delta
    vtable_length = struct.unpack_from("<H", buffer, vtable_position)[0]
    entry = vtable_position + 4 + slot * 2
    if entry + 2 > vtable_position + vtable_length:
        return None
    field_offset = struct.unpack_from("<H", buffer, entry)[0]
    return table_position + field_offset if field_offset else None


def _root_table(buffer: bytes) -> int:
    return struct.unpack_from("<I", buffer, 0)[0]


def _table_at(buffer: bytes, field_position: int) -> int:
    return field_position + struct.unpack_from("<I", buffer, field_position)[0]


def _string_at(buffer: bytes, target: int) -> str:
    size = struct.unpack_from("<I", buffer, target)[0]
    return buffer[target + 4:target + 4 + size].decode("utf-8")


def _vector_strings(buffer: bytes, table_position: int, slot: int) -> tuple[str, ...]:
    field = _field_position(buffer, table_position, slot)
    if field is None:
        return ()
    vector = _table_at(buffer, field)
    count = struct.unpack_from("<I", buffer, vector)[0]
    values = []
    for index in range(count):
        item = vector + 4 + index * 4
        values.append(_string_at(buffer, item + struct.unpack_from("<I", buffer, item)[0]))
    return tuple(values)


class WindowsPsecSpecTests(unittest.TestCase):
    def _build(self):
        return build_psec_spec(
            read_only_paths=(r"C:\Projects\DCP", r"C:\Python314"),
            read_write_paths=(r"C:\ProgramData\DCP\Terminal\job-1",),
            denied_paths=(r"C:\Users\runner", r"C:\ProgramData"),
            enumerate_paths=(r"C:\Projects\DCP", r"C:\Python314"),
            disallow_win32k_system_calls=True,
            ui_restrictions=0x3FF,
        )

    def test_psec_buffer_has_identifier_and_version_1_1(self):
        buffer = self._build()
        self.assertEqual(buffer[4:8], b"PSEC")
        root = _root_table(buffer)
        version_field = _field_position(buffer, root, 0)
        self.assertIsNotNone(version_field)
        self.assertEqual(struct.unpack_from("<HH", buffer, version_field), (1, 1))

    def test_psec_buffer_encodes_read_only_read_write_deny_and_enumerate_paths(self):
        buffer = self._build()
        root = _root_table(buffer)
        self.assertEqual(
            _vector_strings(buffer, root, 4),
            (r"C:\ProgramData\DCP\Terminal\job-1",),
        )
        self.assertEqual(
            _vector_strings(buffer, root, 5),
            (r"C:\Projects\DCP", r"C:\Python314"),
        )
        self.assertEqual(
            _vector_strings(buffer, root, 6),
            (r"C:\Users\runner", r"C:\ProgramData"),
        )
        self.assertEqual(
            _vector_strings(buffer, root, 8),
            (r"C:\Projects\DCP", r"C:\Python314"),
        )

    def test_network_policy_explicitly_denies_egress_ingress_and_host_loopback(self):
        buffer = self._build()
        root = _root_table(buffer)
        network_field = _field_position(buffer, root, 7)
        network = _table_at(buffer, network_field)
        egress_field = _field_position(buffer, network, 1)
        ingress_field = _field_position(buffer, network, 3)
        egress = _table_at(buffer, egress_field)
        ingress = _table_at(buffer, ingress_field)
        self.assertEqual(buffer[_field_position(buffer, egress, 0)], 0)
        self.assertEqual(buffer[_field_position(buffer, ingress, 0)], 0)
        self.assertEqual(buffer[_field_position(buffer, ingress, 1)], 0)

    def test_win32k_is_disabled_and_ui_restrictions_are_encoded(self):
        buffer = self._build()
        root = _root_table(buffer)
        win32k = _field_position(buffer, root, 2)
        ui = _field_position(buffer, root, 3)
        self.assertEqual(buffer[win32k], 1)
        self.assertEqual(struct.unpack_from("<Q", buffer, ui)[0], 0x3FF)

    def test_rejects_relative_unc_and_drive_root_paths(self):
        with self.assertRaises(PsecSpecError):
            build_psec_spec(read_only_paths=("relative",), read_write_paths=(r"C:\scratch",))
        with self.assertRaises(PsecSpecError):
            build_psec_spec(read_only_paths=(r"\\server\share",), read_write_paths=(r"C:\scratch",))
        with self.assertRaises(PsecSpecError):
            build_psec_spec(read_only_paths=(r"C:\",), read_write_paths=(r"D:\scratch",))

    def test_rejects_workspace_and_scratch_overlap(self):
        with self.assertRaisesRegex(PsecSpecError, "separate"):
            build_psec_spec(
                read_only_paths=(r"C:\Projects",),
                read_write_paths=(r"C:\Projects\scratch",),
            )

    def test_rejects_nonempty_capabilities(self):
        with self.assertRaisesRegex(PsecSpecError, "capabilities"):
            build_psec_spec(
                read_only_paths=(r"C:\Projects",),
                read_write_paths=(r"C:\scratch",),
                capabilities=("internetClient",),
            )


if __name__ == "__main__":
    unittest.main()
