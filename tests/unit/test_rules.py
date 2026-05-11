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

RELAXED = TearsConfig(import_rules={1: [0, 1, 2]}).resolved_import_rules()
ISLANDS = TearsConfig(
    import_rules={0: [0, 1], 1: [0, 1], 2: [2, 3], 3: [2, 3]}
).resolved_import_rules()
STRICT = TearsConfig(import_rules={0: [0], 1: [1], 2: [2], 3: [3]}).resolved_import_rules()


def test_relaxed_rules() -> None:
    assert can_import(1, 2, RELAXED) is True
    assert can_import(0, 2, RELAXED) is False
    assert can_import(0, 1, RELAXED) is False


def test_island_rules() -> None:
    assert can_import(0, 1, ISLANDS) is True
    assert can_import(1, 0, ISLANDS) is True
    assert can_import(2, 3, ISLANDS) is True
    assert can_import(3, 2, ISLANDS) is True
    assert can_import(0, 2, ISLANDS) is False
    assert can_import(2, 0, ISLANDS) is False
    assert can_import(1, 3, ISLANDS) is False
    assert can_import(3, 1, ISLANDS) is False


def test_strict_rules() -> None:
    assert can_import(0, 0, STRICT) is True
    assert can_import(0, 1, STRICT) is False
    assert can_import(1, 0, STRICT) is False
    assert can_import(3, 0, STRICT) is False


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
