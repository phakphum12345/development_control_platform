from __future__ import annotations

import unittest
from dataclasses import dataclass, replace

from tools.local_runner_agent.windows_psec_dacl_comparison import (
    DaclComparisonProfile,
    dacl_states_equal,
    resolve_dacl_comparison_profile,
)


@dataclass(frozen=True)
class State:
    dacl_present: bool = True
    dacl_is_null: bool = False
    dacl_bytes: bytes = b"\x02\x00\x08\x00\x00\x00\x00\x00"
    dacl_defaulted: bool = False
    dacl_control_flags: int = 0x9004


BASE = State()


class DaclComparisonProfileTests(unittest.TestCase):
    def test_identical_state_matches_all_four_profiles(self):
        for profile in DaclComparisonProfile:
            with self.subTest(profile=profile):
                self.assertTrue(dacl_states_equal(BASE, BASE, profile))

    def test_control_word_delta_is_visible_only_to_control_and_strict_profiles(self):
        changed = replace(BASE, dacl_control_flags=0x9404)
        self.assertTrue(dacl_states_equal(BASE, changed, DaclComparisonProfile.DACL_CONTENT_EQUALITY))
        self.assertTrue(dacl_states_equal(BASE, changed, DaclComparisonProfile.DACL_OBJECT_STATE_EQUALITY))
        self.assertFalse(dacl_states_equal(BASE, changed, DaclComparisonProfile.CONTROL_STATE_EQUALITY))
        self.assertFalse(dacl_states_equal(BASE, changed, DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY))

    def test_defaulted_metadata_delta_is_visible_to_object_and_strict_profiles(self):
        changed = replace(BASE, dacl_defaulted=True)
        self.assertTrue(dacl_states_equal(BASE, changed, DaclComparisonProfile.DACL_CONTENT_EQUALITY))
        self.assertTrue(dacl_states_equal(BASE, changed, DaclComparisonProfile.CONTROL_STATE_EQUALITY))
        self.assertFalse(dacl_states_equal(BASE, changed, DaclComparisonProfile.DACL_OBJECT_STATE_EQUALITY))
        self.assertFalse(dacl_states_equal(BASE, changed, DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY))

    def test_acl_content_delta_fails_every_profile_that_includes_content(self):
        changed = replace(BASE, dacl_bytes=b"\x02\x00\x08\x00\x01\x00\x00\x00")
        self.assertFalse(dacl_states_equal(BASE, changed, DaclComparisonProfile.DACL_CONTENT_EQUALITY))
        self.assertFalse(dacl_states_equal(BASE, changed, DaclComparisonProfile.DACL_OBJECT_STATE_EQUALITY))
        self.assertTrue(dacl_states_equal(BASE, changed, DaclComparisonProfile.CONTROL_STATE_EQUALITY))
        self.assertFalse(dacl_states_equal(BASE, changed, DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY))

    def test_null_dacl_and_empty_non_null_dacl_are_not_content_equal(self):
        null_dacl = replace(BASE, dacl_is_null=True, dacl_bytes=b"")
        self.assertFalse(dacl_states_equal(BASE, null_dacl, DaclComparisonProfile.DACL_CONTENT_EQUALITY))
        self.assertFalse(dacl_states_equal(BASE, null_dacl, DaclComparisonProfile.DACL_OBJECT_STATE_EQUALITY))
        self.assertFalse(dacl_states_equal(BASE, null_dacl, DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY))
        self.assertTrue(dacl_states_equal(BASE, null_dacl, DaclComparisonProfile.CONTROL_STATE_EQUALITY))

    def test_profile_string_must_match_exact_protocol_name(self):
        self.assertIs(
            resolve_dacl_comparison_profile("STRICT_DESCRIPTOR_EQUALITY"),
            DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
        )
        with self.assertRaisesRegex(ValueError, "unknown DACL comparison profile"):
            resolve_dacl_comparison_profile("CONTENT_EQUALITY")
        with self.assertRaisesRegex(ValueError, "explicit DACL comparison profile is required"):
            resolve_dacl_comparison_profile(None)

    def test_no_profile_is_implicitly_promoted_or_downgraded(self):
        changed = replace(BASE, dacl_control_flags=0x9404)
        self.assertFalse(dacl_states_equal(BASE, changed, DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY))
        self.assertTrue(dacl_states_equal(BASE, changed, DaclComparisonProfile.DACL_CONTENT_EQUALITY))


if __name__ == "__main__":
    unittest.main()
