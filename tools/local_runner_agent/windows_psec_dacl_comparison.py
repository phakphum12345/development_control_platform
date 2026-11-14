"""Pure, explicit comparison profiles for Windows DACL descriptor observations.

This module performs no native calls and grants no authority to mutate ACLs.
The caller must choose a profile for each operation; profiles are never
silently downgraded or substituted.
"""
from __future__ import annotations

from enum import Enum
from typing import Protocol


class DaclComparisonProfile(str, Enum):
    """Protocol v1.0 comparison dimensions."""

    DACL_CONTENT_EQUALITY = "DACL_CONTENT_EQUALITY"
    DACL_OBJECT_STATE_EQUALITY = "DACL_OBJECT_STATE_EQUALITY"
    CONTROL_STATE_EQUALITY = "CONTROL_STATE_EQUALITY"
    STRICT_DESCRIPTOR_EQUALITY = "STRICT_DESCRIPTOR_EQUALITY"


class DaclState(Protocol):
    dacl_present: bool
    dacl_is_null: bool
    dacl_bytes: bytes
    dacl_defaulted: bool
    dacl_control_flags: int


def resolve_dacl_comparison_profile(
    profile: DaclComparisonProfile | str | None,
) -> DaclComparisonProfile:
    """Resolve an explicitly supplied profile or reject it without fallback."""
    if isinstance(profile, DaclComparisonProfile):
        return profile
    if isinstance(profile, str):
        try:
            return DaclComparisonProfile(profile)
        except ValueError as exc:
            raise ValueError(f"unknown DACL comparison profile: {profile!r}") from exc
    raise ValueError("an explicit DACL comparison profile is required")


def dacl_states_equal(
    expected: DaclState,
    actual: DaclState,
    profile: DaclComparisonProfile | str,
) -> bool:
    """Compare only the dimensions named by the selected Protocol v1 profile.

    Structural validation is deliberately separate and must be performed on
    both states by the caller before relying on this predicate.
    """
    selected = resolve_dacl_comparison_profile(profile)

    if selected in (
        DaclComparisonProfile.DACL_CONTENT_EQUALITY,
        DaclComparisonProfile.DACL_OBJECT_STATE_EQUALITY,
        DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
    ):
        content_equal = (
            expected.dacl_present == actual.dacl_present
            and expected.dacl_is_null == actual.dacl_is_null
            and expected.dacl_bytes == actual.dacl_bytes
        )
        if not content_equal:
            return False

    if selected in (
        DaclComparisonProfile.DACL_OBJECT_STATE_EQUALITY,
        DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
    ):
        if expected.dacl_defaulted != actual.dacl_defaulted:
            return False

    if selected in (
        DaclComparisonProfile.CONTROL_STATE_EQUALITY,
        DaclComparisonProfile.STRICT_DESCRIPTOR_EQUALITY,
    ):
        if expected.dacl_control_flags != actual.dacl_control_flags:
            return False

    return True
