# @tear: 3
"""Pure rule functions: tier comparison and directory requirements.

These functions know nothing about files, imports, or graphs — they take primitive
inputs and return booleans. The checker composes them.
"""

from __future__ import annotations


def can_import(
    importer_tier: int,
    target_tier: int,
    resolved_rules: dict[int, frozenset[int]],
) -> bool:
    """Is `importer_tier` allowed to import from `target_tier`?

    `resolved_rules` is the pre-computed full matrix from
    `TearsConfig.resolved_import_rules()`. Per-edge check is one set membership.
    """
    return target_tier in resolved_rules[importer_tier]


def check_directory_requirement(
    file_path: str,
    file_tier: int,
    requirements: dict[str, int],
) -> bool:
    """Does `file_tier` satisfy the longest-prefix-matching directory requirement?

    Matching is path-segment aware: `src/auth` matches `src/auth/tokens.py` but NOT
    `src/authentic/foo.py`. Files in unrestricted directories pass.
    """
    file_segments = _segments(file_path)
    longest_match: int | None = None
    longest_len = -1
    for dir_key, required_tier in requirements.items():
        dir_segments = _segments(dir_key)
        if len(dir_segments) > len(file_segments):
            continue
        if file_segments[: len(dir_segments)] != dir_segments:
            continue
        if len(dir_segments) > longest_len:
            longest_len = len(dir_segments)
            longest_match = required_tier
    if longest_match is None:
        return True
    return file_tier <= longest_match


def _segments(path: str) -> tuple[str, ...]:
    return tuple(p for p in path.strip("/").split("/") if p)
