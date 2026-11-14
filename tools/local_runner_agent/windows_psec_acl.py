"""Narrow Package-SID DACL grants for disposable Windows PSEC job roots.

This module deliberately does not grant access to the job-root parent, source
Workspace, user profile, or shared directories. It is a candidate ACL manager:
the path-based walk is not a substitute for native handle-relative traversal,
and launcher integration remains gated on target-host acceptance.
"""
from __future__ import annotations

import ctypes
import os
import re
import stat
from ctypes import wintypes
from pathlib import Path


READ_EXECUTE = 0x001200A9
MODIFY = 0x001301BF
FILE_TRAVERSE = 0x00000020

SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x00000004
GRANT_ACCESS = 1
OBJECT_INHERIT_ACE = 0x01
CONTAINER_INHERIT_ACE = 0x02
TRUSTEE_IS_SID = 0
TRUSTEE_IS_UNKNOWN = 0
SDDL_REVISION_1 = 1
ERROR_SUCCESS = 0

_SID_RE = re.compile(r"^S-1-15-2-(?:0|[1-9][0-9]{0,9})(?:-(?:0|[1-9][0-9]{0,9})){0,14}$", re.ASCII)
_ACE_RE = re.compile(
    r"\((A|D);([^;]*);(0x[0-9a-fA-F]+|[0-9a-fA-F]+);;;([^)]*)\)"
)


class WindowsPsecAclError(RuntimeError):
    """A Package-SID ACL could not be safely applied or verified."""


class TRUSTEE_W(ctypes.Structure):
    _fields_ = [
        ("pMultipleTrustee", wintypes.LPVOID),
        ("MultipleTrusteeOperation", wintypes.DWORD),
        ("TrusteeForm", wintypes.DWORD),
        ("TrusteeType", wintypes.DWORD),
        ("ptstrName", wintypes.LPVOID),
    ]


class EXPLICIT_ACCESS_W(ctypes.Structure):
    _fields_ = [
        ("grfAccessPermissions", wintypes.DWORD),
        ("grfAccessMode", wintypes.DWORD),
        ("grfInheritance", wintypes.DWORD),
        ("Trustee", TRUSTEE_W),
    ]


def _valid_package_sid(value: object) -> bool:
    if not isinstance(value, str) or not _SID_RE.fullmatch(value):
        return False
    try:
        return all(int(part) <= 0xFFFFFFFF for part in value.split("-")[4:])
    except ValueError:
        return False


def _is_reparse(path: Path, info: os.stat_result | None = None) -> bool:
    info = info or path.lstat()
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(
        stat.S_ISLNK(info.st_mode)
        or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        or (hasattr(path, "is_junction") and path.is_junction())
    )


def _tree_targets(root: Path) -> list[tuple[Path, bool]]:
    """Return (path, is_directory) without following links or reparse points."""
    targets: list[tuple[Path, bool]] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            info = directory.lstat()
        except OSError as exc:
            raise WindowsPsecAclError("private ACL target cannot be inspected") from exc
        if _is_reparse(directory, info) or not stat.S_ISDIR(info.st_mode):
            raise WindowsPsecAclError("private ACL target is not a regular directory")
        targets.append((directory, True))
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise WindowsPsecAclError("private ACL target cannot be enumerated") from exc
        names: set[str] = set()
        for entry in entries:
            folded = entry.name.casefold()
            if folded in names:
                raise WindowsPsecAclError("private ACL target has a case-insensitive collision")
            names.add(folded)
            child = Path(entry.path)
            try:
                child_info = child.lstat()
            except OSError as exc:
                raise WindowsPsecAclError("private ACL child cannot be inspected") from exc
            if _is_reparse(child, child_info):
                raise WindowsPsecAclError("private ACL target contains a reparse point")
            if stat.S_ISDIR(child_info.st_mode):
                stack.append(child)
            elif stat.S_ISREG(child_info.st_mode):
                targets.append((child, False))
            else:
                raise WindowsPsecAclError("private ACL target contains an unsupported object")
    return targets


def _validate_private_roots(workspace: str | os.PathLike, scratch: str | os.PathLike):
    paths = []
    for value, label in ((workspace, "projected Workspace"), (scratch, "private Scratch")):
        raw = Path(value)
        if not raw.is_absolute():
            raise WindowsPsecAclError(f"{label} must be an absolute path")
        try:
            resolved = raw.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise WindowsPsecAclError(f"{label} is unavailable") from exc
        if resolved != raw or not resolved.is_dir() or _is_reparse(resolved):
            raise WindowsPsecAclError(f"{label} must be a canonical, non-reparse directory")
        paths.append(resolved)
    work, temp = paths
    if work == temp or work in temp.parents or temp in work.parents:
        raise WindowsPsecAclError("projected Workspace and private Scratch must be disjoint")
    if work.parent != temp.parent or not work.parent.name.casefold().startswith("dcp-psec-job-"):
        raise WindowsPsecAclError(
            "ACL targets must be sibling workspace/scratch directories under a dcp-psec-job-* root"
        )
    if work.name.casefold() != "workspace" or temp.name.casefold() != "scratch":
        raise WindowsPsecAclError("ACL target directory names are not the expected private job layout")
    return work, temp, work.parent


def _parse_allow_aces(sddl: str, package_sid: str) -> list[tuple[str, int]]:
    matches = []
    for ace_type, flags, mask_text, sid in _ACE_RE.findall(sddl):
        if sid.casefold() != package_sid.casefold():
            continue
        mask = int(mask_text, 16)
        if ace_type == "A":
            matches.append((flags, mask))
    return matches


class _WindowsAclApi:
    """Small Win32 ACL adapter. All returned LocalAlloc memory is freed."""

    def __init__(self):
        if os.name != "nt":
            raise WindowsPsecAclError("Windows Package-SID ACLs are available only on Windows")
        self.advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        a = self.advapi32
        a.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPVOID)]
        a.ConvertStringSidToSidW.restype = wintypes.BOOL
        a.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(wintypes.LPVOID),
        ]
        a.GetNamedSecurityInfoW.restype = wintypes.DWORD
        a.SetEntriesInAclW.argtypes = [
            wintypes.ULONG, ctypes.POINTER(EXPLICIT_ACCESS_W), wintypes.LPVOID,
            ctypes.POINTER(wintypes.LPVOID),
        ]
        a.SetEntriesInAclW.restype = wintypes.DWORD
        a.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
        ]
        a.SetNamedSecurityInfoW.restype = wintypes.DWORD
        a.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(wintypes.DWORD),
        ]
        a.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
        self.kernel32.LocalFree.argtypes = [wintypes.LPVOID]
        self.kernel32.LocalFree.restype = wintypes.LPVOID

    def _sddl_from_path(self, path: Path) -> str:
        owner = wintypes.LPVOID()
        group = wintypes.LPVOID()
        dacl = wintypes.LPVOID()
        sacl = wintypes.LPVOID()
        descriptor = wintypes.LPVOID()
        result = self.advapi32.GetNamedSecurityInfoW(
            str(path), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
            ctypes.byref(owner), ctypes.byref(group), ctypes.byref(dacl),
            ctypes.byref(sacl), ctypes.byref(descriptor),
        )
        if result != ERROR_SUCCESS:
            raise WindowsPsecAclError(f"GetNamedSecurityInfoW failed ({result})")
        rendered = wintypes.LPWSTR()
        try:
            if not self.advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                descriptor, SDDL_REVISION_1, DACL_SECURITY_INFORMATION,
                ctypes.byref(rendered), None,
            ):
                raise WindowsPsecAclError(
                    f"ConvertSecurityDescriptorToStringSecurityDescriptorW failed ({ctypes.get_last_error()})"
                )
            return rendered.value or ""
        finally:
            if rendered:
                self.kernel32.LocalFree(rendered)
            if descriptor:
                self.kernel32.LocalFree(descriptor)

    def read_sddl(self, path: Path) -> str:
        return self._sddl_from_path(path)

    def add_allow_ace(self, path: Path, package_sid: str, mask: int, inheritance: int) -> None:
        sid = wintypes.LPVOID()
        old_descriptor = wintypes.LPVOID()
        old_owner = wintypes.LPVOID()
        old_group = wintypes.LPVOID()
        old_dacl = wintypes.LPVOID()
        old_sacl = wintypes.LPVOID()
        new_acl = wintypes.LPVOID()
        try:
            if not self.advapi32.ConvertStringSidToSidW(package_sid, ctypes.byref(sid)):
                raise WindowsPsecAclError(
                    f"ConvertStringSidToSidW failed ({ctypes.get_last_error()})"
                )
            result = self.advapi32.GetNamedSecurityInfoW(
                str(path), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
                ctypes.byref(old_owner), ctypes.byref(old_group),
                ctypes.byref(old_dacl), ctypes.byref(old_sacl),
                ctypes.byref(old_descriptor),
            )
            if result != ERROR_SUCCESS:
                raise WindowsPsecAclError(f"GetNamedSecurityInfoW failed ({result})")
            entry = EXPLICIT_ACCESS_W()
            entry.grfAccessPermissions = mask
            entry.grfAccessMode = GRANT_ACCESS
            entry.grfInheritance = inheritance
            entry.Trustee = TRUSTEE_W(None, 0, TRUSTEE_IS_SID, TRUSTEE_IS_UNKNOWN, sid)
            result = self.advapi32.SetEntriesInAclW(
                1, ctypes.byref(entry), old_dacl, ctypes.byref(new_acl)
            )
            if result != ERROR_SUCCESS:
                raise WindowsPsecAclError(f"SetEntriesInAclW failed ({result})")
            result = self.advapi32.SetNamedSecurityInfoW(
                str(path), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
                None, None, new_acl, None,
            )
            if result != ERROR_SUCCESS:
                raise WindowsPsecAclError(f"SetNamedSecurityInfoW failed ({result})")
        finally:
            for pointer in (new_acl, old_descriptor, sid):
                if pointer:
                    self.kernel32.LocalFree(pointer)


class WindowsPsecAclManager:
    """Apply and verify exact Package-SID grants on a disposable job tree only."""

    def __init__(self, api=None):
        self._api = api

    def apply(self, workspace: str | os.PathLike, scratch: str | os.PathLike,
              package_sid: str) -> dict:
        if not _valid_package_sid(package_sid):
            raise WindowsPsecAclError("AppContainer Package SID is invalid")
        work, temp, job_root = _validate_private_roots(workspace, scratch)
        api = self._api or _WindowsAclApi()

        # Complete all filesystem preflight before the first DACL mutation.
        # A rejected reparse point must not leave even the private job root
        # partially modified.
        workspace_targets = _tree_targets(work)
        scratch_targets = _tree_targets(temp)
        targets = [
            *((path, READ_EXECUTE, is_directory) for path, is_directory in workspace_targets),
            *((path, MODIFY, is_directory) for path, is_directory in scratch_targets),
        ]

        # The job root is itself disposable and receives traversal only. Its
        # parent is snapshotted but never modified (it may be a shared runner
        # or acceptance directory).
        shared_parent_before = api.read_sddl(job_root.parent)
        api.add_allow_ace(job_root, package_sid, FILE_TRAVERSE, 0)
        root_sddl = api.read_sddl(job_root)
        root_aces = _parse_allow_aces(root_sddl, package_sid)
        if ("", FILE_TRAVERSE) not in root_aces:
            raise WindowsPsecAclError(
                "Package-SID traversal ACE verification failed on job root; "
                f"parsed_aces={root_aces!r}; root_sddl={root_sddl!r}"
            )
        if any(mask & ~FILE_TRAVERSE for _, mask in root_aces):
            raise WindowsPsecAclError("Package SID has an overbroad allow ACE on job root")

        for path, mask, is_directory in targets:
            inheritance = (OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE) if is_directory else 0
            api.add_allow_ace(path, package_sid, mask, inheritance)

        verified = []
        for path, mask, is_directory in targets:
            sddl = api.read_sddl(path)
            aces = _parse_allow_aces(sddl, package_sid)
            required_flags = {"OI", "CI"} if is_directory else set()
            matching = [
                (flags, granted) for flags, granted in aces
                if granted == mask and required_flags.issubset(
                    {flags[index:index + 2] for index in range(0, len(flags), 2)}
                )
            ]
            if not matching:
                raise WindowsPsecAclError(f"Package-SID ACE verification failed for {path.name}")
            if any(granted & ~mask for _, granted in aces):
                raise WindowsPsecAclError(f"Package SID has an overbroad allow ACE on {path.name}")
            verified.append({"path": str(path), "mask": f"0x{mask:08x}", "sddl": sddl})

        shared_parent_after = api.read_sddl(job_root.parent)
        if shared_parent_before != shared_parent_after:
            raise WindowsPsecAclError("shared parent DACL changed during ACL application")
        return {
            "state": "VERIFIED",
            "package_sid": package_sid,
            "workspace_targets": sum(1 for path, mask, is_directory in targets if mask == READ_EXECUTE),
            "scratch_targets": sum(1 for path, mask, is_directory in targets if mask == MODIFY),
            "job_root_traverse_only": True,
            "shared_parent_sddl_unchanged": True,
            "targets": verified,
        }
