"""Disposable NTFS experiment for DACL_DEFAULTED SetSecurityInfo semantics.

This is an opt-in Windows-host experiment, not a production writer. It creates
one uniquely named temporary directory and one CREATE_NEW file beneath it,
retains the original file handle, and never accepts a target path from callers.
"""
from __future__ import annotations

import ctypes
import os
import tempfile
import uuid
from ctypes import wintypes
from dataclasses import dataclass

from .windows_psec_security_descriptor_reader import WindowsHandleSecurityReader
from .windows_psec_dacl_comparison import DaclComparisonProfile
from .windows_psec_reversible_state import (
    TargetObjectIdentity,
    capture_original_snapshot_from_handle,
    verify_restoration_readback,
)


SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x00000004
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
DACL_ONLY_SECURITY_INFO = DACL_SECURITY_INFORMATION
DACL_AND_PROTECTED_SECURITY_INFO = (
    DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION
)
CREATE_NEW = 1
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
FILE_SHARE_DELETE = 4
READ_CONTROL = 0x00020000
WRITE_DAC = 0x00040000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
SECURITY_DESCRIPTOR_REVISION = 1
ACL_REVISION = 2
SE_DACL_PROTECTED = 0x1000
SE_DACL_DEFAULTED = 0x0008
SE_DACL_AUTO_INHERITED = 0x0400


def _control_flags_match_with_os_managed_auto_inherited(before: int, after: int) -> bool:
    """Allow Windows to set AUTO_INHERITED, but never clear it or alter other bits."""
    stable_mask = 0xFFFF ^ SE_DACL_AUTO_INHERITED
    stable_bits_match = (before & stable_mask) == (after & stable_mask)
    protected_state_matches = (before & SE_DACL_PROTECTED) == (after & SE_DACL_PROTECTED)
    auto_inherited_before = bool(before & SE_DACL_AUTO_INHERITED)
    auto_inherited_after = bool(after & SE_DACL_AUTO_INHERITED)
    auto_inherited_transition_allowed = auto_inherited_before <= auto_inherited_after
    return stable_bits_match and protected_state_matches and auto_inherited_transition_allowed


class DaclExperimentError(RuntimeError):
    """The disposable native experiment could not prove a safe result."""


class DaclDefaultedNotExercised(DaclExperimentError):
    """The filesystem did not retain the requested TRUE setup state."""

    def __init__(self, message, *, evidence=None):
        super().__init__(message)
        self.evidence = dict(evidence or {})


@dataclass(frozen=True)
class ExperimentResult:
    filesystem: str
    dacl_defaulted_before: bool
    dacl_defaulted_after_write: bool | None
    dacl_bytes_equal_after_write: bool
    dacl_defaulted_after_rollback: bool | None
    dacl_bytes_equal_after_rollback: bool
    cleanup_verified: bool
    volume_serial: int
    file_id: str
    process_handles_before: int
    process_handles_after: int
    process_handle_delta: int
    outcome: str
    write_verified: bool
    rollback_verified: bool
    api_errors: tuple[str, ...]
    dacl_bytes_before_hex: str
    dacl_bytes_after_write_hex: str | None
    dacl_bytes_after_rollback_hex: str | None
    control_flags_before: int
    control_flags_after_write: int | None
    control_flags_after_rollback: int | None
    security_info_flags: int = DACL_AND_PROTECTED_SECURITY_INFO
    owned_handle_opened: bool = False
    owned_handle_closed: bool = False
    close_handle_succeeded: bool | None = None
    inherited_ace_count_before: int = 0
    inherited_ace_count_after_write: int | None = None
    inherited_ace_count_after_rollback: int | None = None
    rollback_attempted: bool = True
    control_flags_after_each_write: tuple[int, ...] = ()
    native_write_calls: int = 0
    original_snapshot_transaction_id: str | None = None
    original_snapshot_integrity_sha256: str | None = None
    restoration_verification_state: str | None = None
    restoration_verification_mismatches: tuple[str, ...] = ()
    auto_inherited_changed_after_write: bool = False
    auto_inherited_changed_after_rollback: bool = False
    experiment_acceptance_profile: str = "NTFS_EXPERIMENT_OS_MANAGED_AUTO_INHERITED_ALLOWANCE"


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


class WindowsDaclDefaultedExperiment:
    """Probe disposable NTFS DACL semantics using one retained file handle."""

    def __init__(self, *, reader=None):
        if os.name != "nt":
            raise DaclExperimentError("the DACL experiment is Windows-only")
        self._kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        self._advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
        self._reader = reader or WindowsHandleSecurityReader()
        self.last_cleanup_verified = False
        self._configure()

    def _configure(self):
        k = self._kernel32
        a = self._advapi32
        k.GetTempPathW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
        k.GetTempPathW.restype = wintypes.DWORD
        k.GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        k.GetVolumePathNameW.restype = wintypes.BOOL
        k.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
        ]
        k.GetVolumeInformationW.restype = wintypes.BOOL
        k.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_SECURITY_ATTRIBUTES),
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        k.CreateFileW.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.DeleteFileW.argtypes = [wintypes.LPCWSTR]
        k.DeleteFileW.restype = wintypes.BOOL
        a.InitializeSecurityDescriptor.argtypes = [wintypes.LPVOID, wintypes.DWORD]
        a.InitializeSecurityDescriptor.restype = wintypes.BOOL
        a.InitializeAcl.argtypes = [wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD]
        a.InitializeAcl.restype = wintypes.BOOL
        a.SetSecurityDescriptorDacl.argtypes = [
            wintypes.LPVOID, wintypes.BOOL, wintypes.LPVOID, wintypes.BOOL,
        ]
        a.SetSecurityDescriptorDacl.restype = wintypes.BOOL
        a.GetSecurityDescriptorControl.argtypes = [
            wintypes.LPVOID, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD),
        ]
        a.GetSecurityDescriptorControl.restype = wintypes.BOOL
        a.SetSecurityDescriptorControl.argtypes = [wintypes.LPVOID, wintypes.WORD, wintypes.WORD]
        a.SetSecurityDescriptorControl.restype = wintypes.BOOL
        k.GetCurrentProcess.argtypes = []
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.GetProcessHandleCount.restype = wintypes.BOOL
        a.SetSecurityInfo.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
        ]
        a.SetSecurityInfo.restype = wintypes.DWORD

    def _last_error(self, operation):
        code = ctypes.get_last_error()
        return DaclExperimentError(f"{operation} failed (WinError {code})")

    def _temp_root(self):
        buffer = ctypes.create_unicode_buffer(32768)
        length = self._kernel32.GetTempPathW(len(buffer), buffer)
        if not length or length >= len(buffer):
            raise self._last_error("GetTempPathW")
        return buffer.value

    def _require_ntfs(self, path):
        volume = ctypes.create_unicode_buffer(32768)
        if not self._kernel32.GetVolumePathNameW(path, volume, len(volume)):
            raise self._last_error("GetVolumePathNameW")
        fs_name = ctypes.create_unicode_buffer(64)
        serial = wintypes.DWORD()
        max_component = wintypes.DWORD()
        flags = wintypes.DWORD()
        if not self._kernel32.GetVolumeInformationW(
            volume.value, None, 0, ctypes.byref(serial), ctypes.byref(max_component),
            ctypes.byref(flags), fs_name, len(fs_name),
        ):
            raise self._last_error("GetVolumeInformationW")
        if fs_name.value.upper() != "NTFS":
            raise DaclExperimentError(
                f"refusing experiment on non-NTFS volume: {fs_name.value!r}"
            )
        return fs_name.value

    def _security_descriptor_control(self, descriptor) -> int:
        control = wintypes.WORD()
        revision = wintypes.DWORD()
        if not self._advapi32.GetSecurityDescriptorControl(
            ctypes.cast(descriptor, wintypes.LPVOID),
            ctypes.byref(control),
            ctypes.byref(revision),
        ):
            raise self._last_error("GetSecurityDescriptorControl")
        return int(control.value)

    def _security_attributes(self, *, defaulted: bool):
        # An empty, non-NULL DACL is intentionally used only on the newly
        # created disposable file. The CREATE_NEW handle is retained and has
        # WRITE_DAC/READ_CONTROL; no later path reopen is required.
        descriptor = ctypes.create_string_buffer(64)
        acl = ctypes.create_string_buffer(8)
        if not self._advapi32.InitializeSecurityDescriptor(
            descriptor, SECURITY_DESCRIPTOR_REVISION
        ):
            raise self._last_error("InitializeSecurityDescriptor")
        if not self._advapi32.InitializeAcl(acl, len(acl), ACL_REVISION):
            raise self._last_error("InitializeAcl")
        if not self._advapi32.SetSecurityDescriptorDacl(
            descriptor, True, ctypes.cast(acl, wintypes.LPVOID), bool(defaulted)
        ):
            raise self._last_error("SetSecurityDescriptorDacl(defaulted flag)")
        # Prevent inherited ACEs from the temp directory from being merged
        # into this explicitly empty DACL. This keeps the test's ACL bytes
        # deterministic and makes the inheritance boundary explicit.
        if not self._advapi32.SetSecurityDescriptorControl(
            descriptor, SE_DACL_PROTECTED, SE_DACL_PROTECTED
        ):
            raise self._last_error("SetSecurityDescriptorControl(SE_DACL_PROTECTED)")
        attrs = _SECURITY_ATTRIBUTES(
            ctypes.sizeof(_SECURITY_ATTRIBUTES),
            ctypes.cast(descriptor, wintypes.LPVOID),
            False,
        )
        # Keep descriptor and ACL buffers alive while CreateFileW consumes them.
        return attrs, descriptor, acl

    def _create_file(self, path, *, defaulted):
        attrs, descriptor, acl = self._security_attributes(defaulted=defaulted)
        attrs_ptr = ctypes.byref(attrs)
        handle = self._kernel32.CreateFileW(
            path,
            READ_CONTROL | WRITE_DAC,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            attrs_ptr,
            CREATE_NEW,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if not handle or int(handle) == INVALID_HANDLE_VALUE:
            raise self._last_error("CreateFileW(CREATE_NEW)")
        return int(handle), (attrs, descriptor, acl)

    @staticmethod
    def _inherited_ace_count(snapshot):
        """Parse only bounded ACE headers; do not interpret or copy SID payloads."""
        if not snapshot.dacl_present or snapshot.dacl_is_null or not snapshot.dacl_bytes:
            return 0
        acl = snapshot.dacl_bytes
        if len(acl) < 8:
            raise DaclExperimentError("ACL is shorter than its header")
        declared_size = int.from_bytes(acl[2:4], "little")
        ace_count = int.from_bytes(acl[4:6], "little")
        if declared_size != len(acl) or ace_count > 4096:
            raise DaclExperimentError("ACL bounds/count invalid during ACE inheritance inspection")
        offset = 8
        inherited = 0
        for _ in range(ace_count):
            if offset + 4 > declared_size:
                raise DaclExperimentError("truncated ACE header")
            ace_flags = acl[offset + 1]
            ace_size = int.from_bytes(acl[offset + 2:offset + 4], "little")
            if ace_size < 4 or offset + ace_size > declared_size:
                raise DaclExperimentError("ACE size exceeds ACL bounds")
            if ace_flags & 0x10:  # INHERITED_ACE
                inherited += 1
            offset += ace_size
        # A valid ACL may have unused capacity after the last ACE. The ACL
        # header size bounds the buffer; ACE traversal must stay within it,
        # but need not consume AclBytesFree.
        return inherited

    def _write_dacl(self, handle, snapshot, *, security_info_flags):
        if not snapshot.dacl_present or snapshot.dacl_is_null or not snapshot.dacl_bytes:
            raise DaclExperimentError("only an explicit non-NULL DACL can be tested")
        acl_buffer = ctypes.create_string_buffer(snapshot.dacl_bytes, len(snapshot.dacl_bytes))
        result = self._advapi32.SetSecurityInfo(
            wintypes.HANDLE(handle), SE_FILE_OBJECT, security_info_flags,
            None, None, ctypes.cast(acl_buffer, wintypes.LPVOID), None,
        )
        if result != 0:
            raise DaclExperimentError(f"SetSecurityInfo(handle,DACL) failed (WinError {int(result)})")

    def _process_handle_count(self):
        count = wintypes.DWORD()
        process = self._kernel32.GetCurrentProcess()
        if not self._kernel32.GetProcessHandleCount(process, ctypes.byref(count)):
            raise self._last_error("GetProcessHandleCount")
        return int(count.value)

    def run(
        self, *, defaulted=True, rollback=True,
        security_info_flags=DACL_AND_PROTECTED_SECURITY_INFO,
        write_repetitions=1,
    ):
        if not isinstance(write_repetitions, int) or not 0 <= write_repetitions <= 8:
            raise DaclExperimentError("write_repetitions must be an integer from 0 through 8")
        if write_repetitions == 0 and rollback:
            raise DaclExperimentError("a no-write creation probe cannot request rollback")
        if security_info_flags not in (
            DACL_ONLY_SECURITY_INFO, DACL_AND_PROTECTED_SECURITY_INFO
        ):
            raise DaclExperimentError("unsupported SetSecurityInfo flag combination")
        # Process-wide counts are best-effort diagnostics only. They must not
        # gate the experiment or stand in for harness-owned handle tracking.
        try:
            handles_before = self._process_handle_count()
        except Exception:
            handles_before = -1
        root = None
        file_path = None
        handle = None
        owned_handle_opened = False
        owned_handle_closed = False
        close_handle_succeeded = None
        cleanup_ok = False
        primary_error = None
        result = None
        try:
            temp_root = self._temp_root()
            self._require_ntfs(temp_root)
            root = tempfile.mkdtemp(prefix="dcp-psec-dacl-exp-", dir=temp_root)
            # Re-check the exact newly created root's backing volume before
            # creating any object. Caller-supplied paths are never accepted.
            filesystem = self._require_ntfs(root)
            file_path = os.path.join(root, "probe-" + uuid.uuid4().hex + ".bin")
            handle, keepalive = self._create_file(file_path, defaulted=defaulted)
            owned_handle_opened = True
            identity_before = self._reader.query_identity(handle)
            if identity_before.is_directory or identity_before.attributes & 0x00000400:
                raise DaclExperimentError("created probe handle is a directory or reparse point")
            original_snapshot = capture_original_snapshot_from_handle(
                self._reader, handle, str(uuid.uuid4())
            )
            if not original_snapshot.verify_integrity():
                raise DaclExperimentError("immutable original snapshot integrity verification failed")
            if (
                original_snapshot.target_identity.volume_serial != identity_before.volume_serial
                or original_snapshot.target_identity.file_id != identity_before.file_id.casefold()
            ):
                raise DaclExperimentError("target identity changed before original snapshot capture")
            before = original_snapshot.descriptor
            current_before = self._reader.read_dacl(handle)
            if current_before != before:
                raise DaclExperimentError(
                    "DACL changed after immutable original snapshot capture"
                )
            if defaulted and before.dacl_defaulted is not True:
                raise DaclDefaultedNotExercised(
                    "NTFS did not retain DaclDefaulted=TRUE at creation; TRUE-state writer case NOT EXERCISED",
                    evidence={
                        "filesystem": filesystem,
                        "volume_serial": identity_before.volume_serial,
                        "file_id": identity_before.file_id,
                        "dacl_defaulted_after_create": before.dacl_defaulted,
                        "control_flags_after_create": before.dacl_control_flags,
                        "dacl_bytes_after_create_hex": before.dacl_bytes.hex(),
                        "inherited_ace_count_after_create": self._inherited_ace_count(before),
                        "original_snapshot_transaction_id": original_snapshot.transaction_id,
                        "original_snapshot_integrity_sha256": original_snapshot.integrity_sha256,
                    },
                )
            if not before.dacl_present or before.dacl_is_null:
                raise DaclExperimentError("created object did not expose an explicit non-NULL DACL")

            write_errors = []
            write_control_flags = []
            native_write_calls = 0
            after = before if write_repetitions == 0 else None
            readback_error = None
            for _ in range(write_repetitions):
                try:
                    native_write_calls += 1
                    self._write_dacl(
                        handle, before, security_info_flags=security_info_flags
                    )
                except Exception as exc:
                    write_errors.append(exc)
                    break
                try:
                    after = self._reader.read_dacl(handle)
                    if self._reader.query_identity(handle) != identity_before:
                        raise DaclExperimentError("retained handle identity changed after write")
                    write_control_flags.append(after.dacl_control_flags)
                except Exception as exc:
                    readback_error = exc
                    break
            write_error = "; ".join(str(error) for error in write_errors) or None

            # Rollback is unconditional in rollback mode after the write
            # attempt, including when write/read-back reports an error.
            # Write-only mode deliberately records the immediate effect on
            # this disposable object and then relies on deletion for cleanup.
            rollback_error = None
            rollback_read_error = None
            restored = None
            restoration_verification = None
            if rollback:
                try:
                    self._write_dacl(
                        handle, before, security_info_flags=security_info_flags
                    )
                except Exception as exc:
                    rollback_error = exc
                try:
                    restored = self._reader.read_dacl(handle)
                    identity_after_rollback = self._reader.query_identity(handle)
                    if identity_after_rollback != identity_before:
                        raise DaclExperimentError("retained handle identity changed after rollback")
                    restoration_verification = verify_restoration_readback(
                        original_snapshot,
                        transaction_id=original_snapshot.transaction_id,
                        target_identity=TargetObjectIdentity(
                            identity_after_rollback.volume_serial,
                            identity_after_rollback.file_id,
                        ),
                        readback=restored,
                        comparison_profile=DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
                    )
                except Exception as exc:
                    rollback_read_error = exc
            write_verified = bool(
                after is not None
                and after.dacl_bytes == before.dacl_bytes
                and after.dacl_defaulted == before.dacl_defaulted
                and _control_flags_match_with_os_managed_auto_inherited(
                    before.dacl_control_flags, after.dacl_control_flags
                )
            )
            rollback_equal = bool(
                restored is not None
                and restored.dacl_bytes == before.dacl_bytes
                and restored.dacl_defaulted == before.dacl_defaulted
                and _control_flags_match_with_os_managed_auto_inherited(
                    before.dacl_control_flags, restored.dacl_control_flags
                )
            )
            api_errors = tuple(
                str(error) for error in
                (write_error, readback_error, rollback_error, rollback_read_error)
                if error is not None
            )
            outcome = ("PASS" if write_verified and rollback_equal and not api_errors else "FAIL") if rollback else ("OBSERVED" if after is not None and not write_error and not readback_error else "FAIL")
            result = ExperimentResult(
                filesystem=filesystem,
                dacl_defaulted_before=before.dacl_defaulted,
                dacl_defaulted_after_write=(after.dacl_defaulted if after is not None else None),
                dacl_bytes_equal_after_write=(
                    after is not None and after.dacl_bytes == before.dacl_bytes
                ),
                dacl_defaulted_after_rollback=(
                    restored.dacl_defaulted if restored is not None else None
                ),
                dacl_bytes_equal_after_rollback=rollback_equal,
                cleanup_verified=False,
                volume_serial=identity_before.volume_serial,
                file_id=identity_before.file_id,
                process_handles_before=handles_before,
                process_handles_after=-1,
                process_handle_delta=-1,
                outcome=outcome,
                write_verified=write_verified,
                rollback_verified=rollback_equal,
                api_errors=api_errors,
                dacl_bytes_before_hex=before.dacl_bytes.hex(),
                dacl_bytes_after_write_hex=(after.dacl_bytes.hex() if after is not None else None),
                dacl_bytes_after_rollback_hex=(
                    restored.dacl_bytes.hex() if restored is not None else None
                ),
                control_flags_before=before.dacl_control_flags,
                control_flags_after_write=(
                    after.dacl_control_flags if after is not None else None
                ),
                control_flags_after_rollback=(
                    restored.dacl_control_flags if restored is not None else None
                ),
                security_info_flags=security_info_flags,
                owned_handle_opened=owned_handle_opened,
                inherited_ace_count_before=self._inherited_ace_count(before),
                inherited_ace_count_after_write=(self._inherited_ace_count(after) if after is not None else None),
                inherited_ace_count_after_rollback=(self._inherited_ace_count(restored) if restored is not None else None),
                rollback_attempted=bool(rollback),
                control_flags_after_each_write=tuple(write_control_flags),
                native_write_calls=native_write_calls,
                auto_inherited_changed_after_write=bool(
                    after is not None
                    and ((after.dacl_control_flags ^ before.dacl_control_flags) & SE_DACL_AUTO_INHERITED)
                ),
                auto_inherited_changed_after_rollback=bool(
                    restored is not None
                    and ((restored.dacl_control_flags ^ before.dacl_control_flags) & SE_DACL_AUTO_INHERITED)
                ),
                experiment_acceptance_profile="NTFS_EXPERIMENT_OS_MANAGED_AUTO_INHERITED_ALLOWANCE",
                original_snapshot_transaction_id=original_snapshot.transaction_id,
                original_snapshot_integrity_sha256=original_snapshot.integrity_sha256,
                restoration_verification_state=(
                    restoration_verification.state if restoration_verification is not None else None
                ),
                restoration_verification_mismatches=(
                    restoration_verification.mismatches if restoration_verification is not None else ()
                ),
            )
        except Exception as exc:
            primary_error = exc
        finally:
            close_error = None
            if handle is not None:
                close_handle_succeeded = bool(self._kernel32.CloseHandle(wintypes.HANDLE(handle)))
                if close_handle_succeeded:
                    owned_handle_closed = True
                else:
                    close_error = self._last_error("CloseHandle")
                handle = None
            delete_error = None
            if file_path and os.path.exists(file_path):
                if not self._kernel32.DeleteFileW(file_path):
                    delete_error = self._last_error("DeleteFileW(disposable file)")
            if root and os.path.isdir(root):
                try:
                    os.rmdir(root)  # remove only the exact empty directory created above
                except OSError as exc:
                    delete_error = delete_error or DaclExperimentError(
                        f"disposable root cleanup failed: {exc}"
                    )
            cleanup_ok = bool(root) and not os.path.exists(root)
            self.last_cleanup_verified = cleanup_ok
            try:
                handles_after = self._process_handle_count()
            except Exception:
                handles_after = -1
            if close_error or delete_error or not cleanup_ok:
                cleanup_error = close_error or delete_error or DaclExperimentError(
                    "disposable root remains after cleanup"
                )
                primary_error = primary_error or cleanup_error
        if primary_error:
            raise primary_error
        if result is None or not cleanup_ok:
            raise DaclExperimentError("experiment did not produce a verified result and cleanup")
        return ExperimentResult(
            filesystem=result.filesystem,
            dacl_defaulted_before=result.dacl_defaulted_before,
            dacl_defaulted_after_write=result.dacl_defaulted_after_write,
            dacl_bytes_equal_after_write=result.dacl_bytes_equal_after_write,
            dacl_defaulted_after_rollback=result.dacl_defaulted_after_rollback,
            dacl_bytes_equal_after_rollback=result.dacl_bytes_equal_after_rollback,
            cleanup_verified=True,
            volume_serial=result.volume_serial,
            file_id=result.file_id,
            process_handles_before=result.process_handles_before,
            process_handles_after=handles_after,
            process_handle_delta=(
                handles_after - result.process_handles_before
                if handles_after >= 0 and result.process_handles_before >= 0
                else -1
            ),
            outcome=result.outcome,
            write_verified=result.write_verified,
            rollback_verified=result.rollback_verified,
            api_errors=result.api_errors,
            dacl_bytes_before_hex=result.dacl_bytes_before_hex,
            dacl_bytes_after_write_hex=result.dacl_bytes_after_write_hex,
            dacl_bytes_after_rollback_hex=result.dacl_bytes_after_rollback_hex,
            control_flags_before=result.control_flags_before,
            control_flags_after_write=result.control_flags_after_write,
            control_flags_after_rollback=result.control_flags_after_rollback,
            security_info_flags=result.security_info_flags,
            owned_handle_opened=result.owned_handle_opened,
            owned_handle_closed=owned_handle_closed,
            close_handle_succeeded=close_handle_succeeded,
            inherited_ace_count_before=result.inherited_ace_count_before,
            inherited_ace_count_after_write=result.inherited_ace_count_after_write,
            inherited_ace_count_after_rollback=result.inherited_ace_count_after_rollback,
            rollback_attempted=result.rollback_attempted,
            control_flags_after_each_write=result.control_flags_after_each_write,
            native_write_calls=result.native_write_calls,
            auto_inherited_changed_after_write=result.auto_inherited_changed_after_write,
            auto_inherited_changed_after_rollback=result.auto_inherited_changed_after_rollback,
            experiment_acceptance_profile=result.experiment_acceptance_profile,
            original_snapshot_transaction_id=result.original_snapshot_transaction_id,
            original_snapshot_integrity_sha256=result.original_snapshot_integrity_sha256,
            restoration_verification_state=result.restoration_verification_state,
            restoration_verification_mismatches=result.restoration_verification_mismatches,
        )
