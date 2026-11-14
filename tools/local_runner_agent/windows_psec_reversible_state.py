"""Immutable original-state preservation and read-back verification for PSEC.

This module is platform-independent and performs no native calls. It binds a
validated DescriptorSnapshot to one transaction and stable object identity,
protects the captured state with a SHA-256 digest, and verifies independently
read-back state under an explicit Protocol v1 comparison profile.

It does not implement SetSecurityInfo or claim that Windows can restore every
descriptor control bit. Native restoration capability remains a separate,
host-tested gate.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Literal

from tools.local_runner_agent.windows_psec_dacl_comparison import (
    DaclComparisonProfile,
    dacl_states_equal,
    resolve_dacl_comparison_profile,
)
from tools.local_runner_agent.windows_psec_security_descriptor_transaction import (
    DescriptorSnapshot,
    TransactionLimits,
)


class ReversibleStateError(ValueError):
    """An original snapshot cannot be safely captured or verified."""


@dataclass(frozen=True)
class TargetObjectIdentity:
    """Stable identity of the object observed through the retained handle."""

    volume_serial: int
    file_id: str

    def validate(self) -> None:
        if (
            isinstance(self.volume_serial, bool)
            or not isinstance(self.volume_serial, int)
            or self.volume_serial < 0
            or self.volume_serial > 0xFFFFFFFFFFFFFFFF
        ):
            raise ReversibleStateError("target volume serial is invalid")
        if not isinstance(self.file_id, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", self.file_id):
            raise ReversibleStateError("target 128-bit file identity is invalid")


@dataclass(frozen=True)
class OriginalDescriptorSnapshot:
    """Immutable S0 bound to its transaction and target object."""

    transaction_id: str
    target_identity: TargetObjectIdentity
    descriptor: DescriptorSnapshot
    integrity_sha256: str

    def verify_integrity(self, *, limits: TransactionLimits | None = None) -> bool:
        selected_limits = limits or TransactionLimits()
        try:
            _validate_transaction_id(self.transaction_id)
            self.target_identity.validate()
            _validate_descriptor(self.descriptor, selected_limits)
            expected = _snapshot_digest(
                self.transaction_id, self.target_identity, self.descriptor
            )
        except (ReversibleStateError, TypeError, ValueError):
            return False
        return (
            isinstance(self.integrity_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", self.integrity_sha256) is not None
            and hmac.compare_digest(expected, self.integrity_sha256)
        )


@dataclass(frozen=True)
class RestorationVerification:
    """Read-back result; success means equality under the chosen profile."""

    state: Literal["RESTORED_EXACT", "RESTORE_NOT_EXACT", "SNAPSHOT_INVALID"]
    profile: str | None
    mismatches: tuple[str, ...] = ()


def _validate_transaction_id(value: object) -> None:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
        value,
    ):
        raise ReversibleStateError("transaction_id must be a canonical UUID")


def _validate_descriptor(
    descriptor: DescriptorSnapshot, limits: TransactionLimits
) -> None:
    if not isinstance(descriptor, DescriptorSnapshot):
        raise ReversibleStateError("original descriptor snapshot has an invalid type")
    descriptor.validate(
        max_descriptor_bytes=limits.max_descriptor_bytes,
        max_aces=limits.max_aces_per_descriptor,
    )


def _snapshot_digest(
    transaction_id: str,
    target_identity: TargetObjectIdentity,
    descriptor: DescriptorSnapshot,
) -> str:
    metadata = {
        "transaction_id": transaction_id,
        "volume_serial": target_identity.volume_serial,
        "file_id": target_identity.file_id.casefold(),
        "dacl_present": descriptor.dacl_present,
        "dacl_is_null": descriptor.dacl_is_null,
        "dacl_defaulted": descriptor.dacl_defaulted,
        "dacl_control_flags": descriptor.dacl_control_flags,
        "descriptor_revision": descriptor.descriptor_revision,
        "acl_revision": descriptor.acl_revision,
        "ace_count": descriptor.ace_count,
        "dacl_bytes_length": len(descriptor.dacl_bytes),
    }
    encoded = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    digest.update(descriptor.dacl_bytes)
    return digest.hexdigest()


def capture_original_snapshot(
    transaction_id: str,
    target_identity: TargetObjectIdentity,
    descriptor: DescriptorSnapshot,
    *,
    limits: TransactionLimits | None = None,
) -> OriginalDescriptorSnapshot:
    """Capture S0 before mutation and return a detached immutable snapshot."""
    selected_limits = limits or TransactionLimits()
    _validate_transaction_id(transaction_id)
    if not isinstance(target_identity, TargetObjectIdentity):
        raise ReversibleStateError("target identity has an invalid type")
    target_identity.validate()
    _validate_descriptor(descriptor, selected_limits)

    detached_descriptor = DescriptorSnapshot(
        dacl_present=descriptor.dacl_present,
        dacl_is_null=descriptor.dacl_is_null,
        dacl_bytes=bytes(descriptor.dacl_bytes),
        dacl_control_flags=descriptor.dacl_control_flags,
        descriptor_revision=descriptor.descriptor_revision,
        acl_revision=descriptor.acl_revision,
        ace_count=descriptor.ace_count,
        dacl_defaulted=descriptor.dacl_defaulted,
    )
    detached_identity = TargetObjectIdentity(
        volume_serial=target_identity.volume_serial,
        file_id=target_identity.file_id.casefold(),
    )
    digest = _snapshot_digest(transaction_id, detached_identity, detached_descriptor)
    return OriginalDescriptorSnapshot(
        transaction_id=transaction_id,
        target_identity=detached_identity,
        descriptor=detached_descriptor,
        integrity_sha256=digest,
    )


def verify_restoration_readback(
    original: OriginalDescriptorSnapshot,
    *,
    transaction_id: str,
    target_identity: TargetObjectIdentity,
    readback: DescriptorSnapshot,
    comparison_profile: DaclComparisonProfile | str,
    limits: TransactionLimits | None = None,
) -> RestorationVerification:
    """Verify S2 against immutable S0; this function never performs a write."""
    selected_limits = limits or TransactionLimits()
    try:
        profile = resolve_dacl_comparison_profile(comparison_profile)
        _validate_transaction_id(transaction_id)
        if not isinstance(original, OriginalDescriptorSnapshot):
            return RestorationVerification(
                "SNAPSHOT_INVALID", profile.value, ("original_snapshot_type_invalid",)
            )
        target_identity.validate()
        if not original.verify_integrity(limits=selected_limits):
            return RestorationVerification(
                "SNAPSHOT_INVALID", profile.value, ("original_snapshot_integrity_invalid",)
            )
        if transaction_id != original.transaction_id:
            return RestorationVerification(
                "RESTORE_NOT_EXACT", profile.value, ("transaction_id_mismatch",)
            )
        normalized_identity = TargetObjectIdentity(
            volume_serial=target_identity.volume_serial,
            file_id=target_identity.file_id.casefold(),
        )
        if normalized_identity != original.target_identity:
            return RestorationVerification(
                "RESTORE_NOT_EXACT", profile.value, ("target_identity_mismatch",)
            )
        _validate_descriptor(readback, selected_limits)
        if not dacl_states_equal(original.descriptor, readback, profile):
            mismatches = []
            if (
                original.descriptor.dacl_present != readback.dacl_present
                or original.descriptor.dacl_is_null != readback.dacl_is_null
                or original.descriptor.dacl_bytes != readback.dacl_bytes
            ):
                mismatches.append("dacl_content_mismatch")
            if original.descriptor.dacl_defaulted != readback.dacl_defaulted:
                mismatches.append("dacl_defaulted_mismatch")
            if original.descriptor.dacl_control_flags != readback.dacl_control_flags:
                mismatches.append("control_flags_mismatch")
            return RestorationVerification(
                "RESTORE_NOT_EXACT", profile.value, tuple(mismatches)
            )
        return RestorationVerification("RESTORED_EXACT", profile.value)
    except (ReversibleStateError, TypeError, ValueError) as exc:
        return RestorationVerification(
            "RESTORE_NOT_EXACT", None, (f"verification_rejected:{exc}",)
        )
