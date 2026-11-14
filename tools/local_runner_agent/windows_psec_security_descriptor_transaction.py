"""Fail-closed DACL transaction coordinator for retained Windows handles.

This module is an orchestration/contract layer. It never resolves paths and
contains no Win32 mutation implementation. A platform adapter must operate on
the exact retained handle supplied by the handle-tree layer and must preserve
native API errors. The caller owns all handles for the full transaction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, Sequence


_PACKAGE_SID_RE = re.compile(
    r"^S-1-15-2-(?:0|[1-9][0-9]{0,9})(?:-(?:0|[1-9][0-9]{0,9})){0,14}$",
    re.ASCII,
)
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400


class NativeSecurityDescriptorTransactionError(RuntimeError):
    """A DACL transaction could not be proven safe."""


@dataclass(frozen=True)
class DescriptorSnapshot:
    """Lossless DACL state required to verify or restore one object."""

    dacl_present: bool
    dacl_is_null: bool
    dacl_bytes: bytes
    dacl_control_flags: int
    descriptor_revision: int = 1
    acl_revision: int = 0
    ace_count: int = 0

    def validate(self, *, max_descriptor_bytes: int, max_aces: int) -> None:
        if not isinstance(self.dacl_present, bool) or not isinstance(self.dacl_is_null, bool):
            raise NativeSecurityDescriptorTransactionError("DACL presence state is malformed")
        if not isinstance(self.dacl_bytes, bytes):
            raise NativeSecurityDescriptorTransactionError("DACL snapshot must contain immutable bytes")
        if len(self.dacl_bytes) > max_descriptor_bytes:
            raise NativeSecurityDescriptorTransactionError("DACL snapshot exceeds byte ceiling")
        if self.dacl_is_null:
            if self.dacl_bytes:
                raise NativeSecurityDescriptorTransactionError("NULL DACL must not carry ACL bytes")
        else:
            if not self.dacl_present:
                raise NativeSecurityDescriptorTransactionError("non-NULL DACL is not marked present")
            if len(self.dacl_bytes) < 8:
                raise NativeSecurityDescriptorTransactionError("ACL snapshot is shorter than an ACL header")
            if self.acl_revision not in (2, 4):
                raise NativeSecurityDescriptorTransactionError("unsupported ACL revision")
        if self.descriptor_revision != 1:
            raise NativeSecurityDescriptorTransactionError("unsupported security descriptor revision")
        if not isinstance(self.dacl_control_flags, int) or self.dacl_control_flags < 0:
            raise NativeSecurityDescriptorTransactionError("DACL control flags are malformed")
        if not isinstance(self.ace_count, int) or self.ace_count < 0 or self.ace_count > max_aces:
            raise NativeSecurityDescriptorTransactionError("ACE count exceeds configured ceiling")


@dataclass(frozen=True)
class DescriptorCandidate:
    """Fully constructed DACL state; construction is delegated to a strict adapter."""

    dacl_present: bool
    dacl_is_null: bool
    dacl_bytes: bytes
    dacl_control_flags: int
    descriptor_revision: int = 1
    acl_revision: int = 2
    ace_count: int = 0

    def validate(self, *, max_descriptor_bytes: int, max_aces: int) -> None:
        DescriptorSnapshot(
            dacl_present=self.dacl_present,
            dacl_is_null=self.dacl_is_null,
            dacl_bytes=self.dacl_bytes,
            dacl_control_flags=self.dacl_control_flags,
            descriptor_revision=self.descriptor_revision,
            acl_revision=self.acl_revision,
            ace_count=self.ace_count,
        ).validate(max_descriptor_bytes=max_descriptor_bytes, max_aces=max_aces)
        if not self.dacl_present or self.dacl_is_null:
            raise NativeSecurityDescriptorTransactionError(
                "Package-SID candidate must contain an explicit, non-NULL DACL"
            )

    def as_snapshot(self) -> DescriptorSnapshot:
        return DescriptorSnapshot(
            dacl_present=self.dacl_present,
            dacl_is_null=self.dacl_is_null,
            dacl_bytes=self.dacl_bytes,
            dacl_control_flags=self.dacl_control_flags,
            descriptor_revision=self.descriptor_revision,
            acl_revision=self.acl_revision,
            ace_count=self.ace_count,
        )


@dataclass(frozen=True)
class TransactionTarget:
    """One already-opened object; target_id is diagnostic, never a path."""

    target_id: str
    handle: int
    identity: object
    access_mask: int
    inheritance_flags: int = 0


@dataclass(frozen=True)
class TransactionLimits:
    max_targets: int = 10000
    max_descriptor_bytes: int = 1024 * 1024
    max_aces_per_descriptor: int = 4096
    max_journal_bytes: int = 64 * 1024 * 1024


@dataclass(frozen=True)
class TransactionResult:
    state: str
    attempted_targets: int
    verified_targets: int
    error: str | None = None
    rollback_errors: tuple[str, ...] = ()


class HandleSecurityApi(Protocol):
    """Adapter contract. Every method must use the supplied retained handle."""

    def query_identity(self, handle: int) -> object: ...
    def read_dacl(self, handle: int) -> DescriptorSnapshot: ...
    def build_candidate(
        self, snapshot: DescriptorSnapshot, target: TransactionTarget, package_sid: str
    ) -> DescriptorCandidate: ...
    def write_dacl(self, handle: int, state: DescriptorSnapshot | DescriptorCandidate) -> None: ...


def _valid_package_sid(value: object) -> bool:
    if not isinstance(value, str) or not _PACKAGE_SID_RE.fullmatch(value):
        return False
    try:
        return all(int(part) <= 0xFFFFFFFF for part in value.split("-")[4:])
    except ValueError:
        return False


def _handle_value(handle: object) -> int:
    try:
        value = int(handle)
    except (TypeError, ValueError, OverflowError) as exc:
        raise NativeSecurityDescriptorTransactionError("target handle is not an integer handle") from exc
    if value <= 0 or value == (1 << (8 * 8)) - 1:
        raise NativeSecurityDescriptorTransactionError("target handle is invalid")
    return value


def _validate_target(target: TransactionTarget) -> None:
    if not isinstance(target.target_id, str) or not target.target_id or len(target.target_id) > 128:
        raise NativeSecurityDescriptorTransactionError("target identifier is invalid")
    _handle_value(target.handle)
    identity = target.identity
    if not all(hasattr(identity, field) for field in (
        "volume_serial", "file_id", "is_directory", "attributes", "reparse_tag"
    )):
        raise NativeSecurityDescriptorTransactionError("target identity is incomplete")
    if not isinstance(identity.volume_serial, int) or identity.volume_serial < 0:
        raise NativeSecurityDescriptorTransactionError("target volume identity is invalid")
    if not isinstance(identity.file_id, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", identity.file_id):
        raise NativeSecurityDescriptorTransactionError("target 128-bit file identity is invalid")
    if not isinstance(identity.is_directory, bool):
        raise NativeSecurityDescriptorTransactionError("target object type is invalid")
    if identity.attributes & FILE_ATTRIBUTE_REPARSE_POINT:
        raise NativeSecurityDescriptorTransactionError("reparse-point targets are forbidden")
    if not isinstance(target.access_mask, int) or target.access_mask <= 0 or target.access_mask > 0xFFFFFFFF:
        raise NativeSecurityDescriptorTransactionError("target access mask is invalid")
    if not isinstance(target.inheritance_flags, int) or target.inheritance_flags < 0:
        raise NativeSecurityDescriptorTransactionError("target inheritance flags are invalid")


class NativeSecurityDescriptorTransaction:
    """Preflight, apply, read-back, and reverse-order rollback coordinator."""

    def __init__(self, api: HandleSecurityApi, limits: TransactionLimits | None = None):
        self._api = api
        self._limits = limits or TransactionLimits()

    def apply(
        self, targets: Sequence[TransactionTarget], package_sid: str
    ) -> TransactionResult:
        if not _valid_package_sid(package_sid):
            return TransactionResult("PREFLIGHT_REJECTED_BLOCKED", 0, 0, "invalid Package SID")
        if not targets or len(targets) > self._limits.max_targets:
            return TransactionResult(
                "PREFLIGHT_REJECTED_BLOCKED", 0, 0, "target count is empty or exceeds configured ceiling"
            )

        # Phase A: all reads, identity checks, parsing and candidate construction
        # complete before the first write.
        planned: list[tuple[TransactionTarget, DescriptorSnapshot, DescriptorCandidate]] = []
        handles: set[int] = set()
        identities: set[tuple[int, str]] = set()
        journal_bytes = 0
        try:
            for target in targets:
                _validate_target(target)
                handle = _handle_value(target.handle)
                identity_key = (target.identity.volume_serial, target.identity.file_id.casefold())
                if handle in handles or identity_key in identities:
                    raise NativeSecurityDescriptorTransactionError(
                        "duplicate handle or duplicate file identity in transaction manifest"
                    )
                handles.add(handle)
                identities.add(identity_key)
                actual_identity = self._api.query_identity(handle)
                if actual_identity != target.identity:
                    raise NativeSecurityDescriptorTransactionError(
                        f"identity mismatch during preflight for {target.target_id}"
                    )
                if (
                    not actual_identity.is_directory
                    and actual_identity.attributes & FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    raise NativeSecurityDescriptorTransactionError(
                        f"unsafe object attributes for {target.target_id}"
                    )
                snapshot = self._api.read_dacl(handle)
                if not isinstance(snapshot, DescriptorSnapshot):
                    raise NativeSecurityDescriptorTransactionError("adapter returned an invalid DACL snapshot")
                snapshot.validate(
                    max_descriptor_bytes=self._limits.max_descriptor_bytes,
                    max_aces=self._limits.max_aces_per_descriptor,
                )
                candidate = self._api.build_candidate(snapshot, target, package_sid)
                if not isinstance(candidate, DescriptorCandidate):
                    raise NativeSecurityDescriptorTransactionError("adapter returned an invalid DACL candidate")
                candidate.validate(
                    max_descriptor_bytes=self._limits.max_descriptor_bytes,
                    max_aces=self._limits.max_aces_per_descriptor,
                )
                journal_bytes += len(snapshot.dacl_bytes) + len(candidate.dacl_bytes)
                if journal_bytes > self._limits.max_journal_bytes:
                    raise NativeSecurityDescriptorTransactionError("transaction journal exceeds memory ceiling")
                planned.append((target, snapshot, candidate))
        except Exception as exc:
            return TransactionResult("PREFLIGHT_REJECTED_BLOCKED", 0, 0, str(exc))

        # Phase B: journal BEFORE each native write. A failed call may have
        # changed the descriptor despite returning an error, so that target
        # must also be restored.
        attempted: list[tuple[TransactionTarget, DescriptorSnapshot]] = []
        verified = 0
        apply_error: str | None = None
        for target, snapshot, candidate in planned:
            handle = _handle_value(target.handle)
            try:
                if self._api.query_identity(handle) != target.identity:
                    raise NativeSecurityDescriptorTransactionError(
                        f"identity mismatch immediately before mutation for {target.target_id}"
                    )
                attempted.append((target, snapshot))
                self._api.write_dacl(handle, candidate)
                read_back = self._api.read_dacl(handle)
                if read_back != candidate.as_snapshot():
                    raise NativeSecurityDescriptorTransactionError(
                        f"DACL read-back mismatch for {target.target_id}"
                    )
                verified += 1
            except Exception as exc:
                apply_error = f"{target.target_id}: {exc}"
                break

        if apply_error is None:
            return TransactionResult("APPLIED_VERIFIED", len(attempted), verified)

        # Phase C: restore every attempted target in reverse order. Continue
        # after errors so one failure cannot prevent other restorations.
        rollback_errors: list[str] = []
        for target, snapshot in reversed(attempted):
            handle = _handle_value(target.handle)
            try:
                if self._api.query_identity(handle) != target.identity:
                    raise NativeSecurityDescriptorTransactionError("identity changed before rollback")
                self._api.write_dacl(handle, snapshot)
                restored = self._api.read_dacl(handle)
                if restored != snapshot:
                    raise NativeSecurityDescriptorTransactionError("rollback read-back mismatch")
            except Exception as exc:
                rollback_errors.append(f"{target.target_id}: {exc}")

        state = "ROLLBACK_INCOMPLETE_BLOCKED" if rollback_errors else "ROLLED_BACK_VERIFIED"
        return TransactionResult(
            state,
            len(attempted),
            verified,
            error=apply_error,
            rollback_errors=tuple(rollback_errors),
        )
