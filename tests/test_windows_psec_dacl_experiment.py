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
    DACL_ONLY_SECURITY_INFO,
    DACL_AND_PROTECTED_SECURITY_INFO,
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
        "set_security_info_flags": {
            "decimal": result.security_info_flags,
            "hex": hex(result.security_info_flags),
        },
        "dacl_defaulted": {
            "after_create": result.dacl_defaulted_before,
            "after_write": result.dacl_defaulted_after_write,
            "after_rollback": result.dacl_defaulted_after_rollback,
        },
        "write_verified": result.write_verified,
        "rollback_verified": result.rollback_verified,
        "rollback_attempted": result.rollback_attempted,
        "control_flags_after_each_write": result.control_flags_after_each_write,
        "native_write_calls": result.native_write_calls,
        "os_managed_control_flag_transitions": {
            "se_dacl_auto_inherited_changed_after_write": result.auto_inherited_changed_after_write,
            "se_dacl_auto_inherited_changed_after_rollback": result.auto_inherited_changed_after_rollback,
        },
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
        experiment = WindowsDaclDefaultedExperiment()
        try:
            result = experiment.run(defaulted=True)
        except DaclDefaultedNotExercised as exc:
            evidence = {
                "label": "TRUE_SETUP_NOT_EXERCISED",
                "windows_build": platform.platform(),
                "python": sys.version,
                "outcome": "NOT_EXERCISED",
                **exc.evidence,
                "cleanup_verified": experiment.last_cleanup_verified,
            }
            print("DACL_EXPERIMENT_EVIDENCE=" + json.dumps(evidence, default=str), flush=True)
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

    def _assert_write_only_flag_case(self, security_info_flags, label):
        # Each API flag combination receives a fresh disposable file.
        result = WindowsDaclDefaultedExperiment().run(
            defaulted=False, rollback=False,
            security_info_flags=security_info_flags,
        )
        _emit_evidence(label, result)
        self.assertEqual(result.filesystem.upper(), "NTFS")
        self.assertFalse(result.dacl_defaulted_before)
        self.assertEqual(result.outcome, "OBSERVED")
        self.assertEqual(result.security_info_flags, security_info_flags)
        self.assertFalse(result.rollback_attempted)
        self.assertIsNotNone(result.dacl_bytes_after_write_hex)
        self.assertFalse(result.api_errors)
        self.assertIsNone(result.dacl_defaulted_after_rollback)
        self.assertIsNone(result.dacl_bytes_after_rollback_hex)
        self.assertTrue(result.cleanup_verified)
        self.assertTrue(result.owned_handle_opened)
        self.assertTrue(result.owned_handle_closed)
        self.assertIs(result.close_handle_succeeded, True)
        self.assertIsNotNone(result.control_flags_after_write)
        self.assertEqual(
            result.control_flags_before & 0xEFFF,
            result.control_flags_after_write & 0xEFFF,
            "write-only probe changed control bits other than SE_DACL_AUTO_INHERITED",
        )
        self.assertEqual(
            result.control_flags_before & 0x1000,
            result.control_flags_after_write & 0x1000,
            "write-only probe changed SE_DACL_PROTECTED",
        )

    def test_false_creation_state_without_native_write(self):
        experiment = WindowsDaclDefaultedExperiment()
        result = experiment.run(
            defaulted=False, rollback=False, write_repetitions=0
        )
        _emit_evidence("FALSE_CREATION_ONLY", result)
        self.assertEqual(result.filesystem.upper(), "NTFS")
        self.assertFalse(result.dacl_defaulted_before)
        self.assertEqual(result.outcome, "OBSERVED")
        self.assertEqual(result.native_write_calls, 0)
        self.assertEqual(result.control_flags_after_each_write, ())
        self.assertEqual(result.control_flags_after_write, result.control_flags_before)
        self.assertEqual(result.dacl_bytes_after_write_hex, result.dacl_bytes_before_hex)
        self.assertFalse(result.api_errors)
        self.assertTrue(result.cleanup_verified)
        self.assertTrue(result.owned_handle_opened)
        self.assertTrue(result.owned_handle_closed)
        self.assertIs(result.close_handle_succeeded, True)

    def test_repeated_setsecurityinfo_control_flags_on_same_retained_handle(self):
        experiment = WindowsDaclDefaultedExperiment()
        result = experiment.run(
            defaulted=False, rollback=False, write_repetitions=3
        )
        _emit_evidence("FALSE_REPEATED_SETSECURITYINFO", result)
        self.assertEqual(result.filesystem.upper(), "NTFS")
        self.assertFalse(result.dacl_defaulted_before)
        self.assertEqual(result.outcome, "OBSERVED")
        self.assertEqual(result.native_write_calls, 3)
        self.assertTrue(all(
            (flags & 0xEFFF) == (result.control_flags_before & 0xEFFF)
            for flags in result.control_flags_after_each_write
        ), "repeated writes changed control bits other than SE_DACL_AUTO_INHERITED")
        self.assertTrue(all(
            (flags & 0x1000) == (result.control_flags_before & 0x1000)
            for flags in result.control_flags_after_each_write
        ), "repeated writes changed SE_DACL_PROTECTED")
        self.assertEqual(len(result.control_flags_after_each_write), 3)
        self.assertFalse(result.api_errors)
        self.assertTrue(result.cleanup_verified)
        self.assertTrue(result.owned_handle_opened)
        self.assertTrue(result.owned_handle_closed)
        self.assertIs(result.close_handle_succeeded, True)

    def test_write_only_dacl_security_information_only(self):
        self._assert_write_only_flag_case(
            DACL_ONLY_SECURITY_INFO, "FALSE_WRITE_ONLY_DACL_ONLY"
        )

    def test_write_only_dacl_plus_protected_security_information(self):
        self._assert_write_only_flag_case(
            DACL_AND_PROTECTED_SECURITY_INFO, "FALSE_WRITE_ONLY_DACL_PLUS_PROTECTED"
        )

    def test_ambiguous_native_write_error_still_attempts_rollback_and_cleanup(self):
        experiment = WindowsDaclDefaultedExperiment()
        original_write = experiment._write_dacl
        calls = {"count": 0}

        def fail_after_native_write(handle, snapshot, *, security_info_flags):
            # Mirror the production method's keyword-only API exactly. The
            # injected error happens only after the first native write returns.
            calls["count"] += 1
            original_write(
                handle, snapshot, security_info_flags=security_info_flags
            )
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

    @unittest.skipUnless(
        os.name == "nt"
        and os.environ.get("DCP_RUN_WINDOWS_PSEC_REAL_HOST") == "1"
        and not any(
            os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}
            for name in ("CI", "GITHUB_ACTIONS")
        ),
        "real NTFS DACL rollback experiment is local-only; explicitly set "
        "DCP_RUN_WINDOWS_PSEC_REAL_HOST=1 on a local Windows NTFS host",
    )
    def test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file(self):
        result = WindowsDaclDefaultedExperiment().run(defaulted=False)
        _emit_evidence("FALSE_ROUND_TRIP", result)
        self.assertEqual(result.filesystem.upper(), "NTFS")
        self.assertFalse(result.dacl_defaulted_before)
        self.assertEqual(result.outcome, "PASS", "FALSE DACL state failed round-trip invariants")
        self.assertTrue(result.write_verified)
        self.assertTrue(result.rollback_verified)
        self.assertTrue(result.dacl_bytes_equal_after_write)
        self.assertTrue(result.dacl_bytes_equal_after_rollback)
        self.assertEqual(result.dacl_defaulted_after_write, result.dacl_defaulted_before)
        self.assertEqual(result.dacl_defaulted_after_rollback, result.dacl_defaulted_before)
        self.assertEqual(
            result.control_flags_before & 0x1000,
            result.control_flags_after_write & 0x1000,
            "write changed SE_DACL_PROTECTED",
        )
        self.assertEqual(
            result.control_flags_before & 0x1000,
            result.control_flags_after_rollback & 0x1000,
            "rollback changed SE_DACL_PROTECTED",
        )
        self.assertEqual(
            result.control_flags_before & 0xEFFF,
            result.control_flags_after_write & 0xEFFF,
            "write changed control bits other than SE_DACL_AUTO_INHERITED",
        )
        self.assertEqual(
            result.control_flags_before & 0xEFFF,
            result.control_flags_after_rollback & 0xEFFF,
            "rollback changed control bits other than SE_DACL_AUTO_INHERITED",
        )
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
