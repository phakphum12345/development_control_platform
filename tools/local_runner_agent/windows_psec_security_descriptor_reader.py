"""Read-only native Windows security descriptor inspection by retained handle.

This checkpoint intentionally implements descriptor acquisition only. It does
not construct ACLs, call SetSecurityInfo, mutate host ACLs, or authorize launch.
All returned ACL bytes are copied before the LocalFree-owned descriptor buffer
is released.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from .windows_psec_native_handles import (
    HandleIdentity,
    NativeHandleAclError,
    WindowsNativeHandleApi,
)
from .windows_psec_security_descriptor_transaction import DescriptorSnapshot


SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x00000004
ACL_SIZE_INFORMATION_CLASS = 2
ACL_HEADER_SIZE = 8
MAX_ACL_SIZE = 0xFFFF


class WindowsSecurityDescriptorReadError(RuntimeError):
    """A native security descriptor could not be read and validated safely."""


class ACL_SIZE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD),
        ("AclBytesFree", wintypes.DWORD),
    ]


class WindowsHandleSecurityReader:
    """Read identity and exact DACL state from the same retained Windows handle."""

    def __init__(self, identity_api=None):
        if os.name != "nt":
            raise WindowsSecurityDescriptorReadError(
                "native security descriptor reads require Windows"
            )
        self._identity_api = identity_api or WindowsNativeHandleApi()
        self._advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

        self._advapi32.GetSecurityInfo.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
        ]
        self._advapi32.GetSecurityInfo.restype = wintypes.DWORD
        self._advapi32.GetSecurityDescriptorControl.argtypes = [
            wintypes.LPVOID, ctypes.POINTER(wintypes.WORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._advapi32.GetSecurityDescriptorControl.restype = wintypes.BOOL
        self._advapi32.GetSecurityDescriptorDacl.argtypes = [
            wintypes.LPVOID, ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.BOOL),
        ]
        self._advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL
        self._advapi32.IsValidSecurityDescriptor.argtypes = [wintypes.LPVOID]
        self._advapi32.IsValidSecurityDescriptor.restype = wintypes.BOOL
        self._advapi32.IsValidAcl.argtypes = [wintypes.LPVOID]
        self._advapi32.IsValidAcl.restype = wintypes.BOOL
        self._advapi32.GetAclInformation.argtypes = [
            wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.c_int,
        ]
        self._advapi32.GetAclInformation.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

    def query_identity(self, handle: int) -> HandleIdentity:
        """Query the exact object behind a retained handle; never resolve a path."""
        try:
            return self._identity_api.query_identity(handle)
        except Exception as exc:
            raise WindowsSecurityDescriptorReadError(
                f"GetFileInformationByHandleEx(identity) failed: {exc}"
            ) from exc

    def read_dacl(self, handle: int) -> DescriptorSnapshot:
        """Return a bounded byte-for-byte DACL snapshot for a retained file handle."""
        if not isinstance(handle, int) or handle <= 0 or handle == ctypes.c_void_p(-1).value:
            raise WindowsSecurityDescriptorReadError("a valid retained handle is required")

        owner = wintypes.LPVOID()
        group = wintypes.LPVOID()
        dacl = wintypes.LPVOID()
        sacl = wintypes.LPVOID()
        descriptor = wintypes.LPVOID()
        result = self._advapi32.GetSecurityInfo(
            wintypes.HANDLE(handle),
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            ctypes.byref(owner),
            ctypes.byref(group),
            ctypes.byref(dacl),
            ctypes.byref(sacl),
            ctypes.byref(descriptor),
        )
        if result != 0:
            raise WindowsSecurityDescriptorReadError(
                f"GetSecurityInfo(handle, SE_FILE_OBJECT, DACL) failed (WinError {int(result)})"
            )
        if not descriptor:
            raise WindowsSecurityDescriptorReadError(
                "GetSecurityInfo returned success without a security descriptor"
            )

        primary_error = None
        try:
            if not self._advapi32.IsValidSecurityDescriptor(descriptor):
                raise WindowsSecurityDescriptorReadError(
                    "IsValidSecurityDescriptor rejected the returned descriptor"
                )

            control = wintypes.WORD()
            revision = wintypes.DWORD()
            if not self._advapi32.GetSecurityDescriptorControl(
                descriptor, ctypes.byref(control), ctypes.byref(revision)
            ):
                raise WindowsSecurityDescriptorReadError(
                    f"GetSecurityDescriptorControl failed (WinError {ctypes.get_last_error()})"
                )

            present = wintypes.BOOL()
            dacl_defaulted = wintypes.BOOL()
            dacl_pointer = wintypes.LPVOID()
            if not self._advapi32.GetSecurityDescriptorDacl(
                descriptor,
                ctypes.byref(present),
                ctypes.byref(dacl_pointer),
                ctypes.byref(dacl_defaulted),
            ):
                raise WindowsSecurityDescriptorReadError(
                    f"GetSecurityDescriptorDacl failed (WinError {ctypes.get_last_error()})"
                )

            if not present.value or not dacl_pointer:
                # The present bit and pointer state together distinguish an
                # absent DACL from a present-but-NULL DACL. Both are preserved
                # as no ACL bytes, and the coordinator will reject unsafe
                # candidates rather than silently treating either as empty.
                return DescriptorSnapshot(
                    dacl_present=bool(present.value),
                    dacl_is_null=True,
                    dacl_bytes=b"",
                    dacl_control_flags=int(control.value),
                    descriptor_revision=int(revision.value),
                    acl_revision=0,
                    ace_count=0,
                )

            if not self._advapi32.IsValidAcl(dacl_pointer):
                raise WindowsSecurityDescriptorReadError("IsValidAcl rejected the returned DACL")

            acl_info = ACL_SIZE_INFORMATION()
            if not self._advapi32.GetAclInformation(
                dacl_pointer,
                ctypes.byref(acl_info),
                ctypes.sizeof(acl_info),
                ACL_SIZE_INFORMATION_CLASS,
            ):
                raise WindowsSecurityDescriptorReadError(
                    f"GetAclInformation(AclSizeInformation) failed (WinError {ctypes.get_last_error()})"
                )

            bytes_in_use = int(acl_info.AclBytesInUse)
            bytes_free = int(acl_info.AclBytesFree)
            total_size = bytes_in_use + bytes_free
            if (
                bytes_in_use < ACL_HEADER_SIZE
                or total_size < bytes_in_use
                or total_size > MAX_ACL_SIZE
                or int(acl_info.AceCount) > 4096
            ):
                raise WindowsSecurityDescriptorReadError(
                    "ACL size or ACE count exceeds the accepted structural bounds"
                )

            raw_acl = ctypes.string_at(dacl_pointer, total_size)
            acl_revision = raw_acl[0]
            declared_size = int.from_bytes(raw_acl[2:4], "little")
            declared_count = int.from_bytes(raw_acl[4:6], "little")
            if (
                declared_size != total_size
                or declared_count != int(acl_info.AceCount)
                or acl_revision not in (2, 4)
            ):
                raise WindowsSecurityDescriptorReadError(
                    "ACL header disagrees with GetAclInformation metadata"
                )

            return DescriptorSnapshot(
                dacl_present=True,
                dacl_is_null=False,
                dacl_bytes=raw_acl,
                dacl_control_flags=int(control.value),
                descriptor_revision=int(revision.value),
                acl_revision=acl_revision,
                ace_count=declared_count,
            )
        except Exception as exc:
            primary_error = exc
            raise
        finally:
            # GetSecurityInfo allocates the descriptor with LocalAlloc. The
            # descriptor owns the DACL pointer; never free the DACL separately.
            free_result = self._kernel32.LocalFree(descriptor)
            if free_result:
                cleanup_error = WindowsSecurityDescriptorReadError(
                    "LocalFree failed for GetSecurityInfo descriptor buffer"
                )
                if primary_error is None:
                    raise cleanup_error
