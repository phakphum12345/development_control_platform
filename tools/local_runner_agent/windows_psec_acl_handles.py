"""Handle-relative Package-SID ACL authorization for disposable PSEC job trees.

This implementation opens every ancestor and descendant by handle, verifies
NTFS file identity between directory enumeration and relative open, and uses
GetSecurityInfo/SetSecurityInfo on retained handles. It never writes a DACL by
re-resolving a pathname.
"""
from __future__ import annotations

import ctypes
import ntpath
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from tools.local_runner_agent.windows_psec_acl import (
    CONTAINER_INHERIT_ACE,
    DACL_SECURITY_INFORMATION,
    FILE_TRAVERSE,
    GRANT_ACCESS,
    MODIFY,
    OBJECT_INHERIT_ACE,
    READ_EXECUTE,
    SE_FILE_OBJECT,
    SDDL_REVISION_1,
    TRUSTEE_IS_SID,
    TRUSTEE_IS_UNKNOWN,
    EXPLICIT_ACCESS_W,
    TRUSTEE_W,
    WindowsPsecAclError,
    _parse_allow_aces,
    _valid_package_sid,
    _validate_private_roots,
)


FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
FILE_READ_ATTRIBUTES = 0x00000080
FILE_LIST_DIRECTORY = 0x00000001
READ_CONTROL = 0x00020000
WRITE_DAC = 0x00040000
SYNCHRONIZE = 0x00100000

FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_DELETE_CHILD = 0x00000040
OPEN_EXISTING = 3

FILE_OPEN = 1
FILE_DIRECTORY_FILE = 0x00000001
FILE_NON_DIRECTORY_FILE = 0x00000040
FILE_OPEN_REPARSE_POINT = 0x00200000
FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
OBJ_CASE_INSENSITIVE = 0x00000040
OBJ_DONT_REPARSE = 0x00001000

FILE_ID_BOTH_DIR_INFO_CLASS = 10
FILE_ID_BOTH_DIR_RESTART_INFO_CLASS = 11
FILE_STREAM_INFO_CLASS = 7
ERROR_NO_MORE_FILES = 18
STATUS_SUCCESS = 0

_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", _FILETIME),
        ("ftLastAccessTime", _FILETIME),
        ("ftLastWriteTime", _FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


class _FILE_ID_BOTH_DIR_INFO(ctypes.Structure):
    _fields_ = [
        ("NextEntryOffset", wintypes.DWORD),
        ("FileIndex", wintypes.DWORD),
        ("CreationTime", ctypes.c_longlong),
        ("LastAccessTime", ctypes.c_longlong),
        ("LastWriteTime", ctypes.c_longlong),
        ("ChangeTime", ctypes.c_longlong),
        ("EndOfFile", ctypes.c_longlong),
        ("AllocationSize", ctypes.c_longlong),
        ("FileAttributes", wintypes.DWORD),
        ("FileNameLength", wintypes.DWORD),
        ("EaSize", wintypes.DWORD),
        ("ShortNameLength", ctypes.c_byte),
        ("ShortName", wintypes.WCHAR * 12),
        ("FileId", ctypes.c_longlong),
        ("FileName", wintypes.WCHAR * 1),
    ]


class _UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", wintypes.LPWSTR),
    ]


class _OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(_UNICODE_STRING)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", wintypes.LPVOID),
        ("SecurityQualityOfService", wintypes.LPVOID),
    ]


class _IO_STATUS_BLOCK(ctypes.Structure):
    _fields_ = [
        ("Status", ctypes.c_void_p),
        ("Information", ctypes.c_size_t),
    ]


class _ACL_HEADER(ctypes.Structure):
    _fields_ = [
        ("AclRevision", ctypes.c_ubyte),
        ("Sbz1", ctypes.c_ubyte),
        ("AclSize", wintypes.USHORT),
        ("AceCount", wintypes.USHORT),
        ("Sbz2", wintypes.USHORT),
    ]


@dataclass(frozen=True)
class DirectoryEntry:
    name: str
    attributes: int
    file_id: int


@dataclass
class HandleEntry:
    handle: wintypes.HANDLE
    path: str
    is_directory: bool
    volume_serial: int
    file_id: int
    attributes: int
    link_count: int


class _WindowsHandleAclApi:
    """Native NTFS adapter using relative opens and handle-based ACL APIs."""

    def __init__(self):
        if os.name != "nt":
            raise WindowsPsecAclError(
                "handle-relative Package-SID ACLs require Windows NTFS"
            )
        if ctypes.sizeof(wintypes.WCHAR) != 2:
            raise WindowsPsecAclError("Windows WCHAR ABI is unavailable")
        if (_FILE_ID_BOTH_DIR_INFO.FileId.offset != 96
                or _FILE_ID_BOTH_DIR_INFO.FileName.offset != 104):
            raise WindowsPsecAclError(
                "FILE_ID_BOTH_DIR_INFO structure layout is not the expected Windows ABI"
            )

        self.kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        self.advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
        self.ntdll = ctypes.WinDLL("ntdll.dll")

        k = self.kernel32
        k.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        k.CreateFileW.restype = wintypes.HANDLE
        k.GetFileInformationByHandle.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION),
        ]
        k.GetFileInformationByHandle.restype = wintypes.BOOL
        k.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        k.GetFileInformationByHandleEx.restype = wintypes.BOOL
        k.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
        ]
        k.GetVolumeInformationW.restype = wintypes.BOOL
        k.LocalFree.argtypes = [wintypes.LPVOID]
        k.LocalFree.restype = wintypes.LPVOID

        a = self.advapi32
        a.GetSecurityInfo.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
        ]
        a.GetSecurityInfo.restype = wintypes.DWORD
        a.SetSecurityInfo.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
        ]
        a.SetSecurityInfo.restype = wintypes.DWORD
        a.GetSecurityDescriptorDacl.argtypes = [
            wintypes.LPVOID, ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.BOOL),
        ]
        a.GetSecurityDescriptorDacl.restype = wintypes.BOOL
        a.ConvertStringSidToSidW.argtypes = [
            wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPVOID),
        ]
        a.ConvertStringSidToSidW.restype = wintypes.BOOL
        a.SetEntriesInAclW.argtypes = [
            wintypes.ULONG, ctypes.POINTER(EXPLICIT_ACCESS_W), wintypes.LPVOID,
            ctypes.POINTER(wintypes.LPVOID),
        ]
        a.SetEntriesInAclW.restype = wintypes.DWORD
        a.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(wintypes.DWORD),
        ]
        a.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL

        n = self.ntdll
        n.NtCreateFile.argtypes = [
            ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
            ctypes.POINTER(_OBJECT_ATTRIBUTES), ctypes.POINTER(_IO_STATUS_BLOCK),
            ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        ]
        n.NtCreateFile.restype = ctypes.c_long
        n.NtClose.argtypes = [wintypes.HANDLE]
        n.NtClose.restype = ctypes.c_long

    @staticmethod
    def _raise_win32(operation: str) -> None:
        error = ctypes.get_last_error()
        raise WindowsPsecAclError(
            f"{operation} failed (Windows error {error})"
        )

    @staticmethod
    def _raise_nt(operation: str, status: int) -> None:
        raise WindowsPsecAclError(
            f"{operation} failed (NTSTATUS 0x{status & 0xFFFFFFFF:08x})"
        )

    def _file_info(self, handle: wintypes.HANDLE) -> _BY_HANDLE_FILE_INFORMATION:
        info = _BY_HANDLE_FILE_INFORMATION()
        if not self.kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            self._raise_win32("GetFileInformationByHandle")
        return info

    @staticmethod
    def _file_id(info: _BY_HANDLE_FILE_INFORMATION) -> int:
        return (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)

    def _handle_entry(
        self, handle: wintypes.HANDLE, path: str, *, expected_directory: bool,
        expected_file_id: int | None, volume_serial: int | None,
    ) -> HandleEntry:
        info = self._file_info(handle)
        attributes = int(info.dwFileAttributes)
        is_directory = bool(attributes & FILE_ATTRIBUTE_DIRECTORY)
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise WindowsPsecAclError(
                f"handle-relative ACL target is a reparse point: {path}"
            )
        if is_directory != expected_directory:
            raise WindowsPsecAclError(
                f"handle-relative ACL target type changed: {path}"
            )
        file_id = self._file_id(info)
        serial = int(info.dwVolumeSerialNumber)
        if not file_id or not serial:
            raise WindowsPsecAclError(
                f"filesystem object identity is unavailable: {path}"
            )
        if expected_file_id is not None and file_id != expected_file_id:
            raise WindowsPsecAclError(
                f"directory entry identity changed between enumeration and relative open: {path}"
            )
        if volume_serial is not None and serial != volume_serial:
            raise WindowsPsecAclError(
                f"handle-relative traversal crossed a volume boundary: {path}"
            )
        links = int(info.nNumberOfLinks)
        if not is_directory and links != 1:
            raise WindowsPsecAclError(
                f"handle-relative ACL target is multiply linked or link count is unknown: {path}"
            )
        return HandleEntry(
            handle=handle,
            path=path,
            is_directory=is_directory,
            volume_serial=serial,
            file_id=file_id,
            attributes=attributes,
            link_count=links,
        )

    def open_drive_root(self, drive_root: str) -> HandleEntry:
        handle = self.kernel32.CreateFileW(
            drive_root,
            FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if not handle or handle == _INVALID_HANDLE_VALUE:
            self._raise_win32("CreateFileW(volume root)")
        try:
            root = self._handle_entry(
                handle, drive_root, expected_directory=True,
                expected_file_id=None, volume_serial=None,
            )
            filesystem_name = ctypes.create_unicode_buffer(32)
            if not self.kernel32.GetVolumeInformationW(
                drive_root, None, 0, None, None, None,
                filesystem_name, len(filesystem_name),
            ):
                self._raise_win32("GetVolumeInformationW")
            if filesystem_name.value.upper() != "NTFS":
                raise WindowsPsecAclError(
                    f"handle-relative ACL target volume must be NTFS, got {filesystem_name.value!r}"
                )
            return root
        except Exception:
            self.close_handle(handle)
            raise

    def enumerate_directory(self, directory: HandleEntry) -> list[DirectoryEntry]:
        if not directory.is_directory:
            raise WindowsPsecAclError(
                f"cannot enumerate a non-directory handle: {directory.path}"
            )
        buffer_size = 64 * 1024
        buffer = ctypes.create_string_buffer(buffer_size)
        base = ctypes.addressof(buffer)
        name_offset = _FILE_ID_BOTH_DIR_INFO.FileName.offset
        entries: list[DirectoryEntry] = []

        first_batch = True
        while True:
            information_class = (
                FILE_ID_BOTH_DIR_RESTART_INFO_CLASS
                if first_batch else FILE_ID_BOTH_DIR_INFO_CLASS
            )
            ok = self.kernel32.GetFileInformationByHandleEx(
                directory.handle,
                information_class,
                ctypes.cast(buffer, wintypes.LPVOID),
                buffer_size,
            )
            first_batch = False
            if not ok:
                error = ctypes.get_last_error()
                if error == ERROR_NO_MORE_FILES:
                    break
                self._raise_win32("GetFileInformationByHandleEx(FileIdBothDirectoryInfo)")

            offset = 0
            while True:
                if offset + name_offset > buffer_size:
                    raise WindowsPsecAclError(
                        "directory enumeration returned a truncated FILE_ID_BOTH_DIR_INFO"
                    )
                next_offset = int(ctypes.c_uint32.from_address(base + offset).value)
                attributes = int(ctypes.c_uint32.from_address(base + offset + 56).value)
                name_length = int(ctypes.c_uint32.from_address(base + offset + 60).value)
                file_id = int(ctypes.c_int64.from_address(base + offset + 96).value)
                if name_length <= 0 or name_length % 2:
                    raise WindowsPsecAclError(
                        "directory enumeration returned an invalid filename length"
                    )
                if offset + name_offset + name_length > buffer_size:
                    raise WindowsPsecAclError(
                        "directory enumeration filename exceeds its returned buffer"
                    )
                name = ctypes.wstring_at(base + offset + name_offset, name_length // 2)
                if name not in {".", ".."}:
                    entries.append(DirectoryEntry(
                        name=name,
                        attributes=attributes,
                        file_id=file_id & 0xFFFFFFFFFFFFFFFF,
                    ))
                if next_offset == 0:
                    break
                if next_offset < name_offset or next_offset % 8 or offset + next_offset >= buffer_size:
                    raise WindowsPsecAclError(
                        "directory enumeration returned an invalid entry offset"
                    )
                offset += next_offset

        seen: set[str] = set()
        for entry in entries:
            folded = entry.name.casefold()
            if folded in seen:
                raise WindowsPsecAclError(
                    f"directory has a case-insensitive name collision: {directory.path}"
                )
            seen.add(folded)
        return entries

    @staticmethod
    def _validate_component(name: str) -> None:
        if (
            not name or name in {".", ".."} or name.endswith((".", " "))
            or any(ord(char) < 32 for char in name)
            or any(char in name for char in '<>:"/\\|?*')
        ):
            raise WindowsPsecAclError("directory contains an invalid Windows path component")

    def open_child(
        self, parent: HandleEntry, name: str, *, is_directory: bool,
        expected_file_id: int, write_dac: bool = True,
    ) -> HandleEntry:
        self._validate_component(name)
        if parent.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise WindowsPsecAclError("relative-open parent is a reparse point")
        name_buffer = ctypes.create_unicode_buffer(name)
        encoded_length = len(name.encode("utf-16-le"))
        unicode_name = _UNICODE_STRING(
            encoded_length,
            encoded_length,
            ctypes.cast(name_buffer, wintypes.LPWSTR),
        )
        object_attributes = _OBJECT_ATTRIBUTES(
            ctypes.sizeof(_OBJECT_ATTRIBUTES),
            parent.handle,
            ctypes.pointer(unicode_name),
            OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE,
            None,
            None,
        )
        desired_access = FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE
        if is_directory:
            desired_access |= FILE_LIST_DIRECTORY
        if write_dac:
            desired_access |= WRITE_DAC
        create_options = (
            FILE_OPEN_REPARSE_POINT
            | FILE_SYNCHRONOUS_IO_NONALERT
            | (FILE_DIRECTORY_FILE if is_directory else FILE_NON_DIRECTORY_FILE)
        )
        output_handle = wintypes.HANDLE()
        io_status = _IO_STATUS_BLOCK()
        status = int(self.ntdll.NtCreateFile(
            ctypes.byref(output_handle),
            desired_access,
            ctypes.byref(object_attributes),
            ctypes.byref(io_status),
            None,
            0,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            FILE_OPEN,
            create_options,
            None,
            0,
        ))
        if status < 0 or not output_handle:
            self._raise_nt("NtCreateFile(relative child)", status)
        path = ntpath.join(parent.path, name)
        try:
            return self._handle_entry(
                output_handle,
                path,
                expected_directory=is_directory,
                expected_file_id=expected_file_id,
                volume_serial=parent.volume_serial,
            )
        except Exception:
            self.close_handle(output_handle)
            raise

    def enumerate_streams(self, item: HandleEntry) -> list[str]:
        if item.is_directory:
            return []
        buffer_size = 64 * 1024
        buffer = ctypes.create_string_buffer(buffer_size)
        base = ctypes.addressof(buffer)
        streams = []
        ok = self.kernel32.GetFileInformationByHandleEx(
            item.handle,
            FILE_STREAM_INFO_CLASS,
            ctypes.cast(buffer, wintypes.LPVOID),
            buffer_size,
        )
        if not ok:
            self._raise_win32("GetFileInformationByHandleEx(FileStreamInfo)")
        offset = 0
        while True:
            if offset + 24 > buffer_size:
                raise WindowsPsecAclError(
                    f"file stream enumeration returned a truncated record: {item.path}"
                )
            next_offset = int(ctypes.c_uint32.from_address(base + offset).value)
            name_length = int(ctypes.c_uint32.from_address(base + offset + 4).value)
            if name_length <= 0 or name_length % 2 or offset + 24 + name_length > buffer_size:
                raise WindowsPsecAclError(
                    f"file stream enumeration returned an invalid name: {item.path}"
                )
            streams.append(
                ctypes.wstring_at(base + offset + 24, name_length // 2)
            )
            if next_offset == 0:
                break
            if next_offset < 24 or next_offset % 8 or offset + next_offset >= buffer_size:
                raise WindowsPsecAclError(
                    f"file stream enumeration returned an invalid offset: {item.path}"
                )
            offset += next_offset
        return streams

    def verify_identity(self, item: HandleEntry) -> None:
        info = self._file_info(item.handle)
        attributes = int(info.dwFileAttributes)
        is_directory = bool(attributes & FILE_ATTRIBUTE_DIRECTORY)
        file_id = self._file_id(info)
        volume_serial = int(info.dwVolumeSerialNumber)
        link_count = int(info.nNumberOfLinks)
        if (
            attributes & FILE_ATTRIBUTE_REPARSE_POINT
            or is_directory != item.is_directory
            or file_id != item.file_id
            or volume_serial != item.volume_serial
            or link_count != item.link_count
            or (not is_directory and link_count != 1)
        ):
            raise WindowsPsecAclError(
                f"filesystem object identity or type changed before ACL mutation: {item.path}"
            )

    def open_ancestor_chain(self, directory: str | os.PathLike) -> list[HandleEntry]:
        path = ntpath.normpath(str(directory))
        drive, tail = ntpath.splitdrive(path)
        if len(drive) != 2 or not tail.startswith("\\"):
            raise WindowsPsecAclError(
                "private parent must be an absolute local drive path on NTFS"
            )
        chain: list[HandleEntry] = []
        try:
            current = self.open_drive_root(drive + "\\")
            chain.append(current)
            for component in (part for part in tail.split("\\") if part):
                entries = self.enumerate_directory(current)
                matches = [entry for entry in entries if entry.name.casefold() == component.casefold()]
                if len(matches) != 1:
                    raise WindowsPsecAclError(
                        f"private parent component is missing or ambiguous: {component}"
                    )
                entry = matches[0]
                if entry.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    raise WindowsPsecAclError(
                        f"private parent contains a reparse point: {component}"
                    )
                if not entry.attributes & FILE_ATTRIBUTE_DIRECTORY:
                    raise WindowsPsecAclError(
                        f"private parent component is not a directory: {component}"
                    )
                child = self.open_child(
                    current, component, is_directory=True,
                    expected_file_id=entry.file_id, write_dac=False,
                )
                chain.append(child)
                current = child
            return chain
        except Exception:
            for item in reversed(chain):
                try:
                    self.close_handle(item.handle)
                except Exception:
                    pass
            raise

    def _get_security_descriptor(self, item: HandleEntry):
        owner = wintypes.LPVOID()
        group = wintypes.LPVOID()
        dacl = wintypes.LPVOID()
        sacl = wintypes.LPVOID()
        descriptor = wintypes.LPVOID()
        result = self.advapi32.GetSecurityInfo(
            item.handle, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
            ctypes.byref(owner), ctypes.byref(group), ctypes.byref(dacl),
            ctypes.byref(sacl), ctypes.byref(descriptor),
        )
        if result != 0:
            raise WindowsPsecAclError(f"GetSecurityInfo failed ({result})")
        return descriptor, dacl

    def read_sddl(self, item: HandleEntry) -> str:
        descriptor, _ = self._get_security_descriptor(item)
        rendered = wintypes.LPWSTR()
        try:
            if not self.advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                descriptor, SDDL_REVISION_1, DACL_SECURITY_INFORMATION,
                ctypes.byref(rendered), None,
            ):
                self._raise_win32("ConvertSecurityDescriptorToStringSecurityDescriptorW")
            return rendered.value or ""
        finally:
            if rendered:
                self.kernel32.LocalFree(rendered)
            if descriptor:
                self.kernel32.LocalFree(descriptor)

    def snapshot_dacl(self, item: HandleEntry) -> bytes:
        descriptor, _ = self._get_security_descriptor(item)
        try:
            present = wintypes.BOOL()
            dacl = wintypes.LPVOID()
            defaulted = wintypes.BOOL()
            if not self.advapi32.GetSecurityDescriptorDacl(
                descriptor, ctypes.byref(present), ctypes.byref(dacl),
                ctypes.byref(defaulted),
            ):
                self._raise_win32("GetSecurityDescriptorDacl")
            if not present.value or not dacl:
                raise WindowsPsecAclError(
                    f"target has an absent or NULL DACL: {item.path}"
                )
            header = ctypes.cast(dacl, ctypes.POINTER(_ACL_HEADER)).contents
            size = int(header.AclSize)
            if size < ctypes.sizeof(_ACL_HEADER) or size > 1024 * 1024:
                raise WindowsPsecAclError(
                    f"target DACL has an invalid size: {item.path}"
                )
            return ctypes.string_at(dacl, size)
        finally:
            if descriptor:
                self.kernel32.LocalFree(descriptor)

    def restore_dacl(self, item: HandleEntry, snapshot: bytes) -> None:
        buffer = ctypes.create_string_buffer(snapshot)
        result = self.advapi32.SetSecurityInfo(
            item.handle, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
            None, None, ctypes.cast(buffer, wintypes.LPVOID), None,
        )
        if result != 0:
            raise WindowsPsecAclError(f"SetSecurityInfo(restore) failed ({result})")
        if self.snapshot_dacl(item) != snapshot:
            raise WindowsPsecAclError(
                f"handle-relative DACL rollback verification failed: {item.path}"
            )

    def add_allow_ace(
        self, item: HandleEntry, package_sid: str, mask: int, inheritance: int,
    ) -> None:
        sid = wintypes.LPVOID()
        descriptor = wintypes.LPVOID()
        old_dacl = wintypes.LPVOID()
        new_acl = wintypes.LPVOID()
        try:
            if not self.advapi32.ConvertStringSidToSidW(package_sid, ctypes.byref(sid)):
                self._raise_win32("ConvertStringSidToSidW")
            descriptor, old_dacl = self._get_security_descriptor(item)
            entry = EXPLICIT_ACCESS_W()
            entry.grfAccessPermissions = mask
            entry.grfAccessMode = GRANT_ACCESS
            entry.grfInheritance = inheritance
            entry.Trustee = TRUSTEE_W(
                None, 0, TRUSTEE_IS_SID, TRUSTEE_IS_UNKNOWN, sid
            )
            result = self.advapi32.SetEntriesInAclW(
                1, ctypes.byref(entry), old_dacl, ctypes.byref(new_acl)
            )
            if result != 0:
                raise WindowsPsecAclError(f"SetEntriesInAclW failed ({result})")
            result = self.advapi32.SetSecurityInfo(
                item.handle, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
                None, None, new_acl, None,
            )
            if result != 0:
                raise WindowsPsecAclError(f"SetSecurityInfo failed ({result})")
        finally:
            for pointer in (new_acl, descriptor, sid):
                if pointer:
                    self.kernel32.LocalFree(pointer)

    def close_handle(self, handle: wintypes.HANDLE) -> None:
        status = int(self.ntdll.NtClose(handle))
        if status < 0:
            self._raise_nt("NtClose", status)


class WindowsPsecAclAuthorization:
    """Successful ACL authorization whose validated handles remain held."""

    def __init__(self, api, handles: list[HandleEntry], evidence: dict):
        self._api = api
        self._handles = list(handles)
        self.evidence = evidence
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        remaining = []
        errors = []
        for item in reversed(self._handles):
            try:
                self._api.close_handle(item.handle)
            except Exception as exc:
                remaining.append(item)
                errors.append(f"{item.path}: {type(exc).__name__}: {exc}")
        self._handles = list(reversed(remaining))
        if self._handles:
            raise WindowsPsecAclError(
                "handle-relative ACL authorization handle cleanup failed: "
                + "; ".join(errors)
            )
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False


class WindowsPsecHandleAclManager:
    """Apply exact Package-SID DACLs using only retained, relative-open handles."""

    def __init__(self, api=None):
        self._api = api

    @staticmethod
    def _find_entry(api, directory: HandleEntry, name: str) -> DirectoryEntry:
        matches = [
            entry for entry in api.enumerate_directory(directory)
            if entry.name.casefold() == name.casefold()
        ]
        if len(matches) != 1:
            raise WindowsPsecAclError(
                f"expected exactly one directory entry named {name!r} under {directory.path}"
            )
        entry = matches[0]
        if entry.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise WindowsPsecAclError(
                f"directory entry is a reparse point: {ntpath.join(directory.path, name)}"
            )
        return entry

    @classmethod
    def _open_named_child(
        cls, api, parent: HandleEntry, name: str, *, is_directory: bool,
        handles: list[HandleEntry],
    ) -> HandleEntry:
        entry = cls._find_entry(api, parent, name)
        if bool(entry.attributes & FILE_ATTRIBUTE_DIRECTORY) != is_directory:
            raise WindowsPsecAclError(
                f"directory entry has an unexpected type: {ntpath.join(parent.path, name)}"
            )
        child = api.open_child(
            parent, name, is_directory=is_directory,
            expected_file_id=entry.file_id, write_dac=True,
        )
        handles.append(child)
        return child

    @staticmethod
    def _walk_tree(api, root: HandleEntry, handles: list[HandleEntry]):
        targets = [root]
        stack = [root]
        while stack:
            directory = stack.pop()
            entries = api.enumerate_directory(directory)
            seen: set[str] = set()
            for entry in sorted(entries, key=lambda item: item.name.casefold()):
                folded = entry.name.casefold()
                if folded in seen:
                    raise WindowsPsecAclError(
                        f"case-insensitive collision in handle-relative tree: {directory.path}"
                    )
                seen.add(folded)
                if entry.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    raise WindowsPsecAclError(
                        f"handle-relative tree contains a reparse point: {entry.name}"
                    )
                is_directory = bool(entry.attributes & FILE_ATTRIBUTE_DIRECTORY)
                child = api.open_child(
                    directory, entry.name, is_directory=is_directory,
                    expected_file_id=entry.file_id, write_dac=True,
                )
                handles.append(child)
                api.verify_identity(child)
                if not is_directory:
                    streams = api.enumerate_streams(child)
                    if [stream.casefold() for stream in streams] != ["::$data"]:
                        raise WindowsPsecAclError(
                            f"handle-relative tree contains an alternate or unsupported data stream: {child.path}"
                        )
                targets.append(child)
                if is_directory:
                    stack.append(child)
        return targets

    def apply(
        self, workspace: str | os.PathLike, scratch: str | os.PathLike,
        package_sid: str,
    ) -> WindowsPsecAclAuthorization:
        if not _valid_package_sid(package_sid):
            raise WindowsPsecAclError("AppContainer Package SID is invalid")
        work, temp, job_root = _validate_private_roots(workspace, scratch)
        api = self._api or _WindowsHandleAclApi()
        handles: list[HandleEntry] = []
        snapshots: list[tuple[HandleEntry, bytes]] = []
        changed: list[HandleEntry] = []

        try:
            chain = api.open_ancestor_chain(job_root.parent)
            handles.extend(chain)
            if not chain or ntpath.normcase(chain[-1].path) != ntpath.normcase(str(job_root.parent)):
                raise WindowsPsecAclError(
                    "handle-relative private-parent chain does not match the validated parent path"
                )
            parent = chain[-1]
            ancestor_sddl_before = [api.read_sddl(item) for item in chain]

            root = self._open_named_child(
                api, parent, job_root.name, is_directory=True, handles=handles
            )
            root_entries = api.enumerate_directory(root)
            root_names = {entry.name.casefold() for entry in root_entries}
            if root_names != {"workspace", "scratch"} or len(root_entries) != 2:
                raise WindowsPsecAclError(
                    "job root must contain exactly workspace and scratch directories"
                )

            projected = self._open_named_child(
                api, root, work.name, is_directory=True, handles=handles
            )
            private_scratch = self._open_named_child(
                api, root, temp.name, is_directory=True, handles=handles
            )
            workspace_targets = self._walk_tree(api, projected, handles)
            scratch_targets = self._walk_tree(api, private_scratch, handles)

            target_specs = [
                (root, [(FILE_TRAVERSE, 0)]),
                *(
                    (
                        item,
                        [(
                            READ_EXECUTE,
                            OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
                            if item.is_directory else 0,
                        )],
                    )
                    for item in workspace_targets
                ),
                *(
                    (
                        item,
                        (
                            [
                                (MODIFY, OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE),
                                (FILE_DELETE_CHILD, CONTAINER_INHERIT_ACE),
                            ]
                            if item.is_directory else [(MODIFY, 0)]
                        ),
                    )
                    for item in scratch_targets
                ),
            ]

            # Snapshot and validate every target before the first DACL write.
            already_authorized = {}
            for item, required_aces in target_specs:
                api.verify_identity(item)
                current_sddl = api.read_sddl(item)
                existing_aces = _parse_allow_aces(current_sddl, package_sid)
                allowed_mask = 0
                for mask, _ in required_aces:
                    allowed_mask |= mask
                if any(granted & ~allowed_mask for _, granted in existing_aces):
                    raise WindowsPsecAclError(
                        f"Package SID already has an overbroad allow ACE: {item.path}"
                    )
                already_authorized[id(item)] = all(
                    any(
                        granted == mask
                        and {
                            flags[index:index + 2]
                            for index in range(0, len(flags), 2)
                        }.issuperset(
                            {
                                flag for flag, bit in (("OI", OBJECT_INHERIT_ACE), ("CI", CONTAINER_INHERIT_ACE))
                                if inheritance & bit
                            }
                        )
                        for flags, granted in existing_aces
                    )
                    for mask, inheritance in required_aces
                )
                snapshots.append((item, api.snapshot_dacl(item)))

            verified = []
            for item, required_aces in target_specs:
                api.verify_identity(item)
                if not already_authorized[id(item)]:
                    changed.append(item)
                    for mask, inheritance in required_aces:
                        api.verify_identity(item)
                        api.add_allow_ace(item, package_sid, mask, inheritance)
                api.verify_identity(item)
                sddl = api.read_sddl(item)
                aces = _parse_allow_aces(sddl, package_sid)
                for mask, inheritance in required_aces:
                    required_flags = {
                        flag for flag, bit in (
                            ("OI", OBJECT_INHERIT_ACE),
                            ("CI", CONTAINER_INHERIT_ACE),
                        ) if inheritance & bit
                    }
                    matching = [
                        (flags, granted) for flags, granted in aces
                        if granted == mask
                        and {
                            flags[index:index + 2]
                            for index in range(0, len(flags), 2)
                        }.issuperset(required_flags)
                    ]
                    if not matching:
                        raise WindowsPsecAclError(
                            f"Package-SID ACE verification failed for {item.path} "
                            f"mask=0x{mask:08x}"
                        )
                allowed_mask = 0
                for mask, _ in required_aces:
                    allowed_mask |= mask
                if any(granted & ~allowed_mask for _, granted in aces):
                    raise WindowsPsecAclError(
                        f"Package SID has an overbroad allow ACE: {item.path}"
                    )
                verified.append({
                    "path": item.path,
                    "identity": {
                        "volume_serial": item.volume_serial,
                        "file_id": item.file_id,
                    },
                    "masks": [f"0x{mask:08x}" for mask, _ in required_aces],
                    "sddl": sddl,
                })

            ancestor_sddl_after = [api.read_sddl(item) for item in chain]
            if ancestor_sddl_before != ancestor_sddl_after:
                raise WindowsPsecAclError(
                    "shared parent or ancestor DACL changed during handle-relative ACL application"
                )

            evidence = {
                "state": "DACL_VERIFIED",
                "effective_access": "NOT_TESTED",
                "package_sid": package_sid,
                "handle_relative": True,
                "filesystem": "NTFS",
                "workspace_targets": len(workspace_targets),
                "scratch_targets": len(scratch_targets),
                "job_root_traverse_only": True,
                "shared_parent_sddl_unchanged": True,
                "shared_ancestor_sddl_unchanged": True,
                "parent_chain": [
                    {
                        "path": item.path,
                        "volume_serial": item.volume_serial,
                        "file_id": item.file_id,
                    }
                    for item in chain
                ],
                "targets": verified,
            }
            return WindowsPsecAclAuthorization(api, handles, evidence)

        except Exception as exc:
            rollback_errors = []
            # Restore parents before descendants so inheritance propagation
            # cannot overwrite a child rollback performed earlier.
            for item, snapshot in snapshots:
                if item not in changed:
                    continue
                try:
                    api.restore_dacl(item, snapshot)
                    if api.snapshot_dacl(item) != snapshot:
                        raise WindowsPsecAclError(
                            f"DACL rollback read-back mismatch: {item.path}"
                        )
                except Exception as rollback_exc:
                    rollback_errors.append(
                        f"{item.path}: {type(rollback_exc).__name__}: {rollback_exc}"
                    )

            close_errors = []
            for item in reversed(handles):
                try:
                    api.close_handle(item.handle)
                except Exception as close_exc:
                    close_errors.append(
                        f"{item.path}: {type(close_exc).__name__}: {close_exc}"
                    )

            rollback_state = "VERIFIED" if changed and not rollback_errors else (
                "NOT_REQUIRED" if not changed else "FAILED"
            )
            detail = (
                f"handle-relative ACL application failed: {type(exc).__name__}: {exc}; "
                f"rollback={rollback_state}"
            )
            if rollback_errors:
                detail += "; rollback_errors=" + " | ".join(rollback_errors)
            if close_errors:
                detail += "; handle_cleanup_errors=" + " | ".join(close_errors)
            raise WindowsPsecAclError(detail) from exc
