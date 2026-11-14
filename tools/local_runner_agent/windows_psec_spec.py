"""Minimal, versioned FlatBuffer builder for Windows PSEC v1.1.

Only the Terminal policy shape is supported: no AppContainer capabilities,
explicit deny-by-default network policy, read-only workspace/runtime paths,
read-write per-job scratch, explicit denied paths, and explicit enumeration.
"""
from __future__ import annotations

import ntpath
from collections.abc import Iterable

import flatbuffers


PSEC_SCHEMA_MAJOR = 1
PSEC_SCHEMA_MINOR = 1
FILTER_ACTION_DENY = 0


class PsecSpecError(ValueError):
    """The requested PSEC policy is invalid or outside the Terminal contract."""


def _normalize_path(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PsecSpecError(f"{label} must be a non-empty path")
    if not ntpath.isabs(value) or value.startswith("\\\\"):
        raise PsecSpecError(f"{label} must be an absolute local drive path")
    drive, _ = ntpath.splitdrive(value)
    if len(drive) != 2 or drive[1] != ":":
        raise PsecSpecError(f"{label} must use a local drive letter")
    if any(part == ".." for part in value.replace("/", "\\").split("\\")):
        raise PsecSpecError(f"{label} must not contain parent traversal")
    normalized = ntpath.normpath(value)
    if normalized in (drive, drive + "\\"):
        raise PsecSpecError(f"{label} cannot be a drive root")
    return normalized


def _normalize_paths(values: Iterable[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PsecSpecError(f"{label} must be a sequence of paths")
    try:
        normalized = tuple(_normalize_path(value, label) for value in values)
    except TypeError:
        raise PsecSpecError(f"{label} must be a sequence of paths") from None
    seen = set()
    result = []
    for value in normalized:
        key = ntpath.normcase(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _is_same_or_child(path: str, parent: str) -> bool:
    child = ntpath.normcase(path)
    base = ntpath.normcase(parent)
    return child == base or child.startswith(base.rstrip("\\") + "\\")


def _string_vector(builder: flatbuffers.Builder, values: tuple[str, ...]) -> int:
    if not values:
        return 0
    offsets = [builder.CreateString(value) for value in values]
    builder.StartVector(4, len(offsets), 4)
    for offset in reversed(offsets):
        builder.PrependUOffsetTRelative(offset)
    return builder.EndVector()


def build_psec_spec(
    *,
    read_only_paths: Iterable[str],
    read_write_paths: Iterable[str],
    denied_paths: Iterable[str] = (),
    enumerate_paths: Iterable[str] = (),
    capabilities: Iterable[str] = (),
    disallow_win32k_system_calls: bool = True,
    ui_restrictions: int = 0,
) -> bytes:
    """Build a PSEC v1.1 FlatBuffer for the fixed read-only Terminal policy."""
    read_only = _normalize_paths(read_only_paths, "read_only_paths")
    read_write = _normalize_paths(read_write_paths, "read_write_paths")
    denied = _normalize_paths(denied_paths, "denied_paths")
    enumerate = _normalize_paths(enumerate_paths, "enumerate_paths")

    if not read_only or not read_write:
        raise PsecSpecError("at least one read-only path and one read-write scratch path are required")
    if tuple(capabilities):
        raise PsecSpecError("Terminal PSEC policy does not permit AppContainer capabilities")
    if not isinstance(disallow_win32k_system_calls, bool):
        raise PsecSpecError("disallow_win32k_system_calls must be boolean")
    if (isinstance(ui_restrictions, bool) or not isinstance(ui_restrictions, int)
            or not 0 <= ui_restrictions <= 0xFFFFFFFFFFFFFFFF):
        raise PsecSpecError("ui_restrictions must be an unsigned 64-bit integer")

    for read_path in read_only:
        for write_path in read_write:
            if _is_same_or_child(read_path, write_path) or _is_same_or_child(write_path, read_path):
                raise PsecSpecError("read-only workspace/runtime paths and writable scratch must be separate")
    allowed = read_only + read_write
    for deny_path in denied:
        if any(ntpath.normcase(deny_path) == ntpath.normcase(path) for path in allowed):
            raise PsecSpecError("a path cannot be both explicitly allowed and denied")
    for enum_path in enumerate:
        if not any(_is_same_or_child(enum_path, allowed_path) for allowed_path in allowed):
            raise PsecSpecError("enumeration paths must be inside an explicitly allowed path")

    builder = flatbuffers.Builder(1024)

    # NetworkPolicy: explicit deny for egress, ingress, and host loopback.
    builder.StartObject(3)
    builder.PrependUint8Slot(0, FILTER_ACTION_DENY, 1)
    egress = builder.EndObject()

    builder.StartObject(2)
    builder.PrependUint8Slot(0, FILTER_ACTION_DENY, 1)
    builder.PrependUint8Slot(1, FILTER_ACTION_DENY, 1)
    ingress = builder.EndObject()

    builder.StartObject(4)
    builder.PrependUOffsetTRelativeSlot(3, ingress, 0)
    builder.PrependUOffsetTRelativeSlot(1, egress, 0)
    network_policy = builder.EndObject()

    read_write_vector = _string_vector(builder, read_write)
    read_only_vector = _string_vector(builder, read_only)
    denied_vector = _string_vector(builder, denied)
    enumerate_vector = _string_vector(builder, enumerate)
    capabilities_string = builder.CreateString("")

    builder.StartObject(9)
    if enumerate_vector:
        builder.PrependUOffsetTRelativeSlot(8, enumerate_vector, 0)
    builder.PrependUOffsetTRelativeSlot(7, network_policy, 0)
    if denied_vector:
        builder.PrependUOffsetTRelativeSlot(6, denied_vector, 0)
    builder.PrependUOffsetTRelativeSlot(5, read_only_vector, 0)
    builder.PrependUOffsetTRelativeSlot(4, read_write_vector, 0)
    builder.PrependUint64Slot(3, ui_restrictions, 0)
    builder.PrependBoolSlot(2, disallow_win32k_system_calls, False)
    builder.PrependUOffsetTRelativeSlot(1, capabilities_string, 0)
    # FlatBuffers structs must be built immediately before their table slot.
    builder.Prep(4, 4)
    builder.PrependUint16(PSEC_SCHEMA_MINOR)
    builder.PrependUint16(PSEC_SCHEMA_MAJOR)
    version_struct = builder.Offset()
    builder.PrependStructSlot(0, version_struct, 0)
    root = builder.EndObject()
    builder.Finish(root, file_identifier=b"PSEC")
    return bytes(builder.Output())
