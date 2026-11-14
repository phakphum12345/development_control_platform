"""Trusted drive-root traversal and extended-ID directory enumeration.

This module performs read-only namespace discovery. It never changes ACLs,
creates/deletes files, or integrates with the PSEC launcher. Every descendant
is opened relative to a retained, identity-checked directory handle.
"""
from __future__ import annotations

import ctypes
import re
from ctypes import wintypes
from dataclasses import dataclass

from .windows_psec_native_handles import (
    FILE_ATTRIBUTE_DIRECTORY,
    FILE_ATTRIBUTE_REPARSE_POINT,
    FILE_READ_ATTRIBUTES,
    READ_CONTROL,
    SYNCHRONIZE,
    HandleIdentity,
    NativeHandleAclError,
    OpenedObject,
    validate_relative_component,
)

FILE_ID_EXTD_DIRECTORY_INFO_CLASS = 19
FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS = 20
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
OPEN_EXISTING = 3
ERROR_NO_MORE_FILES = 18
DIRECTORY_BUFFER_SIZE = 64 * 1024
DEFAULT_MAX_CHILDREN = 10000


class FILE_ID_128(ctypes.Structure):
    _fields_ = [("Identifier", ctypes.c_ubyte * 16)]


class FILE_ID_EXTD_DIR_INFO(ctypes.Structure):
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
        ("ReparsePointTag", wintypes.DWORD),
        ("FileId", FILE_ID_128),
        ("FileName", wintypes.WCHAR * 1),
    ]


@dataclass(frozen=True)
class ExtendedDirectoryEntry:
    name: str
    file_id: str
    attributes: int
    reparse_tag: int

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & FILE_ATTRIBUTE_DIRECTORY)


@dataclass
class OpenedDirectoryChain:
    """Owns every handle from the drive root through the requested directory."""

    api: object
    objects: list[OpenedObject]

    @property
    def leaf(self) -> OpenedObject:
        if not self.objects:
            raise NativeHandleAclError("directory chain is empty")
        return self.objects[-1]

    def close(self) -> None:
        errors = []
        for opened in reversed(self.objects):
            try:
                opened.close(self.api.close)
            except Exception as exc:  # close every retained handle even after one failure
                errors.append(str(exc))
        if errors:
            raise NativeHandleAclError(
                "one or more directory-chain handles failed to close: " + "; ".join(errors)
            )


def parse_drive_absolute_path(path: str) -> tuple[str, tuple[str, ...]]:
    """Accept only a canonical drive-letter absolute path; reject namespaces/UNC."""
    if not isinstance(path, str) or not path:
        raise NativeHandleAclError("root path must be a non-empty string")
    if "/" in path or path.startswith("\\\\") or path.startswith("\\\\?\\") or path.startswith("\\\\.\\"):
        raise NativeHandleAclError("UNC, device, extended, and slash-normalized paths are unsupported")
    match = re.fullmatch(r"([A-Za-z]):\\(.*)", path)
    if not match:
        raise NativeHandleAclError("root path must be an absolute drive-letter path such as C:\\work")
    drive = match.group(1).upper()
    tail = match.group(2)
    if tail.endswith("\\"):
        tail = tail[:-1]
    if tail and (not tail or tail.startswith("\\") or "\\\\" in tail):
        raise NativeHandleAclError("root path contains an empty path component")
    components = tuple(tail.split("\\")) if tail else ()
    for component in components:
        validate_relative_component(component)
    return drive, components


def parse_extended_directory_buffer(buffer: bytes, *, max_entries: int = DEFAULT_MAX_CHILDREN) -> list[ExtendedDirectoryEntry]:
    """Parse FILE_ID_EXTD_DIR_INFO records, failing closed on malformed offsets."""
    if max_entries < 1:
        raise NativeHandleAclError("max_entries must be positive")
    entries: list[ExtendedDirectoryEntry] = []
    offset = 0
    header_size = FILE_ID_EXTD_DIR_INFO.FileName.offset
    while True:
        if offset + ctypes.sizeof(FILE_ID_EXTD_DIR_INFO) > len(buffer):
            raise NativeHandleAclError("directory information record is truncated")
        record = FILE_ID_EXTD_DIR_INFO.from_buffer_copy(
            buffer[offset : offset + ctypes.sizeof(FILE_ID_EXTD_DIR_INFO)]
        )
        name_length = int(record.FileNameLength)
        name_start = offset + header_size
        name_end = name_start + name_length
        if name_length == 0 or name_length % 2 or name_end > len(buffer):
            raise NativeHandleAclError("directory entry has an invalid UTF-16 filename length")
        try:
            name = buffer[name_start:name_end].decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as exc:
            raise NativeHandleAclError("directory entry filename is invalid UTF-16") from exc
        entry = ExtendedDirectoryEntry(
            name=name,
            file_id=bytes(record.FileId.Identifier).hex(),
            attributes=int(record.FileAttributes),
            reparse_tag=int(record.ReparsePointTag),
        )
        entries.append(entry)
        if len(entries) > max_entries:
            raise NativeHandleAclError("directory entry count exceeds configured resource ceiling")
        next_offset = int(record.NextEntryOffset)
        if next_offset == 0:
            break
        if next_offset < header_size or next_offset % 8 or offset + next_offset > len(buffer):
            raise NativeHandleAclError("directory information contains an invalid next-entry offset")
        offset += next_offset
    return entries


class WindowsNativeHandleTree:
    """Read-only trusted-root traversal and direct-child handle enumeration."""

    def __init__(self, api):
        self.api = api
        if not hasattr(api, "kernel32") or not hasattr(api, "open_child"):
            raise NativeHandleAclError("native handle API adapter is incomplete")

    def open_directory_chain(self, path: str) -> OpenedDirectoryChain:
        drive, components = parse_drive_absolute_path(path)
        kernel32 = self.api.kernel32
        root_path = f"\\\\?\\{drive}:\\"
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        access = FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE
        share = 0x1 | 0x2 | 0x4
        handle = kernel32.CreateFileW(
            root_path, access, share, None, OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, None,
        )
        invalid = ctypes.c_void_p(-1).value
        if not handle or int(handle) == invalid:
            error = ctypes.get_last_error()
            raise NativeHandleAclError(f"drive root open failed (WinError {error})")
        root_handle = int(handle)
        objects: list[OpenedObject] = []
        try:
            identity = self.api.query_identity(root_handle)
            if not identity.is_directory or identity.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise NativeHandleAclError("drive root is not a validated non-reparse directory")
            objects.append(OpenedObject(root_handle, identity, f"{drive}:\\"))
            for component in components:
                parent = objects[-1]
                child = self.api.open_child(
                    parent.handle, parent.identity, component, directory=True,
                )
                objects.append(child)
            return OpenedDirectoryChain(self.api, objects)
        except Exception:
            for opened in reversed(objects):
                try:
                    opened.close(self.api.close)
                except Exception:
                    pass
            if not objects:
                self.api.close(root_handle)
            raise

    def enumerate_open_children(
        self, directory: OpenedObject, *, max_entries: int = DEFAULT_MAX_CHILDREN,
    ) -> list[OpenedObject]:
        """Enumerate direct children and retain each verified child handle.

        Uses FileIdExtdDirectoryInfo (128-bit IDs). There is deliberately no
        fallback to the legacy 64-bit directory information class.
        """
        if max_entries < 1:
            raise NativeHandleAclError("max_entries must be positive")
        before = self.api.query_identity(directory.handle)
        if before != directory.identity or not before.is_directory or before.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise NativeHandleAclError("enumeration parent identity is not stable and trusted")
        buffer = ctypes.create_string_buffer(DIRECTORY_BUFFER_SIZE)
        opened_children: list[OpenedObject] = []
        first = True
        total = 0
        seen_names: set[str] = set()
        seen_file_ids: set[str] = set()
        try:
            while True:
                info_class = (
                    FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS if first
                    else FILE_ID_EXTD_DIRECTORY_INFO_CLASS
                )
                first = False
                ok = self.api.kernel32.GetFileInformationByHandleEx(
                    wintypes.HANDLE(directory.handle), info_class,
                    ctypes.byref(buffer), DIRECTORY_BUFFER_SIZE,
                )
                if not ok:
                    error = ctypes.get_last_error()
                    if error == ERROR_NO_MORE_FILES:
                        break
                    raise NativeHandleAclError(
                        f"128-bit handle directory enumeration failed (WinError {error})"
                    )
                records = parse_extended_directory_buffer(
                    buffer.raw, max_entries=max(1, max_entries - total),
                )
                for record in records:
                    if record.name in {".", ".."}:
                        continue
                    validate_relative_component(record.name)
                    folded_name = record.name.casefold()
                    if folded_name in seen_names:
                        raise NativeHandleAclError("directory contains duplicate or case-fold-colliding names")
                    if record.file_id in seen_file_ids:
                        raise NativeHandleAclError("directory contains duplicate file identities or hard-link aliases")
                    seen_names.add(folded_name)
                    seen_file_ids.add(record.file_id)
                    if record.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                        raise NativeHandleAclError(
                            f"directory contains a reparse point: {record.name!r}"
                        )
                    child = self.api.open_child(
                        directory.handle, directory.identity, record.name,
                        directory=record.is_directory,
                    )
                    if (
                        child.identity.file_id != record.file_id
                        or child.identity.volume_serial != directory.identity.volume_serial
                        or child.identity.is_directory != record.is_directory
                        or child.identity.attributes & FILE_ATTRIBUTE_REPARSE_POINT
                    ):
                        child.close(self.api.close)
                        raise NativeHandleAclError(
                            f"enumerated identity does not match opened object: {record.name!r}"
                        )
                    opened_children.append(child)
                    total += 1
                    if total > max_entries:
                        raise NativeHandleAclError("directory entry count exceeds configured resource ceiling")
            after = self.api.query_identity(directory.handle)
            if after != before:
                raise NativeHandleAclError("enumeration parent identity changed during enumeration")
            return opened_children
        except Exception:
            for child in reversed(opened_children):
                try:
                    child.close(self.api.close)
                except Exception:
                    pass
            raise
