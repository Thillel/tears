# @tear: 2
"""Path filtering shared by the scanner and header-marking paths.

Patterns are fnmatch-style with `**` extended to match across path separators
(`**/foo.py` matches `a/b/c/foo.py`). Paths are matched relative to the repo root
in POSIX form.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path


def should_skip_path(
    file_path: Path,
    repo_root: Path,
    *,
    patterns: list[str],
    respect_gitignore: bool,
) -> bool:
    """True if `file_path` should be skipped for explicit or gitignore policy."""
    if is_excluded(file_path, repo_root, patterns):
        return True
    return respect_gitignore and is_gitignored(file_path, repo_root)


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


def is_gitignored(path: Path, repo_root: Path) -> bool:
    """Return True if `path` is ignored by git, False if not or git is unavailable."""
    try:
        rel_or_abs = path.relative_to(repo_root)
    except ValueError:
        rel_or_abs = path
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(rel_or_abs)],
            capture_output=True,
            cwd=repo_root,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _match_glob(path: str, pattern: str) -> bool:
    return re.compile(_glob_to_regex(pattern)).fullmatch(path) is not None


def _glob_to_regex(pattern: str) -> str:
    placeholder = "\x00DOUBLESTAR\x00"
    p = pattern.replace("**", placeholder)
    p = fnmatch.translate(p).rstrip("\\Z")
    return p.replace(re.escape(placeholder), ".*")
