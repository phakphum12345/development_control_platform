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
        for result in results:
            print(
                "DACL_RESTORE_API_EVIDENCE="
                + json.dumps(asdict(result), sort_keys=True),
                flush=True,
            )
            with self.subTest(candidate=result.candidate):
                self.assertTrue(result.cleanup_verified)
                self.assertEqual(len(result.snapshot_integrity_sha256), 64)
                self.assertTrue(result.transaction_id)
                self.assertIsNotNone(result.api_return_code)
                self.assertIsNotNone(result.control_flags_s0)
                self.assertIsNotNone(result.control_flags_s1)
                self.assertIsNotNone(result.control_flags_s2)
                self.assertIsNone(result.readback_error)
                self.assertIn(
                    result.verification_state,
                    ("RESTORED_EXACT", "RESTORE_NOT_EXACT"),
                )


if __name__ == "__main__":
    unittest.main()
