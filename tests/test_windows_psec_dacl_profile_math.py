from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from tools.local_runner_agent.windows_psec_dacl_comparison import (
    DaclComparisonProfile,
    dacl_states_equal,
)
from tools.local_runner_agent.windows_psec_dacl_profile_math import (
    EncodedComparisonLevel,
    comparison_level_diagnostics,
    decode_comparison_level,
    encode_comparison_level,
    resolve_comparison_level,
)


EXPECTED = (
    DaclComparisonProfile.DACL_CONTENT_EQUALITY,
    DaclComparisonProfile.DACL_OBJECT_STATE_EQUALITY,
    DaclComparisonProfile.CONTROL_STATE_EQUALITY,
    DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
)


class State:
    dacl_present = True
    dacl_is_null = False
    dacl_bytes = b"\x02\x00\x08\x00\x00\x00\x00\x00"
    dacl_defaulted = False

    def __init__(self, control_flags: int):
        self.dacl_control_flags = control_flags


class DaclProfileMathAdapterTests(unittest.TestCase):
    def test_adapter_contains_exactly_the_four_existing_profiles(self):
        self.assertEqual(tuple(resolve_comparison_level(i) for i in range(4)), EXPECTED)
        self.assertEqual(len(DaclComparisonProfile), 4)

    def test_square_root_encoding_round_trips_to_original_profile(self):
        for level_id, expected_profile in enumerate(EXPECTED):
            with self.subTest(level_id=level_id):
                encoded = encode_comparison_level(level_id)
                self.assertEqual(encoded.level_id, level_id)
                self.assertEqual(decode_comparison_level(encoded), expected_profile)

    def test_normalized_values_are_diagnostic_only_and_in_unit_interval(self):
        for level_id in range(4):
            encoded = encode_comparison_level(level_id)
            self.assertGreaterEqual(encoded.normalized, Decimal(0))
            self.assertLessEqual(encoded.normalized, Decimal(1))
        self.assertEqual(encode_comparison_level(0).normalized, Decimal(0))
        self.assertEqual(encode_comparison_level(3).normalized, Decimal(1))

    def test_square_root_square_round_trip_is_within_declared_decimal_precision(self):
        for level_id in range(4):
            values = comparison_level_diagnostics(level_id)
            self.assertEqual(values["level_id"], level_id)
            self.assertLessEqual(
                abs(Decimal(values["square"]) - Decimal(level_id)),
                Decimal("1e-45"),
            )

    def test_invalid_level_types_and_boundaries_fail_closed(self):
        for value in (-1, 4, True, False, 1.0, "1", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    resolve_comparison_level(value)
                with self.assertRaises(ValueError):
                    encode_comparison_level(value)

    def test_tampered_encoded_values_are_rejected(self):
        original = encode_comparison_level(2)
        tampered_sqrt = replace(original, square_root=original.square_root + Decimal("0.01"))
        tampered_normalized = replace(original, normalized=Decimal("0.5"))
        for candidate in (tampered_sqrt, tampered_normalized):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(ValueError, "integrity validation"):
                    decode_comparison_level(candidate)

    def test_untyped_or_forged_encoding_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "typed encoded"):
            decode_comparison_level({"level_id": 2})  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            decode_comparison_level(EncodedComparisonLevel(4, Decimal(2), Decimal(2)))

    def test_math_adapter_does_not_downgrade_strict_control_transition(self):
        before = State(0x9004)
        after = State(0x9404)
        strict = resolve_comparison_level(3)
        content = resolve_comparison_level(0)
        self.assertTrue(dacl_states_equal(before, after, content))
        self.assertFalse(dacl_states_equal(before, after, strict))
        self.assertIs(decode_comparison_level(encode_comparison_level(3)), strict)


if __name__ == "__main__":
    unittest.main()
