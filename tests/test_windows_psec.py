from __future__ import annotations

import ctypes
import unittest

from tools.local_runner_agent.windows_psec import (
    PSE_SUPPORT_FS_DENY,
    PSE_SUPPORT_FS_ENUMERATE,
    PSE_SUPPORT_NETWORK_INGRESS,
    probe_psec,
)


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class FakePsecDll:
    def __init__(self, *, flags, minor=1, version_available=1, query_hr=0, version_hr=0, missing=()):
        self.CreateProcessSecurityEnvironment = FakeFunction(lambda *args: 0)
        self.QueryProcessSecurityEnvironmentSupport = FakeFunction(
            lambda output: self._set(output, flags, query_hr)
        )
        self.IsProcessSecurityEnvironmentVersionSupported = FakeFunction(
            lambda major, available, out_minor: self._version(
                major, available, out_minor, minor, version_available, version_hr
            )
        )
        self.CloseProcessSecurityEnvironment = FakeFunction(lambda *args: None)
        for name in missing:
            delattr(self, name)

    @staticmethod
    def _set(output, flags, hr):
        ctypes.cast(output, ctypes.POINTER(ctypes.c_uint64))[0] = flags
        return hr

    @staticmethod
    def _version(major, available, out_minor, minor, supported, hr):
        ctypes.cast(available, ctypes.POINTER(ctypes.c_uint8))[0] = supported
        ctypes.cast(out_minor, ctypes.POINTER(ctypes.c_uint32))[0] = minor
        return hr


class WindowsPsecProbeTests(unittest.TestCase):
    def test_non_windows_is_blocked_without_loading_dll(self):
        def should_not_load():
            raise AssertionError("DLL loader must not run off Windows")

        result = probe_psec(platform_name="posix", dll_loader=should_not_load)
        self.assertEqual(result.state, "BLOCKED")
        self.assertFalse(result.available)

    def test_missing_required_export_is_blocked(self):
        fake = FakePsecDll(
            flags=PSE_SUPPORT_FS_DENY | PSE_SUPPORT_FS_ENUMERATE | PSE_SUPPORT_NETWORK_INGRESS,
            missing=("CreateProcessSecurityEnvironment",),
        )
        result = probe_psec(platform_name="nt", dll_loader=lambda: fake)
        self.assertEqual(result.state, "BLOCKED")
        self.assertIn("CreateProcessSecurityEnvironment", result.reason)

    def test_missing_v11_feature_is_blocked(self):
        fake = FakePsecDll(flags=PSE_SUPPORT_FS_DENY | PSE_SUPPORT_FS_ENUMERATE)
        result = probe_psec(platform_name="nt", dll_loader=lambda: fake)
        self.assertEqual(result.state, "BLOCKED")
        self.assertIn("network_ingress_policy", result.missing_features)

    def test_unsupported_version_is_blocked(self):
        fake = FakePsecDll(
            flags=PSE_SUPPORT_FS_DENY | PSE_SUPPORT_FS_ENUMERATE | PSE_SUPPORT_NETWORK_INGRESS,
            minor=0,
        )
        result = probe_psec(platform_name="nt", dll_loader=lambda: fake)
        self.assertEqual(result.state, "BLOCKED")
        self.assertEqual(result.version_major, 1)
        self.assertEqual(result.version_minor, 0)

    def test_supported_v11_surface_is_ready_for_acceptance_not_verified(self):
        fake = FakePsecDll(
            flags=PSE_SUPPORT_FS_DENY | PSE_SUPPORT_FS_ENUMERATE | PSE_SUPPORT_NETWORK_INGRESS,
            minor=1,
        )
        result = probe_psec(platform_name="nt", dll_loader=lambda: fake)
        self.assertEqual(result.state, "READY_FOR_ACCEPTANCE")
        self.assertTrue(result.available)
        self.assertFalse(result.missing_features)
        self.assertNotEqual(result.state, "VERIFIED")


if __name__ == "__main__":
    unittest.main()
