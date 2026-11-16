from __future__ import annotations

import json
import os
import unittest
from dataclasses import asdict
from unittest import skipUnless

from tools.local_runner_agent.windows_psec_dacl_restore_api_experiment import (
    RESTORE_API_CANDIDATES,
    DaclRestoreApiExperimentError,
    WindowsDaclRestoreApiExperiment,
)


class WindowsDaclRestoreApiContractTests(unittest.TestCase):
    def test_candidate_allowlist_is_fixed_and_explicit(self):
        self.assertEqual(
            RESTORE_API_CANDIDATES,
            (
                "setsecurityinfo_unprotected",
                "setnamedsecurityinfo_unprotected",
                "setfilesecurity_original_control",
                "setfilesecurity_auto_inherit_req",
            ),
        )

    @unittest.skipUnless(os.name != "nt", "off-Windows constructor contract")
    def test_constructor_fails_closed_off_windows(self):
        with self.assertRaises(DaclRestoreApiExperimentError):
            WindowsDaclRestoreApiExperiment()


@skipUnless(os.name == "nt", "requires a disposable Windows NTFS host")
class WindowsDaclRestoreApiRealHostTests(unittest.TestCase):
    def test_documented_restore_api_candidates_emit_independent_s2_evidence(self):
        results = WindowsDaclRestoreApiExperiment().run_all()
        self.assertEqual(
            tuple(result.candidate for result in results), RESTORE_API_CANDIDATES
        )
        expected = {
            "setsecurityinfo_unprotected": ("RESTORE_NOT_EXACT", 0, 0x8404, 3, False),
            "setnamedsecurityinfo_unprotected": ("RESTORE_NOT_EXACT", 0, 0x8404, 3, False),
            "setfilesecurity_original_control": ("RESTORED_EXACT", 1, 0x9004, 0, True),
            "setfilesecurity_auto_inherit_req": ("RESTORED_EXACT", 1, 0x9004, 0, True),
        }
        transaction_ids = set()
        file_ids = set()
        for result in results:
            print(
                "DACL_RESTORE_API_EVIDENCE="
                + json.dumps(asdict(result), sort_keys=True),
                flush=True,
            )
            with self.subTest(candidate=result.candidate):
                expected_state, expected_code, expected_s2, inherited_s2, bytes_equal = expected[result.candidate]
                self.assertTrue(result.cleanup_verified)
                self.assertEqual(len(result.snapshot_integrity_sha256), 64)
                self.assertTrue(result.transaction_id)
                self.assertNotIn(result.transaction_id, transaction_ids)
                transaction_ids.add(result.transaction_id)
                self.assertNotIn(result.file_id, file_ids)
                file_ids.add(result.file_id)
                self.assertEqual(result.api_return_code, expected_code)
                self.assertIsNone(result.api_error)
                self.assertIsNone(result.readback_error)
                self.assertEqual(result.control_flags_s0, 0x9004)
                self.assertEqual(result.control_flags_s1, 0x9404)
                self.assertEqual(result.control_flags_s2, expected_s2)
                self.assertEqual(result.inherited_ace_count_s0, 0)
                self.assertEqual(result.inherited_ace_count_s2, inherited_s2)
                self.assertEqual(
                    result.dacl_bytes_s0_hex == result.dacl_bytes_s2_hex,
                    bytes_equal,
                )
                self.assertEqual(result.verification_state, expected_state)


if __name__ == "__main__":
    unittest.main()
