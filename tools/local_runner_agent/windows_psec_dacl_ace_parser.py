"""Strict, lossless parser for the supported Windows DACL ACE subset.

The parser never edits ACLs. It preserves each supported ACE byte-for-byte,
rejects unknown ACE layouts, and reports unused ACL allocation separately.
Object-specific and callback ACE layouts are intentionally unsupported until
their SID offsets and trailing application data receive dedicated validation.
"""
from __future__ import annotations

from dataclasses import dataclass


ACL_HEADER_SIZE = 8
ACE_HEADER_SIZE = 4
MAX_ACL_BYTES = 0xFFFF
MAX_ACES = 4096
SUPPORTED_ACE_TYPES = frozenset({0, 1, 2, 3, 17})


class DaclAceParseError(ValueError):
    """An ACL or ACE is malformed or outside the explicitly supported subset."""


@dataclass(frozen=True)
class AceRecord:
    index: int
    ace_type: int
    ace_flags: int
    ace_size: int
    access_mask: int
    sid: str
    raw: bytes


@dataclass(frozen=True)
class ParsedDacl:
    revision: int
    declared_size: int
    ace_count: int
    aces: tuple[AceRecord, ...]
    unused_bytes: bytes


def _sid_text(raw: bytes) -> str:
    if len(raw) < 8:
        raise DaclAceParseError("ACE SID is shorter than the SID header")
    revision = raw[0]
    count = raw[1]
    expected = 8 + count * 4
    if revision != 1 or count > 15 or len(raw) != expected:
        raise DaclAceParseError("ACE SID has an invalid revision, count, or length")
    authority = int.from_bytes(raw[2:8], "big")
    sub_authorities = [
        int.from_bytes(raw[8 + offset * 4:12 + offset * 4], "little")
        for offset in range(count)
    ]
    return "S-" + "-".join(str(value) for value in (revision, authority, *sub_authorities))


def parse_dacl(raw_acl: bytes, *, max_acl_bytes: int = MAX_ACL_BYTES,
               max_aces: int = MAX_ACES) -> ParsedDacl:
    """Parse a bounded ACL, preserving supported ACE bytes exactly.

    The input is the complete ACL allocation: ACL.AclSize must equal len(input).
    Bytes after the declared ACE sequence are retained as unused allocation and
    are not interpreted as ACE data.
    """
    if not isinstance(raw_acl, bytes):
        raise DaclAceParseError("ACL input must be immutable bytes")
    if not isinstance(max_acl_bytes, int) or max_acl_bytes < ACL_HEADER_SIZE:
        raise DaclAceParseError("ACL byte limit is invalid")
    if not isinstance(max_aces, int) or max_aces < 0:
        raise DaclAceParseError("ACE count limit is invalid")
    if len(raw_acl) < ACL_HEADER_SIZE or len(raw_acl) > min(max_acl_bytes, MAX_ACL_BYTES):
        raise DaclAceParseError("ACL allocation is outside the accepted size bounds")

    revision = raw_acl[0]
    declared_size = int.from_bytes(raw_acl[2:4], "little")
    ace_count = int.from_bytes(raw_acl[4:6], "little")
    if revision not in (2, 4):
        raise DaclAceParseError("unsupported ACL revision")
    if declared_size != len(raw_acl):
        raise DaclAceParseError("ACL header size does not match the supplied allocation")
    if ace_count > max_aces:
        raise DaclAceParseError("ACL ACE count exceeds the configured limit")

    cursor = ACL_HEADER_SIZE
    records: list[AceRecord] = []
    for index in range(ace_count):
        if cursor + ACE_HEADER_SIZE > declared_size:
            raise DaclAceParseError("truncated ACE header")
        ace_type = raw_acl[cursor]
        ace_flags = raw_acl[cursor + 1]
        ace_size = int.from_bytes(raw_acl[cursor + 2:cursor + 4], "little")
        if ace_type not in SUPPORTED_ACE_TYPES:
            raise DaclAceParseError(f"unsupported ACE type {ace_type}")
        if ace_size < ACE_HEADER_SIZE + 4 + 8 or ace_size % 4:
            raise DaclAceParseError("ACE size is too small or not DWORD-aligned")
        end = cursor + ace_size
        if end > declared_size:
            raise DaclAceParseError("ACE extends beyond the ACL allocation")

        access_mask = int.from_bytes(raw_acl[cursor + 4:cursor + 8], "little")
        sid_bytes = raw_acl[cursor + 8:end]
        sid = _sid_text(sid_bytes)
        records.append(AceRecord(
            index=index,
            ace_type=ace_type,
            ace_flags=ace_flags,
            ace_size=ace_size,
            access_mask=access_mask,
            sid=sid,
            raw=raw_acl[cursor:end],
        ))
        cursor = end

    return ParsedDacl(
        revision=revision,
        declared_size=declared_size,
        ace_count=ace_count,
        aces=tuple(records),
        unused_bytes=raw_acl[cursor:],
    )
