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


SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x00000004
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


class DaclExperimentError(RuntimeError):
    """The disposable native experiment could not prove a safe result."""


@dataclass(frozen=True)
class ExperimentResult:
    filesystem: str
    dacl_defaulted_before: bool
    dacl_defaulted_after_write: bool
    dacl_bytes_equal_after_write: bool
    dacl_defaulted_after_rollback: bool
    dacl_bytes_equal_after_rollback: bool
    cleanup_verified: bool
    volume_serial: int
    file_id: str


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


class WindowsDaclDefaultedExperiment:
    """Run exactly one disposable-file round-trip using a retained file handle."""

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

    def _security_attributes(self, *, defaulted: bool):
        # An empty, non-NULL DACL is intentionally used only on the newly
        # created disposable file. The CREATE_NEW handle is retained and has
        # WRITE_DAC/READ_CONTROL; no later path reopen is required.
        descriptor = ctypes.create_string_buffer( SECURITY_DESCRIPTOR_SIZE := 64 )
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
            raise self._last_error("SetSecurityDescriptorDacl(defaulted=TRUE)")
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

    def _write_dacl(self, handle, snapshot):
        if not snapshot.dacl_present or snapshot.dacl_is_null or not snapshot.dacl_bytes:
            raise DaclExperimentError("only an explicit non-NULL DACL can be tested")
        acl_buffer = ctypes.create_string_buffer(snapshot.dacl_bytes, len(snapshot.dacl_bytes))
        result = self._advapi32.SetSecurityInfo(
            wintypes.HANDLE(handle), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
            None, None, ctypes.cast(acl_buffer, wintypes.LPVOID), None,
        )
        if result != 0:
            raise DaclExperimentError(f"SetSecurityInfo(handle,DACL) failed (WinError {int(result)})")

    def run(self, *, defaulted=True):
        root = None
        file_path = None
        handle = None
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
            identity_before = self._reader.query_identity(handle)
            if identity_before.is_directory or identity_before.attributes & 0x00000400:
                raise DaclExperimentError("created probe handle is a directory or reparse point")
            before = self._reader.read_dacl(handle)
            if defaulted and before.dacl_defaulted is not True:
                raise DaclExperimentError(
                    "NTFS did not retain DaclDefaulted=TRUE at creation; TRUE-state writer case NOT EXERCISED"
                )
            if not before.dacl_present or before.dacl_is_null:
                raise DaclExperimentError("created object did not expose an explicit non-NULL DACL")

            write_error = None
            try:
                self._write_dacl(handle, before)
            except Exception as exc:
                write_error = exc
            after = None
            readback_error = None
            try:
                after = self._reader.read_dacl(handle)
                if self._reader.query_identity(handle) != identity_before:
                    raise DaclExperimentError("retained handle identity changed after write")
            except Exception as exc:
                readback_error = exc

            # Rollback is unconditional after the write attempt, including
            # when the write or its read-back reports an error.
            rollback_error = None
            try:
                self._write_dacl(handle, before)
            except Exception as exc:
                rollback_error = exc
            restored = None
            rollback_read_error = None
            try:
                restored = self._reader.read_dacl(handle)
                if self._reader.query_identity(handle) != identity_before:
                    raise DaclExperimentError("retained handle identity changed after rollback")
            except Exception as exc:
                rollback_read_error = exc
            rollback_equal = bool(
                restored is not None
                and restored.dacl_bytes == before.dacl_bytes
                and restored.dacl_defaulted == before.dacl_defaulted
                and restored.dacl_control_flags == before.dacl_control_flags
            )
            if write_error or readback_error or rollback_error or rollback_read_error:
                raise DaclExperimentError(
                    "experiment error: "
                    f"write={write_error}; readback={readback_error}; "
                    f"rollback_write={rollback_error}; rollback_read={rollback_read_error}; "
                    f"rollback_equal={rollback_equal}"
                )
            if not rollback_equal:
                raise DaclExperimentError("rollback not verified: DACL bytes/control state differ")
            result = ExperimentResult(
                filesystem=filesystem,
                dacl_defaulted_before=before.dacl_defaulted,
                dacl_defaulted_after_write=after.dacl_defaulted,
                dacl_bytes_equal_after_write=(after is not None and after.dacl_bytes == before.dacl_bytes),
                dacl_defaulted_after_rollback=restored.dacl_defaulted,
                dacl_bytes_equal_after_rollback=rollback_equal,
                cleanup_verified=False,
                volume_serial=identity_before.volume_serial,
                file_id=identity_before.file_id,
            )
        except Exception as exc:
            primary_error = exc
        finally:
            close_error = None
            if handle is not None:
                if not self._kernel32.CloseHandle(wintypes.HANDLE(handle)):
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
        )
