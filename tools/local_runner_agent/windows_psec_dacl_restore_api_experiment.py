"""Disposable NTFS experiment for alternative DACL restoration APIs.

The experiment creates a fresh harness-owned NTFS file per candidate, captures
immutable S0 from a retained handle, mutates it through SetSecurityInfo to
produce S1, then probes one documented restore API and verifies S2 against S0.

SetFileSecurityW is included only as an obsolete compatibility probe. No
candidate is promoted to a production writer by this module.
"""
from __future__ import annotations

import ctypes
import os
import tempfile
import uuid
from dataclasses import dataclass
from ctypes import wintypes

from tools.local_runner_agent.windows_psec_dacl_comparison import DaclComparisonProfile
from tools.local_runner_agent.windows_psec_reversible_state import (
    TargetObjectIdentity,
    capture_original_snapshot_from_handle,
    verify_restoration_readback,
)
from tools.local_runner_agent.windows_psec_dacl_experiment import (
    DACL_AND_PROTECTED_SECURITY_INFO,
    DACL_ONLY_SECURITY_INFO,
    DACL_SECURITY_INFORMATION,
    SE_FILE_OBJECT,
    SECURITY_DESCRIPTOR_REVISION,
    WindowsDaclDefaultedExperiment,
)


UNPROTECTED_DACL_SECURITY_INFORMATION = 0x20000000
SE_DACL_PROTECTED = 0x1000
SE_DACL_AUTO_INHERITED = 0x0400
SE_DACL_AUTO_INHERIT_REQ = 0x0100

RESTORE_API_CANDIDATES = (
    "setsecurityinfo_unprotected",
    "setnamedsecurityinfo_unprotected",
    "setfilesecurity_original_control",
    "setfilesecurity_auto_inherit_req",
)


class DaclRestoreApiExperimentError(RuntimeError):
    """A disposable restore-API experiment could not produce safe evidence."""


@dataclass(frozen=True)
class RestoreApiCandidateResult:
    candidate: str
    filesystem: str
    transaction_id: str
    snapshot_integrity_sha256: str
    volume_serial: int
    file_id: str
    control_flags_s0: int
    control_flags_s1: int | None
    control_flags_s2: int | None
    dacl_bytes_s0_hex: str
    dacl_bytes_s1_hex: str | None
    dacl_bytes_s2_hex: str | None
    inherited_ace_count_s0: int
    inherited_ace_count_s1: int | None
    inherited_ace_count_s2: int | None
    api_return_code: int | None
    api_error: str | None
    readback_error: str | None
    verification_state: str | None
    mismatches: tuple[str, ...]
    cleanup_verified: bool


class WindowsDaclRestoreApiExperiment(WindowsDaclDefaultedExperiment):
    """Run one documented restore candidate per new disposable NTFS file."""

    def __init__(self, *, reader=None):
        if os.name != "nt":
            raise DaclRestoreApiExperimentError(
                "restore API experiment is Windows-only"
            )
        super().__init__(reader=reader)
        self._advapi32.SetFileSecurityW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID
        ]
        self._advapi32.SetFileSecurityW.restype = wintypes.BOOL
        self._advapi32.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
        ]
        self._advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD
        self._advapi32.MakeSelfRelativeSD.argtypes = [
            wintypes.LPVOID, wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD)
        ]
        self._advapi32.MakeSelfRelativeSD.restype = wintypes.BOOL

    @staticmethod
    def candidate_names() -> tuple[str, ...]:
        return RESTORE_API_CANDIDATES

    def _build_absolute_dacl_descriptor(self, snapshot, *, auto_inherit_req: bool):
        if not snapshot.dacl_present or snapshot.dacl_is_null or not snapshot.dacl_bytes:
            raise DaclRestoreApiExperimentError(
                "restore candidate requires an explicit non-NULL DACL"
            )
        descriptor = ctypes.create_string_buffer(64)
        acl_buffer = ctypes.create_string_buffer(
            snapshot.dacl_bytes, len(snapshot.dacl_bytes)
        )
        if not self._advapi32.InitializeSecurityDescriptor(
            descriptor, SECURITY_DESCRIPTOR_REVISION
        ):
            raise self._last_error("InitializeSecurityDescriptor(restore candidate)")
        if not self._advapi32.SetSecurityDescriptorDacl(
            descriptor,
            True,
            ctypes.cast(acl_buffer, wintypes.LPVOID),
            bool(snapshot.dacl_defaulted),
        ):
            raise self._last_error("SetSecurityDescriptorDacl(restore candidate)")
        control_interest = (
            SE_DACL_PROTECTED | SE_DACL_AUTO_INHERITED | SE_DACL_AUTO_INHERIT_REQ
        )
        control_bits = snapshot.dacl_control_flags & control_interest
        if auto_inherit_req:
            control_bits |= SE_DACL_AUTO_INHERIT_REQ
        if not self._advapi32.SetSecurityDescriptorControl(
            descriptor,
            control_interest,
            control_bits,
        ):
            raise self._last_error("SetSecurityDescriptorControl(restore candidate)")
        required = wintypes.DWORD()
        self._advapi32.MakeSelfRelativeSD(
            descriptor, None, ctypes.byref(required)
        )
        if required.value <= 0:
            raise self._last_error("MakeSelfRelativeSD(size query)")
        self_relative = ctypes.create_string_buffer(required.value)
        if not self._advapi32.MakeSelfRelativeSD(
            descriptor, self_relative, ctypes.byref(required)
        ):
            raise self._last_error("MakeSelfRelativeSD(restore candidate)")
        return self_relative, acl_buffer

    def _apply_restore_candidate(self, candidate, *, file_path, handle, snapshot):
        acl_buffer = ctypes.create_string_buffer(
            snapshot.dacl_bytes, len(snapshot.dacl_bytes)
        )
        if candidate == "setsecurityinfo_unprotected":
            code = self._advapi32.SetSecurityInfo(
                wintypes.HANDLE(handle),
                SE_FILE_OBJECT,
                DACL_ONLY_SECURITY_INFO | UNPROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                ctypes.cast(acl_buffer, wintypes.LPVOID),
                None,
            )
            return int(code), (None if code == 0 else f"SetSecurityInfo returned {int(code)}")

        if candidate == "setnamedsecurityinfo_unprotected":
            path_buffer = ctypes.create_unicode_buffer(file_path)
            code = self._advapi32.SetNamedSecurityInfoW(
                path_buffer,
                SE_FILE_OBJECT,
                DACL_ONLY_SECURITY_INFO | UNPROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                ctypes.cast(acl_buffer, wintypes.LPVOID),
                None,
            )
            return int(code), (None if code == 0 else f"SetNamedSecurityInfoW returned {int(code)}")

        if candidate == "setfilesecurity_original_control":
            descriptor, keepalive_acl = self._build_absolute_dacl_descriptor(
                snapshot, auto_inherit_req=False
            )
            success = self._advapi32.SetFileSecurityW(
                file_path, DACL_SECURITY_INFORMATION, descriptor
            )
            if not success:
                return 0, str(self._last_error("SetFileSecurityW(original control)"))
            # Keep both native buffers alive until the call has returned.
            _ = keepalive_acl
            return 1, None

        if candidate == "setfilesecurity_auto_inherit_req":
            descriptor, keepalive_acl = self._build_absolute_dacl_descriptor(
                snapshot, auto_inherit_req=True
            )
            success = self._advapi32.SetFileSecurityW(
                file_path, DACL_SECURITY_INFORMATION, descriptor
            )
            if not success:
                return 0, str(self._last_error("SetFileSecurityW(auto inherit request)"))
            _ = keepalive_acl
            return 1, None

        raise DaclRestoreApiExperimentError(f"unknown restore API candidate: {candidate!r}")

    def run_candidate(self, candidate: str) -> RestoreApiCandidateResult:
        if os.name != "nt":
            raise DaclRestoreApiExperimentError("restore API experiment is Windows-only")
        if candidate not in RESTORE_API_CANDIDATES:
            raise DaclRestoreApiExperimentError("restore API candidate is not allowlisted")

        root = None
        file_path = None
        handle = None
        result = None
        cleanup_error = None
        try:
            temp_root = self._temp_root()
            self._require_ntfs(temp_root)
            root = tempfile.mkdtemp(prefix="dcp-psec-restore-api-", dir=temp_root)
            filesystem = self._require_ntfs(root)
            file_path = os.path.join(root, "probe-" + uuid.uuid4().hex + ".bin")
            handle, keepalive = self._create_file(file_path, defaulted=False)

            identity_before = self._reader.query_identity(handle)
            if identity_before.is_directory or identity_before.attributes & 0x00000400:
                raise DaclRestoreApiExperimentError(
                    "created probe handle is a directory or reparse point"
                )
            original = capture_original_snapshot_from_handle(
                self._reader, handle, str(uuid.uuid4())
            )
            if not original.verify_integrity():
                raise DaclRestoreApiExperimentError("S0 snapshot integrity verification failed")
            if (
                original.target_identity.volume_serial != identity_before.volume_serial
                or original.target_identity.file_id != identity_before.file_id.casefold()
            ):
                raise DaclRestoreApiExperimentError(
                    "target identity changed during S0 capture"
                )

            forward_code = self._advapi32.SetSecurityInfo(
                wintypes.HANDLE(handle),
                SE_FILE_OBJECT,
                DACL_AND_PROTECTED_SECURITY_INFO,
                None,
                None,
                ctypes.cast(
                    ctypes.create_string_buffer(
                        original.descriptor.dacl_bytes,
                        len(original.descriptor.dacl_bytes),
                    ),
                    wintypes.LPVOID,
                ),
                None,
            )
            if forward_code != 0:
                raise DaclRestoreApiExperimentError(
                    f"SetSecurityInfo forward mutation failed (WinError {int(forward_code)})"
                )
            s1 = self._reader.read_dacl(handle)
            identity_after_s1 = self._reader.query_identity(handle)
            if identity_after_s1 != identity_before:
                raise DaclRestoreApiExperimentError("target identity changed after S1 mutation")

            api_return_code = None
            api_error = None
            try:
                api_return_code, api_error = self._apply_restore_candidate(
                    candidate,
                    file_path=file_path,
                    handle=handle,
                    snapshot=original.descriptor,
                )
            except Exception as exc:
                api_error = str(exc)

            readback_error = None
            s2 = None
            verification = None
            try:
                s2 = self._reader.read_dacl(handle)
                identity_after_s2 = self._reader.query_identity(handle)
                if identity_after_s2 != identity_before:
                    raise DaclRestoreApiExperimentError(
                        "target identity changed after candidate restoration"
                    )
                verification = verify_restoration_readback(
                    original,
                    transaction_id=original.transaction_id,
                    target_identity=TargetObjectIdentity(
                        identity_after_s2.volume_serial, identity_after_s2.file_id
                    ),
                    readback=s2,
                    comparison_profile=DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
                )
            except Exception as exc:
                readback_error = str(exc)

            result = RestoreApiCandidateResult(
                candidate=candidate,
                filesystem=filesystem,
                transaction_id=original.transaction_id,
                snapshot_integrity_sha256=original.integrity_sha256,
                volume_serial=original.target_identity.volume_serial,
                file_id=original.target_identity.file_id,
                control_flags_s0=original.descriptor.dacl_control_flags,
                control_flags_s1=s1.dacl_control_flags,
                control_flags_s2=(s2.dacl_control_flags if s2 is not None else None),
                dacl_bytes_s0_hex=original.descriptor.dacl_bytes.hex(),
                dacl_bytes_s1_hex=s1.dacl_bytes.hex(),
                dacl_bytes_s2_hex=(s2.dacl_bytes.hex() if s2 is not None else None),
                inherited_ace_count_s0=self._inherited_ace_count(original.descriptor),
                inherited_ace_count_s1=self._inherited_ace_count(s1),
                inherited_ace_count_s2=(
                    self._inherited_ace_count(s2) if s2 is not None else None
                ),
                api_return_code=api_return_code,
                api_error=api_error,
                readback_error=readback_error,
                verification_state=(
                    verification.state if verification is not None else None
                ),
                mismatches=verification.mismatches if verification is not None else (),
                cleanup_verified=False,
            )
        finally:
            if handle is not None:
                if not self._kernel32.CloseHandle(wintypes.HANDLE(handle)):
                    cleanup_error = self._last_error("CloseHandle(restore API experiment)")
                handle = None
            if file_path and os.path.exists(file_path):
                if not self._kernel32.DeleteFileW(file_path):
                    cleanup_error = cleanup_error or self._last_error(
                        "DeleteFileW(restore API experiment)"
                    )
            if root and os.path.isdir(root):
                try:
                    os.rmdir(root)
                except OSError as exc:
                    cleanup_error = cleanup_error or DaclRestoreApiExperimentError(
                        f"restore API experiment temp directory cleanup failed: {exc}"
                    )
            cleanup_ok = bool(root) and not os.path.exists(root)
            if not cleanup_ok:
                cleanup_error = cleanup_error or DaclRestoreApiExperimentError(
                    "restore API experiment temp directory remains"
                )

        if cleanup_error:
            raise cleanup_error
        if result is None:
            raise DaclRestoreApiExperimentError("candidate produced no result")
        return RestoreApiCandidateResult(
            **{
                **result.__dict__,
                "cleanup_verified": True,
            }
        )

    def run_all(self) -> tuple[RestoreApiCandidateResult, ...]:
        return tuple(self.run_candidate(candidate) for candidate in RESTORE_API_CANDIDATES)
