"""Pure, fail-closed DACL candidate construction for Windows PSEC.

This module operates only on immutable ACL bytes. It does not open handles,
call Win32 APIs, mutate a descriptor, or write filesystem permissions.
Existing supported ACE records are retained byte-for-byte and in their
original relative order. Ambiguous ACE semantics and noncanonical explicit
ordering are rejected rather than silently repaired.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .windows_psec_dacl_ace_parser import (
    DaclAceParseError,
    ParsedDacl,
    parse_dacl,
)

ACL_HEADER_SIZE = 8
MAX_ACL_BYTES = 0xFFFF
MAX_ACES = 4096

ACCESS_ALLOWED_ACE_TYPE = 0
ACCESS_DENIED_ACE_TYPE = 1
INHERITED_ACE = 0x10
OBJECT_INHERIT_ACE = 0x01
CONTAINER_INHERIT_ACE = 0x02

READ_EXECUTE = 0x001200A9
MODIFY = 0x001301BF
FILE_TRAVERSE = 0x00000020

_PACKAGE_SID_RE = re.compile(
    r"^S-1-15-2-(?:0|[1-9][0-9]{0,9})(?:-(?:0|[1-9][0-9]{0,9})){0,14}$",
    re.ASCII,
)


class DaclCandidateBuildError(ValueError):
    """A DACL cannot be transformed without violating the strict policy."""


@dataclass(frozen=True)
class DaclCandidate:
    raw_acl: bytes
    acl_revision: int
    ace_count: int
    package_sid: str
    target_kind: str
    access_mask: int
    inheritance_flags: int
    inserted: bool
    original_ace_count: int


def _valid_package_sid(value: object) -> bool:
    if not isinstance(value, str) or not _PACKAGE_SID_RE.fullmatch(value):
        return False
    try:
        return all(int(part) <= 0xFFFFFFFF for part in value.split("-")[4:])
    except ValueError:
        return False


def _sid_bytes(value: str) -> bytes:
    if not _valid_package_sid(value):
        raise DaclCandidateBuildError("Package SID is invalid")
    parts = [int(part) for part in value.split("-")[1:]]
    revision, authority, *sub_authorities = parts
    if revision != 1 or len(sub_authorities) > 15 or authority > 0xFFFFFFFFFFFF:
        raise DaclCandidateBuildError("Package SID is outside the supported SID bounds")
    return (
        bytes((revision, len(sub_authorities)))
        + authority.to_bytes(6, "big")
        + b"".join(part.to_bytes(4, "little") for part in sub_authorities)
    )


def _policy(target_kind: str, is_directory: bool) -> tuple[int, int]:
    if not isinstance(is_directory, bool):
        raise DaclCandidateBuildError("target object kind must be explicit")
    if target_kind == "workspace":
        return READ_EXECUTE, (
            OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE if is_directory else 0
        )
    if target_kind == "scratch":
        return MODIFY, (
            OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE if is_directory else 0
        )
    if target_kind == "job_root" and is_directory:
        return FILE_TRAVERSE, 0
    raise DaclCandidateBuildError("unsupported target kind/object-kind combination")


def _validate_canonical_order(parsed: ParsedDacl) -> None:
    """Validate a conservative explicit-deny/explicit-allow/inherited ordering."""
    phase = 0  # 0=explicit deny, 1=explicit allow, 2=inherited
    for ace in parsed.aces:
        inherited = bool(ace.ace_flags & INHERITED_ACE)
        if inherited:
            phase = 2
            continue
        if phase == 2:
            raise DaclCandidateBuildError(
                "explicit ACE appears after inherited ACE; refusing to reorder existing ACEs"
            )
        if ace.ace_type == ACCESS_DENIED_ACE_TYPE:
            if phase > 0:
                raise DaclCandidateBuildError(
                    "explicit deny ACE appears after explicit allow ACE"
                )
        elif ace.ace_type == ACCESS_ALLOWED_ACE_TYPE:
            phase = 1
        else:
            raise DaclCandidateBuildError(
                f"ACE type {ace.ace_type} has no approved DACL canonical-order policy"
            )


def _build_allow_ace(package_sid: str, access_mask: int, flags: int) -> bytes:
    sid = _sid_bytes(package_sid)
    size = 8 + len(sid)
    if size > 0xFFFF or size % 4:
        raise DaclCandidateBuildError("generated ACE size is invalid")
    return (
        bytes((ACCESS_ALLOWED_ACE_TYPE, flags))
        + size.to_bytes(2, "little")
        + access_mask.to_bytes(4, "little")
        + sid
    )


def build_dacl_candidate(
    raw_acl: bytes,
    package_sid: str,
    target_kind: str,
    *,
    is_directory: bool,
    dacl_present: bool = True,
    dacl_is_null: bool = False,
    dacl_control_flags: int = 0,
    max_acl_bytes: int = MAX_ACL_BYTES,
    max_aces: int = MAX_ACES,
) -> DaclCandidate:
    """Return a candidate ACL without changing the input or touching the OS.

    Existing ACEs are preserved byte-for-byte. An exact, unique existing
    Package-SID allow ACE makes the operation idempotent. Any other Package-SID
    ACE (deny, inherited, duplicate, overbroad, or wrong inheritance) blocks
    candidate construction. Only supported allow/deny DACL ACE types are
    accepted for canonical-order validation.
    """
    if not dacl_present or dacl_is_null:
        raise DaclCandidateBuildError("absent or NULL DACL is not eligible for candidate construction")
    if not isinstance(dacl_control_flags, int) or dacl_control_flags < 0:
        raise DaclCandidateBuildError("DACL control flags are invalid")
    if not _valid_package_sid(package_sid):
        raise DaclCandidateBuildError("Package SID is invalid")
    access_mask, inheritance_flags = _policy(target_kind, is_directory)

    try:
        parsed = parse_dacl(raw_acl, max_acl_bytes=max_acl_bytes, max_aces=max_aces)
    except DaclAceParseError as exc:
        raise DaclCandidateBuildError(f"source DACL is not safely parseable: {exc}") from exc
    _validate_canonical_order(parsed)

    matching = [ace for ace in parsed.aces if ace.sid.casefold() == package_sid.casefold()]
    if len(matching) > 1:
        raise DaclCandidateBuildError("duplicate Package-SID ACEs are forbidden")
    if matching:
        existing = matching[0]
        if (
            existing.ace_type != ACCESS_ALLOWED_ACE_TYPE
            or existing.access_mask != access_mask
            or existing.ace_flags != inheritance_flags
        ):
            raise DaclCandidateBuildError(
                "existing Package-SID ACE is not the exact policy grant; refusing to broaden or rewrite it"
            )
        return DaclCandidate(
            raw_acl=bytes(raw_acl),
            acl_revision=parsed.revision,
            ace_count=parsed.ace_count,
            package_sid=package_sid,
            target_kind=target_kind,
            access_mask=access_mask,
            inheritance_flags=inheritance_flags,
            inserted=False,
            original_ace_count=parsed.ace_count,
        )

    if parsed.ace_count >= max_aces:
        raise DaclCandidateBuildError("candidate would exceed the configured ACE count ceiling")

    new_ace = _build_allow_ace(package_sid, access_mask, inheritance_flags)
    insertion_index = next(
        (index for index, ace in enumerate(parsed.aces) if ace.ace_flags & INHERITED_ACE),
        parsed.ace_count,
    )
    ace_chunks = [ace.raw for ace in parsed.aces]
    ace_chunks.insert(insertion_index, new_ace)
    body = b"".join(ace_chunks) + parsed.unused_bytes
    new_size = ACL_HEADER_SIZE + len(body)
    if new_size > min(max_acl_bytes, MAX_ACL_BYTES):
        raise DaclCandidateBuildError("candidate ACL exceeds the configured byte ceiling")

    # Retain ACL revision, reserved header bytes and unused allocation bytes.
    header = bytearray(raw_acl[:ACL_HEADER_SIZE])
    header[2:4] = new_size.to_bytes(2, "little")
    header[4:6] = (parsed.ace_count + 1).to_bytes(2, "little")
    candidate_bytes = bytes(header) + body

    try:
        verified = parse_dacl(
            candidate_bytes, max_acl_bytes=max_acl_bytes, max_aces=max_aces
        )
        _validate_canonical_order(verified)
    except DaclAceParseError as exc:
        raise DaclCandidateBuildError(f"constructed candidate failed self-validation: {exc}") from exc
    except DaclCandidateBuildError as exc:
        raise DaclCandidateBuildError(f"constructed candidate failed policy validation: {exc}") from exc

    if verified.aces[insertion_index].raw != new_ace:
        raise DaclCandidateBuildError("generated ACE did not round-trip at the intended insertion point")
    if tuple(ace.raw for ace in verified.aces if ace.raw != new_ace) != tuple(
        ace.raw for ace in parsed.aces
    ):
        raise DaclCandidateBuildError("existing ACE byte sequence changed during candidate construction")

    return DaclCandidate(
        raw_acl=candidate_bytes,
        acl_revision=verified.revision,
        ace_count=verified.ace_count,
        package_sid=package_sid,
        target_kind=target_kind,
        access_mask=access_mask,
        inheritance_flags=inheritance_flags,
        inserted=True,
        original_ace_count=parsed.ace_count,
    )
