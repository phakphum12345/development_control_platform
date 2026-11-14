"""Native Windows handle-relative object opener for PSEC ACL preflight.

This module is deliberately a preflight primitive, not an ACL mutator. It opens
one child relative to a retained directory handle with NtCreateFile and records
handle-derived identity. It does not enumerate directories, change DACLs,
integrate with the launcher, or establish effective AppContainer access.

Until enumeration, transaction/rollback, and target-host adversarial tests are
implemented, callers must keep execution blocked.
"""
from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes
from dataclasses import dataclass


FILE_READ_ATTRIBUTES = 0x0080
READ_CONTROL = 0x00020000
WRITE_DAC = 0x00040000
SYNCHRONIZE = 0x00100000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
FILE_OPEN = 0x00000001
FILE_DIRECTORY_FILE = 0x00000001
FILE_NON_DIRECTORY_FILE = 0x00000040
FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
FILE_OPEN_REPARSE_POINT = 0x00200000
OBJ_CASE_INSENSITIVE = 0x00000040
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_ID_INFO_CLASS = 18
FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
STATUS_SUCCESS = 0

_INVALID_COMPONENT = re.compile(r"[:/\\\x00]", re.ASCII)


class NativeHandleAclError(RuntimeError):
    """A handle-relative preflight operation could not be proven safe."""


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", ctypes.c_wchar_p),
    ]


class OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(UNICODE_STRING)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", wintypes.LPVOID),
        ("SecurityQualityOfService", wintypes.LPVOID),
    ]


class IO_STATUS_BLOCK_UNION(ctypes.Union):
    _fields_ = [("Status", wintypes.LONG), ("Pointer", wintypes.LPVOID)]


class IO_STATUS_BLOCK(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("u", IO_STATUS_BLOCK_UNION), ("Information", ctypes.c_size_t)]


class FILE_ID_128(ctypes.Structure):
    _fields_ = [("Identifier", ctypes.c_ubyte * 16)]


class FILE_ID_INFO(ctypes.Structure):
    _fields_ = [
        ("VolumeSerialNumber", ctypes.c_ulonglong),
        ("FileId", FILE_ID_128),
    ]


class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", wintypes.DWORD),
        ("ReparseTag", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class HandleIdentity:
    volume_serial: int
    file_id: str
    is_directory: bool
    attributes: int
    reparse_tag: int


@dataclass
class OpenedObject:
    handle: int
    identity: HandleIdentity
    relative_name: str

    def close(self, close_handle) -> None:
        if self.handle:
            handle, self.handle = self.handle, 0
            if not close_handle(handle):
                raise NativeHandleAclError("CloseHandle failed for retained object")


def validate_relative_component(name: str) -> str:
    """Accept exactly one ordinary Win32 filename component."""
    if not isinstance(name, str) or not name or name in {".", ".."}:
        raise NativeHandleAclError("relative child name is empty or traversing")
    if _INVALID_COMPONENT.search(name):
        raise NativeHandleAclError("relative child name contains a namespace separator")
    if name.endswith((" ", ".")):
        raise NativeHandleAclError("relative child name has a Win32-normalized suffix")
    if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name, re.IGNORECASE | re.ASCII):
        raise NativeHandleAclError("relative child name is a reserved DOS device name")
    try:
        encoded_length = len(name.encode("utf-16-le"))
    except UnicodeEncodeError as exc:
        raise NativeHandleAclError("relative child name contains an invalid Unicode sequence") from exc
    if encoded_length > 510:
        raise NativeHandleAclError("relative child name exceeds the NT component limit")
    if any(ord(char) < 32 for char in name):
        raise NativeHandleAclError("relative child name contains a control character")
    return name


class WindowsNativeHandleApi:
    """Minimal NT/Win32 adapter; every child open is rooted at a retained handle."""

    def __init__(self):
        if os.name != "nt":
            raise NativeHandleAclError("native handle-relative ACL operations require Windows")
        self.ntdll = ctypes.WinDLL("ntdll.dll")
        self.kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        self.ntdll.NtCreateFile.argtypes = [
            ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
            ctypes.POINTER(OBJECT_ATTRIBUTES), ctypes.POINTER(IO_STATUS_BLOCK),
            ctypes.LPVOID, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
            wintypes.ULONG, wintypes.LPVOID, wintypes.ULONG,
        ]
        self.ntdll.NtCreateFile.restype = wintypes.LONG
        self.ntdll.RtlNtStatusToDosError.argtypes = [wintypes.LONG]
        self.ntdll.RtlNtStatusToDosError.restype = wintypes.ULONG
        self.kernel32.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        self.kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def open_child(self, parent_handle: int, name: str, *, directory: bool) -> OpenedObject:
        if not parent_handle or parent_handle in (0, ctypes.c_void_p(-1).value):
            raise NativeHandleAclError("a valid retained parent directory handle is required")
        component = validate_relative_component(name)
        # Keep the backing UTF-16 buffer alive for the duration of NtCreateFile.
        name_buffer = ctypes.create_unicode_buffer(component)
        name_bytes = len(component.encode("utf-16-le"))
        unicode_name = UNICODE_STRING(name_bytes, name_bytes + 2, ctypes.cast(
            name_buffer, ctypes.c_wchar_p
        ))
        object_name = ctypes.pointer(unicode_name)
        attributes = OBJECT_ATTRIBUTES(
            ctypes.sizeof(OBJECT_ATTRIBUTES),
            wintypes.HANDLE(parent_handle),
            object_name,
            OBJ_CASE_INSENSITIVE,
            None,
            None,
        )
        io_status = IO_STATUS_BLOCK()
        child = wintypes.HANDLE()
        desired_access = FILE_READ_ATTRIBUTES | READ_CONTROL | WRITE_DAC | SYNCHRONIZE
        create_options = FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT
        create_options |= FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE
        status = int(self.ntdll.NtCreateFile(
            ctypes.byref(child),
            desired_access,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            0,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            FILE_OPEN,
            create_options,
            None,
            0,
        ))
        if status != STATUS_SUCCESS:
            winerror = int(self.ntdll.RtlNtStatusToDosError(status))
            raise NativeHandleAclError(
                f"NtCreateFile(relative) failed (NTSTATUS=0x{status & 0xffffffff:08x}, WinError={winerror})"
            )
        try:
            identity = self.query_identity(child)
            if identity.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise NativeHandleAclError("relative child is a reparse point")
            if bool(identity.attributes & FILE_ATTRIBUTE_DIRECTORY) != directory:
                raise NativeHandleAclError("relative child object type does not match expectation")
            return OpenedObject(int(child.value), identity, component)
        except Exception:
            self.kernel32.CloseHandle(child)
            raise

    def query_identity(self, handle: int) -> HandleIdentity:
        file_id = FILE_ID_INFO()
        tag = FILE_ATTRIBUTE_TAG_INFO()
        if not self.kernel32.GetFileInformationByHandleEx(
            wintypes.HANDLE(handle), FILE_ID_INFO_CLASS,
            ctypes.byref(file_id), ctypes.sizeof(file_id),
        ):
            raise NativeHandleAclError(
                f"FileIdInfo query failed (WinError {ctypes.get_last_error()})"
            )
        if not self.kernel32.GetFileInformationByHandleEx(
            wintypes.HANDLE(handle), FILE_ATTRIBUTE_TAG_INFO_CLASS,
            ctypes.byref(tag), ctypes.sizeof(tag),
        ):
            raise NativeHandleAclError(
                f"FileAttributeTagInfo query failed (WinError {ctypes.get_last_error()})"
            )
        return HandleIdentity(
            volume_serial=int(file_id.VolumeSerialNumber),
            file_id=bytes(file_id.FileId.Identifier).hex(),
            is_directory=bool(tag.FileAttributes & FILE_ATTRIBUTE_DIRECTORY),
            attributes=int(tag.FileAttributes),
            reparse_tag=int(tag.ReparseTag),
        )

    def identity_unchanged(self, handle: int, expected: HandleIdentity) -> bool:
        """Re-query the same retained handle; never resolve the path again."""
        return self.query_identity(handle) == expected

    def close(self, handle: int) -> bool:
        return bool(self.kernel32.CloseHandle(wintypes.HANDLE(handle)))
