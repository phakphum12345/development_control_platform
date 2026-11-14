"""Protocol v1 numeric adapter for the four existing DACL comparison profiles.

The numeric IDs are a stable adapter vocabulary, not additional profiles.
Square-root and normalized values are diagnostic transforms only. Resolution
always returns one of the existing Protocol v1 enum members; transformed
Decimals are never used to choose or weaken a comparator profile.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from tools.local_runner_agent.windows_psec_dacl_comparison import (
    DaclComparisonProfile,
    resolve_dacl_comparison_profile,
)


# Stable adapter IDs for the four existing Protocol v1 profiles.
# Do not reorder or reuse these values.
_PROFILE_BY_LEVEL: dict[int, DaclComparisonProfile] = {
    0: DaclComparisonProfile.DACL_CONTENT_EQUALITY,
    1: DaclComparisonProfile.DACL_OBJECT_STATE_EQUALITY,
    2: DaclComparisonProfile.CONTROL_STATE_EQUALITY,
    3: DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
}
_DECIMAL_PRECISION = 50
_ROUND_TRIP_TOLERANCE = Decimal("1e-45")


@dataclass(frozen=True)
class EncodedComparisonLevel:
    """A validated diagnostic representation tied to its original integer ID."""

    level_id: int
    square_root: Decimal
    normalized: Decimal


def encode_comparison_level(level_id: int) -> EncodedComparisonLevel:
    """Encode an existing profile ID for diagnostics without changing its identity."""
    if type(level_id) is not int or level_id not in _PROFILE_BY_LEVEL:
        raise ValueError("comparison level must be an integer from 0 through 3")

    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        value = Decimal(level_id)
        return EncodedComparisonLevel(
            level_id=level_id,
            square_root=value.sqrt(),
            normalized=value / Decimal(3),
        )


def decode_comparison_level(
    encoded: EncodedComparisonLevel,
) -> DaclComparisonProfile:
    """Validate the complete encoding and resolve only its original profile ID.

    This deliberately does not infer an ID by rounding a transformed float or
    Decimal. The original integer ID is checked against a recomputed encoding.
    """
    if not isinstance(encoded, EncodedComparisonLevel):
        raise ValueError("a typed encoded comparison level is required")

    expected = encode_comparison_level(encoded.level_id)
    if (
        type(encoded.level_id) is not int
        or encoded.square_root != expected.square_root
        or encoded.normalized != expected.normalized
    ):
        raise ValueError("encoded comparison level failed integrity validation")

    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        reconstructed = encoded.square_root * encoded.square_root
        original = Decimal(encoded.level_id)
        if abs(reconstructed - original) > _ROUND_TRIP_TOLERANCE:
            raise ValueError("square-root round-trip validation failed")

    return _PROFILE_BY_LEVEL[encoded.level_id]


def resolve_comparison_level(level_id: int) -> DaclComparisonProfile:
    """Resolve an exact integer adapter ID to an existing Protocol v1 profile."""
    if type(level_id) is not int or level_id not in _PROFILE_BY_LEVEL:
        raise ValueError("comparison level must be an integer from 0 through 3")
    return resolve_dacl_comparison_profile(_PROFILE_BY_LEVEL[level_id])


def comparison_level_diagnostics(level_id: int) -> dict[str, str | int]:
    """Return exact diagnostic strings; never use them as comparator inputs."""
    encoded = encode_comparison_level(level_id)
    return {
        "level_id": encoded.level_id,
        "square_root": str(encoded.square_root),
        "square": str(encoded.square_root * encoded.square_root),
        "normalized": str(encoded.normalized),
    }
