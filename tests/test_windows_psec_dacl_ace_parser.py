from __future__ import annotations

import unittest

from tools.local_runner_agent.windows_psec_dacl_ace_parser import (
    DaclAceParseError,
    parse_dacl,
)


def _sid(authority: int, *sub_authorities: int) -> bytes:
    return (
        bytes((1, len(sub_authorities)))
        + authority.to_bytes(6, "big")
        + b"".join(value.to_bytes(4, "little") for value in sub_authorities)
    )


def _ace(ace_type: int, sid: bytes, mask: int = 0x001200A9, flags: int = 0) -> bytes:
    size = 4 + 4 + len(sid)
    return bytes((ace_type, flags)) + size.to_bytes(2, "little") + mask.to_bytes(4, "little") + sid


def _acl(*aces: bytes, revision: int = 2, unused: bytes = b"") -> bytes:
    body = b"".join(aces)
    size = 8 + len(body) + len(unused)
    return bytes((revision, 0)) + size.to_bytes(2, "little") + len(aces).to_bytes(2, "little") + b"\x00\x00" + body + unused


class StrictDaclAceParserTests(unittest.TestCase):
    def test_parses_basic_allow_and_deny_aces_losslessly(self):
        package_sid = _sid(15, 2, 123, 456)
        allow = _ace(0, package_sid, flags=0x03)
        deny = _ace(1, _sid(5, 18), mask=0x00000001)
        parsed = parse_dacl(_acl(allow, deny))
        self.assertEqual(parsed.ace_count, 2)
        self.assertEqual(parsed.aces[0].sid, "S-1-15-2-123-456")
        self.assertEqual(parsed.aces[0].raw, allow)
        self.assertEqual(parsed.aces[0].ace_flags, 0x03)
        self.assertEqual(parsed.aces[1].sid, "S-1-5-18")
        self.assertEqual(parsed.aces[1].raw, deny)

    def test_preserves_unused_allocation_bytes(self):
        parsed = parse_dacl(_acl(_ace(0, _sid(5, 32, 544)), unused=b"\x00" * 12))
        self.assertEqual(parsed.unused_bytes, b"\x00" * 12)

    def test_accepts_acl_revision_four(self):
        parsed = parse_dacl(_acl(_ace(17, _sid(5, 18)), revision=4))
        self.assertEqual(parsed.revision, 4)
        self.assertEqual(parsed.aces[0].ace_type, 17)

    def test_rejects_unknown_object_and_callback_ace_layouts(self):
        for ace_type in (5, 6, 9, 11, 18, 19, 21):
            with self.subTest(ace_type=ace_type):
                with self.assertRaises(DaclAceParseError):
                    parse_dacl(_acl(_ace(ace_type, _sid(5, 18))))

    def test_rejects_acl_size_mismatch(self):
        raw = bytearray(_acl(_ace(0, _sid(5, 18))))
        raw[2:4] = (len(raw) - 1).to_bytes(2, "little")
        with self.assertRaises(DaclAceParseError):
            parse_dacl(bytes(raw))

    def test_rejects_truncated_ace_header_and_body(self):
        for raw in (
            bytes((2, 0, 10, 0, 1, 0, 0, 0, 0, 0)),
            bytes((2, 0, 12, 0, 1, 0, 0, 0, 0, 0, 0, 0)),
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(DaclAceParseError):
                    parse_dacl(raw)

    def test_rejects_non_aligned_and_out_of_bounds_ace_sizes(self):
        for ace_size in (15, 0x100):
            raw = bytearray(_acl(_ace(0, _sid(5, 18))))
            raw[10:12] = ace_size.to_bytes(2, "little")
            with self.subTest(ace_size=ace_size):
                with self.assertRaises(DaclAceParseError):
                    parse_dacl(bytes(raw))

    def test_rejects_invalid_sid_revision_count_and_length(self):
        valid = _ace(0, _sid(5, 18))
        cases = []
        bad_revision = bytearray(valid)
        bad_revision[8] = 2
        cases.append(bytes(bad_revision))
        bad_count = bytearray(valid)
        bad_count[9] = 16
        cases.append(bytes(bad_count))
        cases.append(valid[:-1])
        for ace in cases:
            with self.subTest(ace=ace):
                with self.assertRaises(DaclAceParseError):
                    parse_dacl(_acl(ace))

    def test_enforces_acl_and_ace_count_limits(self):
        raw = _acl(_ace(0, _sid(5, 18)))
        with self.assertRaises(DaclAceParseError):
            parse_dacl(raw, max_acl_bytes=8)
        with self.assertRaises(DaclAceParseError):
            parse_dacl(raw, max_aces=0)

    def test_rejects_non_bytes_and_invalid_limit_values(self):
        with self.assertRaises(DaclAceParseError):
            parse_dacl(bytearray(_acl()))
        with self.assertRaises(DaclAceParseError):
            parse_dacl(_acl(), max_aces=-1)


if __name__ == "__main__":
    unittest.main()
