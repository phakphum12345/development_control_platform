from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace

from tools.local_runner_agent.windows_psec_dacl_comparison import DaclComparisonProfile
from tools.local_runner_agent.windows_psec_security_descriptor_transaction import DescriptorSnapshot
from tools.local_runner_agent.windows_psec_reversible_state import (
    OriginalDescriptorSnapshot,
    ReversibleStateError,
    TargetObjectIdentity,
    capture_original_snapshot,
    verify_restoration_readback,
)


TRANSACTION_ID = "8b77a3f2-1d1a-4e4a-9c42-3b7e6c1f8a20"
IDENTITY = TargetObjectIdentity(9823700658284110452, "8cb7040000006f000000000000000000")
S0 = DescriptorSnapshot(
    dacl_present=True,
    dacl_is_null=False,
    dacl_bytes=bytes.fromhex("0200080000000000"),
    dacl_control_flags=0x9004,
    descriptor_revision=1,
    acl_revision=2,
    ace_count=0,
    dacl_defaulted=False,
)


class ReversibleStatePreservationTests(unittest.TestCase):
    def setUp(self):
        self.original = capture_original_snapshot(TRANSACTION_ID, IDENTITY, S0)

    def verify(self, readback=S0, **overrides):
        arguments = {
            "transaction_id": TRANSACTION_ID,
            "target_identity": IDENTITY,
            "readback": readback,
            "comparison_profile": DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
        }
        arguments.update(overrides)
        return verify_restoration_readback(self.original, **arguments)

    def test_capture_binds_s0_to_transaction_and_target_with_digest(self):
        self.assertIsInstance(self.original, OriginalDescriptorSnapshot)
        self.assertTrue(self.original.verify_integrity())
        self.assertEqual(self.original.descriptor, S0)
        self.assertEqual(self.original.target_identity, IDENTITY)

    def test_snapshot_records_are_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.original.transaction_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            self.original.descriptor.dacl_control_flags = 0x9404

    def test_target_identity_hex_case_is_normalized(self):
        upper_identity = TargetObjectIdentity(IDENTITY.volume_serial, IDENTITY.file_id.upper())
        result = self.verify(target_identity=upper_identity)
        self.assertEqual(result.state, "RESTORED_EXACT")

    def test_invalid_original_envelope_fails_closed(self):
        result = verify_restoration_readback(
            None,
            transaction_id=TRANSACTION_ID,
            target_identity=IDENTITY,
            readback=S0,
            comparison_profile=DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
        )
        self.assertEqual(result.state, "SNAPSHOT_INVALID")
        self.assertEqual(result.mismatches, ("original_snapshot_type_invalid",))

    def test_exact_readback_is_verified_against_s0(self):
        result = self.verify()
        self.assertEqual(result.state, "RESTORED_EXACT")
        self.assertEqual(result.profile, "STRICT_DESCRIPTOR_EQUALITY")
        self.assertEqual(result.mismatches, ())

    def test_control_word_transition_is_not_exact_under_strict_profile(self):
        changed = replace(S0, dacl_control_flags=0x9404)
        result = self.verify(readback=changed)
        self.assertEqual(result.state, "RESTORE_NOT_EXACT")
        self.assertEqual(result.mismatches, ("control_flags_mismatch",))

    def test_content_profile_does_not_silently_change_strict_profile_semantics(self):
        changed = replace(S0, dacl_control_flags=0x9404)
        result = self.verify(
            readback=changed,
            comparison_profile=DaclComparisonProfile.DACL_CONTENT_EQUALITY,
        )
        self.assertEqual(result.state, "RESTORED_EXACT")
        self.assertEqual(result.profile, "DACL_CONTENT_EQUALITY")

    def test_wrong_transaction_or_target_identity_fails_closed(self):
        wrong_transaction = self.verify(transaction_id="9b77a3f2-1d1a-4e4a-9c42-3b7e6c1f8a20")
        wrong_identity = self.verify(
            target_identity=TargetObjectIdentity(IDENTITY.volume_serial, "0" * 32)
        )
        self.assertEqual(wrong_transaction.state, "RESTORE_NOT_EXACT")
        self.assertEqual(wrong_transaction.mismatches, ("transaction_id_mismatch",))
        self.assertEqual(wrong_identity.state, "RESTORE_NOT_EXACT")
        self.assertEqual(wrong_identity.mismatches, ("target_identity_mismatch",))

    def test_tampered_original_snapshot_is_rejected(self):
        tampered = replace(self.original, descriptor=replace(S0, dacl_control_flags=0x9404))
        result = verify_restoration_readback(
            tampered,
            transaction_id=TRANSACTION_ID,
            target_identity=IDENTITY,
            readback=S0,
            comparison_profile=DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
        )
        self.assertFalse(tampered.verify_integrity())
        self.assertEqual(result.state, "SNAPSHOT_INVALID")
        self.assertEqual(result.mismatches, ("original_snapshot_integrity_invalid",))

    def test_missing_or_unknown_profile_never_passes(self):
        for profile in (None, "STRICT", ""):
            with self.subTest(profile=profile):
                result = self.verify(comparison_profile=profile)
                self.assertEqual(result.state, "RESTORE_NOT_EXACT")
                self.assertIsNone(result.profile)

    def test_invalid_snapshot_capture_is_rejected(self):
        with self.assertRaises(ReversibleStateError):
            capture_original_snapshot("not-a-uuid", IDENTITY, S0)
        with self.assertRaises(ReversibleStateError):
            capture_original_snapshot(
                TRANSACTION_ID, IDENTITY, replace(S0, dacl_control_flags=0x10000)
            )


if __name__ == "__main__":
    unittest.main()
