from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tools.local_runner_agent.windows_psec_dacl_experiment import (
    DaclExperimentError,
    WindowsDaclDefaultedExperiment,
)


class WindowsDaclExperimentContractTests(unittest.TestCase):
    def test_constructor_fails_closed_off_windows(self):
        with patch("tools.local_runner_agent.windows_psec_dacl_experiment.os.name", "posix"):
            with self.assertRaisesRegex(DaclExperimentError, "Windows-only"):
                WindowsDaclDefaultedExperiment()


@unittest.skipUnless(os.name == "nt", "native DACL defaulted experiment requires Windows + NTFS")
class WindowsDaclDefaultedRealHostTests(unittest.TestCase):
    def test_explicit_defaulted_true_round_trip_on_disposable_ntfs_file(self):
        result = WindowsDaclDefaultedExperiment().run(defaulted=True)
        self.assertEqual(result.filesystem.upper(), "NTFS")
        self.assertTrue(result.dacl_defaulted_before)
        self.assertTrue(result.dacl_bytes_equal_after_rollback)
        self.assertTrue(result.cleanup_verified)
        # This is the measurement under test, not a pre-assumed success.
        self.assertIn(result.dacl_defaulted_after_write, (True, False))

    def test_explicit_defaulted_false_round_trip_on_disposable_ntfs_file(self):
        result = WindowsDaclDefaultedExperiment().run(defaulted=False)
        self.assertEqual(result.filesystem.upper(), "NTFS")
        self.assertFalse(result.dacl_defaulted_before)
        self.assertTrue(result.dacl_bytes_equal_after_rollback)
        self.assertTrue(result.cleanup_verified)
        self.assertIn(result.dacl_defaulted_after_write, (True, False))


if __name__ == "__main__":
    unittest.main()
