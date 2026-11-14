from __future__ import annotations

import unittest

from tools.local_runner_agent.windows_psec_dacl_ace_parser import parse_dacl
from tools.local_runner_agent.windows_psec_dacl_candidate_builder import (
    DaclCandidateBuildError,
    FILE_TRAVERSE,
    MODIFY,
    READ_EXECUTE,
    build_dacl_candidate,
)


PACKAGE_SID = "S-1-15-2-123-456-789"


def _sid(authority: int, *sub_authorities: int) -> bytes:
    return (
        bytes((1, len(sub_authorities)))
        + authority.to_bytes(6, "big")
        + b"".join(value.to_bytes(4, "little") for value in sub_authorities)
    )


def _ace(ace_type: int, sid: bytes, mask: int, flags: int = 0) -> bytes:
    size = 8 + len(sid)
    return bytes((ace_type, flags)) + size.to_bytes(2, "little") + mask.to_bytes(4, "little") + sid


def _acl(*aces: bytes, unused: bytes = b"", revision: int = 2) -> bytes:
    body = b"".join(aces) + unused
    size = 8 + len(body)
    return bytes((revision, 0x5A)) + size.to_bytes(2, "little") + len(aces).to_bytes(2, "little") + b"\xA5\x5A" + body


def _parsed(raw: bytes):
    return parse_dacl(raw)


class DaclCandidateBuilderTests(unittest.TestCase):
    def test_workspace_directory_adds_explicit_read_execute_without_inheritance(self):
        existing = _ace(0, _sid(5, 18), 0x00120089)
        source = _acl(existing, unused=b"\x00" * 8)
        result = build_dacl_candidate(source, PACKAGE_SID, "workspace", is_directory=True, dacl_control_flags=0x1000)
        parsed = _parsed(result.raw_acl)
        self.assertTrue(result.inserted)
        self.assertEqual(result.access_mask, READ_EXECUTE)
        self.assertEqual(result.inheritance_flags, 0)
        self.assertEqual(result.dacl_control_flags, 0x1000)
        self.assertEqual(parsed.aces[0].raw, existing)
        self.assertEqual(parsed.aces[1].sid, PACKAGE_SID)
        self.assertEqual(parsed.aces[1].access_mask, READ_EXECUTE)
        self.assertEqual(parsed.aces[1].ace_flags, 0)
        self.assertEqual(parsed.unused_bytes, b"\x00" * 8)

    def test_workspace_child_objects_require_separate_explicit_grants(self):
        inherited = _ace(0, _sid(15, 2, 123, 456, 789), READ_EXECUTE, flags=0x10)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(inherited), PACKAGE_SID, "workspace", is_directory=False)

    def test_scratch_directory_adds_explicit_modify_without_inheritance(self):
        result = build_dacl_candidate(_acl(), PACKAGE_SID, "scratch", is_directory=True)
        ace = _parsed(result.raw_acl).aces[0]
        self.assertEqual(ace.access_mask, MODIFY)
        self.assertEqual(ace.ace_flags, 0)

    def test_scratch_file_adds_modify_without_inheritance(self):
        result = build_dacl_candidate(_acl(), PACKAGE_SID, "scratch", is_directory=False)
        ace = _parsed(result.raw_acl).aces[0]
        self.assertEqual(ace.access_mask, MODIFY)
        self.assertEqual(ace.ace_flags, 0)

    def test_job_root_directory_adds_traverse_only(self):
        result = build_dacl_candidate(_acl(), PACKAGE_SID, "job_root", is_directory=True)
        ace = _parsed(result.raw_acl).aces[0]
        self.assertEqual(ace.access_mask, FILE_TRAVERSE)
        self.assertEqual(ace.ace_flags, 0)

    def test_inserts_explicit_allow_before_inherited_aces(self):
        explicit_deny = _ace(1, _sid(5, 18), 1)
        inherited_allow = _ace(0, _sid(5, 32, 544), 0x00120089, flags=0x10)
        source = _acl(explicit_deny, inherited_allow)
        result = build_dacl_candidate(source, PACKAGE_SID, "workspace", is_directory=False)
        parsed = _parsed(result.raw_acl)
        self.assertEqual([ace.ace_type for ace in parsed.aces], [1, 0, 0])
        self.assertEqual(parsed.aces[0].raw, explicit_deny)
        self.assertEqual(parsed.aces[2].raw, inherited_allow)

    def test_preserves_existing_ace_bytes_and_relative_order(self):
        first = _ace(1, _sid(5, 18), 1)
        second = _ace(0, _sid(5, 32, 544), 0x00120089)
        source = _acl(first, second)
        result = build_dacl_candidate(source, PACKAGE_SID, "workspace", is_directory=False)
        original = [ace.raw for ace in _parsed(source).aces]
        candidate = [ace.raw for ace in _parsed(result.raw_acl).aces]
        self.assertEqual([ace for ace in candidate if ace in original], original)

    def test_preserves_acl_header_reserved_bytes_revision_and_padding(self):
        source = _acl(unused=b"\x00" * 16, revision=4)
        result = build_dacl_candidate(source, PACKAGE_SID, "workspace", is_directory=False)
        self.assertEqual(result.raw_acl[:2], source[:2])
        self.assertEqual(result.raw_acl[6:8], source[6:8])
        self.assertEqual(result.acl_revision, 4)
        self.assertEqual(_parsed(result.raw_acl).unused_bytes, b"\x00" * 16)

    def test_exact_existing_package_grant_is_idempotent(self):
        exact = _ace(0, _sid(15, 2, 123, 456, 789), READ_EXECUTE)
        source = _acl(exact)
        result = build_dacl_candidate(source, PACKAGE_SID, "workspace", is_directory=False)
        self.assertFalse(result.inserted)
        self.assertEqual(result.raw_acl, source)
        self.assertEqual(result.ace_count, 1)

    def test_rejects_duplicate_package_sid_aces(self):
        exact = _ace(0, _sid(15, 2, 123, 456, 789), READ_EXECUTE)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(exact, exact), PACKAGE_SID, "workspace", is_directory=False)

    def test_rejects_overbroad_or_wrong_mask_package_grant(self):
        broad = _ace(0, _sid(15, 2, 123, 456, 789), 0x001F01FF)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(broad), PACKAGE_SID, "workspace", is_directory=False)

    def test_rejects_package_sid_deny_ace(self):
        deny = _ace(1, _sid(15, 2, 123, 456, 789), 1)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(deny), PACKAGE_SID, "workspace", is_directory=False)

    def test_rejects_existing_grant_with_wrong_inheritance(self):
        wrong = _ace(0, _sid(15, 2, 123, 456, 789), READ_EXECUTE, flags=3)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(wrong), PACKAGE_SID, "workspace", is_directory=False)

    def test_rejects_noncanonical_explicit_deny_after_allow(self):
        allow = _ace(0, _sid(5, 32, 544), READ_EXECUTE)
        deny = _ace(1, _sid(5, 18), 1)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(allow, deny), PACKAGE_SID, "workspace", is_directory=False)

    def test_rejects_explicit_ace_after_inherited_ace(self):
        inherited = _ace(0, _sid(5, 32, 544), READ_EXECUTE, flags=0x10)
        explicit = _ace(0, _sid(5, 18), READ_EXECUTE)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(inherited, explicit), PACKAGE_SID, "workspace", is_directory=False)

    def test_rejects_ambiguous_dacl_ace_types_for_candidate_policy(self):
        audit = _ace(2, _sid(5, 18), 1)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(audit), PACKAGE_SID, "workspace", is_directory=False)

    def test_rejects_null_or_absent_dacl_and_invalid_scope(self):
        for kwargs in ({"dacl_present": False}, {"dacl_is_null": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(DaclCandidateBuildError):
                build_dacl_candidate(_acl(), PACKAGE_SID, "workspace", is_directory=False, **kwargs)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(), PACKAGE_SID, "workspace/../scratch", is_directory=False)

    def test_rejects_invalid_package_sid_and_malformed_source(self):
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(), "S-1-5-18", "workspace", is_directory=False)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(b"bad", PACKAGE_SID, "workspace", is_directory=False)

    def test_enforces_ace_and_acl_size_limits(self):
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(), PACKAGE_SID, "workspace", is_directory=False, max_aces=0)
        with self.assertRaises(DaclCandidateBuildError):
            build_dacl_candidate(_acl(), PACKAGE_SID, "workspace", is_directory=False, max_acl_bytes=8)

    def test_rejects_control_flags_outside_native_word(self):
        for flags in (-1, 0x10000, True):
            with self.subTest(flags=flags), self.assertRaisesRegex(
                DaclCandidateBuildError, "16-bit control field"
            ):
                build_dacl_candidate(
                    _acl(), PACKAGE_SID, "workspace", is_directory=False,
                    dacl_control_flags=flags,
                )

    def test_input_is_immutable_and_candidate_is_deterministic(self):
        source = _acl(_ace(1, _sid(5, 18), 1))
        first = build_dacl_candidate(source, PACKAGE_SID, "scratch", is_directory=True)
        second = build_dacl_candidate(source, PACKAGE_SID, "scratch", is_directory=True)
        self.assertEqual(first, second)
        self.assertEqual(source, _acl(_ace(1, _sid(5, 18), 1)))


if __name__ == "__main__":
    unittest.main()
