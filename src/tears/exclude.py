# @tear: 2
"""Exclude-pattern matching shared by the graph builder and the Claude hook.

Patterns are fnmatch-style with `**` extended to match across path separators
(`**/foo.py` matches `a/b/c/foo.py`). Paths are matched relative to the repo root
in POSIX form.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path


def is_excluded(file_path: Path, repo_root: Path, patterns: list[str]) -> bool:
    """True if `file_path` matches any of `patterns` relative to `repo_root`."""
    if not patterns:
        return False
    try:
        rel = file_path.relative_to(repo_root).as_posix()
    except ValueError:
        try:
            rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return False
    return any(_match_glob(rel, p) for p in patterns)


def _match_glob(path: str, pattern: str) -> bool:
    return re.compile(_glob_to_regex(pattern)).fullmatch(path) is not None


def _glob_to_regex(pattern: str) -> str:
    placeholder = "\x00DOUBLESTAR\x00"
    p = pattern.replace("**", placeholder)
    p = fnmatch.translate(p).rstrip("\\Z")
    return p.replace(re.escape(placeholder), ".*")
