# @tear: 3
"""Tests for @tear header extraction from the first 5 lines."""

from __future__ import annotations

from pathlib import Path

import pytest

from tears.header import parse_tear_level, parse_tear_level_for_path


@pytest.mark.parametrize(
    "content, expected",
    [
        ("# @tear: 0\nimport os", 0),
        ("# @tear: 1\ndef main(): pass", 1),
        ("# @tear: 2\n# unrelated comment", 2),
        ("# @tear: 3\n", 3),
    ],
    ids=["tear-0", "tear-1", "tear-2", "tear-3"],
)
def test_python_header_basic(content: str, expected: int) -> None:
    assert parse_tear_level(content) == expected


@pytest.mark.parametrize(
    "content, expected",
    [
        ("# @tear: 0\ncode", 0),
        ("#!/usr/bin/env python3\n# @tear: 1\nimport os", 1),
        ("#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n# @tear: 2\n", 2),
        ("# license\n# license\n# license\n# license\n# @tear: 0\n", 0),
        ("# a\n# b\n# c\n# d\n# e\n# @tear: 0\n", None),
    ],
    ids=["line-1", "line-2-after-shebang", "line-3", "line-5-last-valid", "line-6-too-late"],
)
def test_header_position_within_first_5_lines(content: str, expected: int | None) -> None:
    assert parse_tear_level(content) == expected


@pytest.mark.parametrize(
    "content",
    [
        "import os\ndef main(): pass",
        "",
        "# tear: 0",
        "# @tear 0",
        "# @tear: five",
        "# @tear: -1",
        "# @tear: 4",
        "# @tear: 1.5",
        'x = "# @tear: 0"\n',
    ],
    ids=[
        "no-header",
        "empty-file",
        "missing-at-sign",
        "missing-colon",
        "non-numeric",
        "negative",
        "out-of-range-default",
        "float-rejected",
        "inside-string-literal",
    ],
)
def test_missing_and_malformed_headers(content: str) -> None:
    assert parse_tear_level(content) is None


def test_multiple_headers_takes_worst() -> None:
    assert parse_tear_level("# @tear: 0\n# @tear: 2\ncode") == 2


def test_multiple_headers_ignores_out_of_range() -> None:
    """A malformed (out-of-range) value next to a valid one — keep the valid one."""
    assert parse_tear_level("# @tear: 1\n# @tear: 9\ncode") == 1


@pytest.mark.parametrize(
    "max_tear, content, expected",
    [
        (3, "# @tear: 3", 3),
        (3, "# @tear: 4", None),
        (5, "# @tear: 5", 5),
        (5, "# @tear: 4", 4),
        (5, "# @tear: 6", None),
        (1, "# @tear: 1", 1),
        (1, "# @tear: 2", None),
    ],
    ids=[
        "default-max-valid",
        "default-max-over",
        "extended-6-max",
        "extended-6-mid",
        "extended-6-over",
        "minimal-2-max",
        "minimal-2-over",
    ],
)
def test_configurable_max_tear(max_tear: int, content: str, expected: int | None) -> None:
    assert parse_tear_level(content, max_tear=max_tear) == expected


@pytest.mark.parametrize(
    "content, expected",
    [
        ("# @tear:0", 0),
        ("# @tear:  1", 1),
        ("# @tear:\t2", 2),
        ("#  @tear: 0", 0),
        ("  # @tear: 0", 0),
        ("\t#\t@tear:\t3", 3),
    ],
    ids=["no-space", "extra-spaces", "tab", "extra-after-comment", "leading-ws", "all-tabs"],
)
def test_whitespace_tolerance(content: str, expected: int) -> None:
    assert parse_tear_level(content) == expected


@pytest.mark.parametrize(
    "content, expected",
    [
        ("// @tear: 2\nexport const value = 1;\n", 2),
        ("<!-- @tear: 1 -->\n# Title\n", 1),
        ("/* @tear: 3 */\nconst value = 1;\n", 3),
    ],
    ids=["slash-slash", "html-comment", "block-comment"],
)
def test_non_python_comment_styles(content: str, expected: int) -> None:
    path = {
        "//": "main.ts",
        "<!--": "README.md",
        "/*": "styles.css",
    }[content.lstrip()[: content.lstrip().find(" ")]]
    assert parse_tear_level_for_path(Path(path), content) == expected


def test_path_specific_parser_rejects_wrong_comment_style() -> None:
    assert parse_tear_level_for_path(Path("main.ts"), "# @tear: 1\n") is None


def test_path_specific_parser_returns_none_for_unknown_file_type() -> None:
    assert parse_tear_level_for_path(Path("unknown.ext"), "# @tear: 1\n") is None
