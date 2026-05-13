# @tear: 3
"""Tests for the two pure rule functions."""

from __future__ import annotations

import pytest

from tears.config import TearsConfig
from tears.rules import can_import, check_directory_requirement

DEFAULT_4_TIER = TearsConfig().resolved_import_rules()
RESOLVED_6_TIER = TearsConfig(max_tear=5).resolved_import_rules()
RESOLVED_2_TIER = TearsConfig(max_tear=1).resolved_import_rules()


@pytest.mark.parametrize(
    "importer, target, allowed",
    [
        (0, 0, True),
        (0, 1, False),
        (0, 2, False),
        (0, 3, False),
        (1, 0, True),
        (1, 1, True),
        (1, 2, False),
        (1, 3, False),
        (2, 0, True),
        (2, 1, True),
        (2, 2, True),
        (2, 3, False),
        (3, 0, True),
        (3, 1, True),
        (3, 2, True),
        (3, 3, True),
    ],
)
def test_default_matrix(importer: int, target: int, allowed: bool) -> None:
    assert can_import(importer, target, DEFAULT_4_TIER) is allowed


def test_six_tier_system() -> None:
    assert can_import(4, 5, RESOLVED_6_TIER) is False
    assert can_import(5, 4, RESOLVED_6_TIER) is True
    assert can_import(0, 5, RESOLVED_6_TIER) is False


def test_two_tier_system() -> None:
    assert can_import(0, 1, RESOLVED_2_TIER) is False
    assert can_import(1, 0, RESOLVED_2_TIER) is True


# Custom rules — verified through resolved form.
# import_rules maps each tier to the maximum tier it may import from.
# The resolved frozenset is always a contiguous range [0..max].

RELAXED = TearsConfig(import_rules={1: 2}).resolved_import_rules()
RELAXED_TIER0 = TearsConfig(import_rules={0: 1}).resolved_import_rules()
RESTRICTED = TearsConfig(import_rules={2: 1}).resolved_import_rules()


def test_relaxed_rules() -> None:
    assert can_import(1, 2, RELAXED) is True   # max raised to 2
    assert can_import(1, 3, RELAXED) is False  # still blocked above max
    assert can_import(0, 2, RELAXED) is False  # tier 0 unaffected (default max=0)
    assert can_import(0, 1, RELAXED) is False


def test_relaxed_tier0_rules() -> None:
    assert can_import(0, 1, RELAXED_TIER0) is True   # max raised to 1
    assert can_import(0, 2, RELAXED_TIER0) is False  # still blocked above max
    assert can_import(1, 2, RELAXED_TIER0) is False  # tier 1 unaffected (default max=1)


def test_restricted_rules() -> None:
    assert can_import(2, 0, RESTRICTED) is True   # tier 2 may import tier 0
    assert can_import(2, 1, RESTRICTED) is True   # tier 2 may import tier 1
    assert can_import(2, 2, RESTRICTED) is False  # tier 2 blocked from its own tier
    assert can_import(2, 3, RESTRICTED) is False  # tier 2 blocked above max
    assert can_import(3, 3, RESTRICTED) is True   # tier 3 unaffected (default max=3)


# --- Directory requirements ---


@pytest.mark.parametrize(
    "file_path, file_tier, requirements, passes",
    [
        ("src/auth/tokens.py", 0, {"src/auth": 0}, True),
        ("src/auth/tokens.py", 0, {"src/auth": 1}, True),
        ("src/auth/tokens.py", 2, {"src/auth": 0}, False),
        ("src/auth/tokens.py", 3, {"src/auth": 0}, False),
        ("scripts/deploy.py", 3, {"src/auth": 0}, True),
        ("src/auth/tokens.py", 3, {}, True),
    ],
)
def test_basic_directory_check(
    file_path: str, file_tier: int, requirements: dict[str, int], passes: bool
) -> None:
    assert check_directory_requirement(file_path, file_tier, requirements) is passes


@pytest.mark.parametrize(
    "file_path, file_tier, passes",
    [
        ("src/auth/tokens.py", 0, True),
        ("src/auth/tokens.py", 1, False),  # src/auth requires 0
        ("src/utils/helpers.py", 1, True),
        ("src/utils/helpers.py", 2, False),  # src requires 1
        ("src/auth/internal/secret.py", 0, True),
        ("src/auth/internal/secret.py", 1, False),
    ],
)
def test_most_specific_prefix_wins(file_path: str, file_tier: int, passes: bool) -> None:
    requirements = {"src": 1, "src/auth": 0}
    assert check_directory_requirement(file_path, file_tier, requirements) is passes


def test_path_segment_aware_not_startswith() -> None:
    """`src/auth` must NOT match `src/authentic/foo.py`."""
    requirements = {"src/auth": 0}
    assert check_directory_requirement("src/authentic/foo.py", 3, requirements) is True


def test_root_level_file_unrestricted() -> None:
    assert check_directory_requirement("main.py", 3, {"src": 1, "src/auth": 0}) is True
