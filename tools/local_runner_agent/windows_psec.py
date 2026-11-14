"""Fail-closed capability probe for the Windows Process Security Environment API.

This module does not launch a process and never falls back to direct execution.
READY_FOR_ACCEPTANCE means the OS exports the required PSEC v1.1 surface; it is
not a VERIFIED isolation result.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800
PSEC_REQUIRED_VERSION_MAJOR = 1
PSEC_REQUIRED_VERSION_MINOR = 1

PSE_SUPPORT_FS_DENY = 0x0000000000000001
PSE_SUPPORT_FS_ENUMERATE = 0x0000000000000004
PSE_SUPPORT_NETWORK_INGRESS = 0x0000000000000008

_REQUIRED_EXPORTS = (
    "CreateProcessSecurityEnvironment",
    "QueryProcessSecurityEnvironmentSupport",
    "IsProcessSecurityEnvironmentVersionSupported",
    "CloseProcessSecurityEnvironment",
)
_REQUIRED_FEATURES = {
    "filesystem_deny": PSE_SUPPORT_FS_DENY,
    "filesystem_enumerate": PSE_SUPPORT_FS_ENUMERATE,
    "network_ingress_policy": PSE_SUPPORT_NETWORK_INGRESS,
}


@dataclass(frozen=True)
class PsecAssessment:
    backend: str
    state: str
    available: bool
    version_major: int | None
    version_minor: int | None
    support_flags: str | None
    supported_features: tuple[str, ...]
    missing_features: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _blocked(
    reason: str,
    *,
    flags: int | None = None,
    version_major: int | None = None,
    version_minor: int | None = None,
) -> PsecAssessment:
    return PsecAssessment(
        backend="windows-process-security-environment",
        state="BLOCKED",
        available=False,
        version_major=version_major,
        version_minor=version_minor,
        support_flags=f"0x{flags:016x}" if flags is not None else None,
        supported_features=(),
        missing_features=tuple(_REQUIRED_FEATURES),
        reason=reason,
    )


def _load_processmodel():
    # Restrict DLL resolution to the Windows system directory; never search the
    # current directory or user-controlled PATH for a security API DLL.
    return ctypes.WinDLL(
        "processmodel.dll",
        use_last_error=True,
        winmode=LOAD_LIBRARY_SEARCH_SYSTEM32,
    )


def probe_psec(*, platform_name: str | None = None, dll_loader=None) -> PsecAssessment:
    """Probe PSEC v1.1 exports and required feature flags without launching code."""
    current_platform = os.name if platform_name is None else platform_name
    if current_platform != "nt":
        return _blocked("Windows host required")

    loader = _load_processmodel if dll_loader is None else dll_loader
    try:
        dll = loader()
    except (OSError, AttributeError):
        return _blocked("processmodel.dll is unavailable from the System32 search path")

    exports = {}
    for name in _REQUIRED_EXPORTS:
        try:
            exports[name] = getattr(dll, name)
        except AttributeError:
            return _blocked(f"required PSEC export is missing: {name}")

    query = exports["QueryProcessSecurityEnvironmentSupport"]
    query.argtypes = [ctypes.POINTER(ctypes.c_uint64)]
    query.restype = ctypes.c_long
    flags = ctypes.c_uint64(0)
    try:
        hr = int(query(ctypes.byref(flags)))
    except Exception:
        return _blocked("QueryProcessSecurityEnvironmentSupport call failed")
    if hr < 0:
        return _blocked(
            f"QueryProcessSecurityEnvironmentSupport returned HRESULT 0x{hr & 0xffffffff:08x}"
        )

    version = exports["IsProcessSecurityEnvironmentVersionSupported"]
    version.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    version.restype = ctypes.c_long
    available = ctypes.c_uint8(0)
    minor = ctypes.c_uint32(0)
    try:
        hr = int(version(
            PSEC_REQUIRED_VERSION_MAJOR,
            ctypes.byref(available),
            ctypes.byref(minor),
        ))
    except Exception:
        return _blocked(
            "IsProcessSecurityEnvironmentVersionSupported call failed",
            flags=flags.value,
            version_major=PSEC_REQUIRED_VERSION_MAJOR,
        )
    if hr < 0 or not available.value or minor.value < PSEC_REQUIRED_VERSION_MINOR:
        return _blocked(
            "PSEC v1.1 is not supported",
            flags=flags.value,
            version_major=PSEC_REQUIRED_VERSION_MAJOR,
            version_minor=int(minor.value),
        )

    supported = tuple(
        name for name, bit in _REQUIRED_FEATURES.items() if flags.value & bit
    )
    missing = tuple(
        name for name, bit in _REQUIRED_FEATURES.items() if not flags.value & bit
    )
    if missing:
        return PsecAssessment(
            backend="windows-process-security-environment",
            state="BLOCKED",
            available=False,
            version_major=PSEC_REQUIRED_VERSION_MAJOR,
            version_minor=int(minor.value),
            support_flags=f"0x{flags.value:016x}",
            supported_features=supported,
            missing_features=missing,
            reason="required PSEC v1.1 enforcement features are unavailable",
        )

    return PsecAssessment(
        backend="windows-process-security-environment",
        state="READY_FOR_ACCEPTANCE",
        available=True,
        version_major=PSEC_REQUIRED_VERSION_MAJOR,
        version_minor=int(minor.value),
        support_flags=f"0x{flags.value:016x}",
        supported_features=supported,
        missing_features=(),
        reason="PSEC v1.1 API surface is present; process-level acceptance is still required",
    )


def main() -> int:
    assessment = probe_psec()
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "windows_version": platform.win32_ver() if os.name == "nt" else None,
        "windows_build": sys.getwindowsversion().build if os.name == "nt" else None,
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        **assessment.to_dict(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if assessment.state == "READY_FOR_ACCEPTANCE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
