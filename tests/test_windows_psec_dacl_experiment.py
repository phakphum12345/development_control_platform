from __future__ import annotations

import json
import os
import platform
import sys
import unittest
from unittest.mock import patch

from tools.local_runner_agent.windows_psec_dacl_experiment import (
    DaclDefaultedNotExercised,
    DaclExperimentError,
    WindowsDaclDefaultedExperiment,
)


def _emit_evidence(label, result):
    """Print diagnostics before assertions so failed acceptance remains inspectable."""
    evidence = {
        "label": label,
        "windows_build": platform.platform(),
        "python": sys.version,
        "filesystem": result.filesystem,
        "volume_serial": result.volume_serial,
        "file_id": result.file_id,
        "outcome": result.outcome,
        "dacl_defaulted": {
            "after_create": result.dacl_defaulted_before,
            "after_write": result.dacl_defaulted_after_write,
            "after_rollback": result.dacl_defaulted_after_rollback,
        },
        "write_verified": result.write_verified,
        "rollback_verified": result.rollback_verified,
        "control_flags": {
            "after_create": result.control_flags_before,
            "after_write": result.control_flags_after_write,
            "after_rollback": result.control_flags_after_rollback,
        },
        "dacl_bytes_hex": {
            "after_create": result.dacl_bytes_before_hex,
            "after_write": result.dacl_bytes_after_write_hex,
            "after_rollback": result.dacl_bytes_after_rollback_hex,
        },
        "api_errors": result.api_errors,
        "cleanup_verified": result.cleanup_verified,
        "harness_handle": {
            "opened": result.owned_handle_opened,
            "closed": result.owned_handle_closed,
            "close_succeeded": result.close_handle_succeeded,
        },
        "inherited_ace_count": {
            "after_create": result.inherited_ace_count_before,
            "after_write": result.inherited_ace_count_after_write,
            "after_rollback": result.inherited_ace_count_after_rollback,
        },
        # Process-wide count is diagnostic only; it is not a harness-owned
        # resource inventory and must never be used as a leak assertion.
        "process_handle_count": {
            "before": result.process_handles_before,
            "after": result.process_handles_after,
            "delta": result.process_handle_delta,
        },
    }
    print("DACL_EXPERIMENT_EVIDENCE=" + json.dumps(evidence, default=str), flush=True)


class WindowsDaclExperimentContractTests(unittest.TestCase):
    def test_constructor_fails_closed_off_windows(self):
        with patch("tools.local_runner_agent.windows_psec_dacl_experiment.os.name", "posix"):
            with self.assertRaisesRegex(DaclExperimentError, "Windows-only"):
                WindowsDaclDefaultedExperiment()


@unittest.skipUnless(os.name == "nt", "native DACL defaulted experiment requires Windows + NTFS")
class WindowsDaclDefaultedRealHostTests(unittest.TestCase):
    def test_explicit_defaulted_true_round_trip_on_disposable_ntfs_file(self):
        try:
            result = WindowsDaclDefaultedExperiment().run(defaulted=True)
        except DaclDefaultedNotExercised as exc:
            self.skipTest(str(exc))
        _emit_evidence("TRUE_ROUND_TRIP", result)
        self.assertEqual(result.filesystem.upper(), "NTFS")
        self.assertTrue(result.dacl_defaulted_before)
        self.assertEqual(result.outcome, "PASS", "TRUE DACL defaulted state did not round-trip exactly")
        self.assertTrue(result.cleanup_verified)
        self.assertTrue(result.owned_handle_opened)
        self.assertTrue(result.owned_handle_closed)
        self.assertIs(result.close_handle_succeeded, True)
        self.assertGreater(result.volume_serial, 0)
        self.assertEqual(len(result.file_id), 32)
        self.assertIsInstance(result.dacl_defaulted_after_write, bool)

    def test_ambiguous_native_write_error_still_attempts_rollback_and_cleanup(self):
        experiment = WindowsDaclDefaultedExperiment()
        original_write = experiment._write_dacl
        calls = {"count": 0}

        def fail_after_native_write(handle, snapshot):
            calls["count"] += 1
            original_write(handle, snapshot)
            if calls["count"] == 1:
                raise OSError("injected error after native SetSecurityInfo")

        with patch.object(experiment, "_write_dacl", side_effect=fail_after_native_write):
            result = experiment.run(defaulted=False)
        _emit_evidence("AMBIGUOUS_WRITE_ERROR", result)
        self.assertEqual(calls["count"], 2, "rollback must run after an ambiguous write error")
        self.assertIn("injected error after native SetSecurityInfo", result.api_errors)
        self.assertEqual(result.outcome, "FAIL")
        self.assertTrue(experiment.last_cleanup_verified)
        self.assertTrue(result.cleanup_verified)
        self.assertTrue(result.owned_handle_opened)
        self.assertTrue(result.owned_handle_closed)
        self.assertIs(result.close_handle_succeeded, True)

    def test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file(self):
        result = WindowsDaclDefaultedExperiment().run(defaulted=False)
        _emit_evidence("FALSE_ROUND_TRIP", result)
        self.assertEqual(result.filesystem.upper(), "NTFS")
        self.assertFalse(result.dacl_defaulted_before)
        self.assertEqual(result.outcome, "PASS", "FALSE DACL state failed exact round-trip")
        self.assertEqual(result.dacl_defaulted_after_rollback, False)
        self.assertTrue(result.cleanup_verified)
        self.assertTrue(result.owned_handle_opened)
        self.assertTrue(result.owned_handle_closed)
        self.assertIs(result.close_handle_succeeded, True)
        self.assertGreater(result.volume_serial, 0)
        self.assertEqual(len(result.file_id), 32)
        self.assertIn(result.dacl_defaulted_after_write, (True, False))


if __name__ == "__main__":
    unittest.main()
