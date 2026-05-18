# @tear: 3
"""Tests for shared path filtering."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tears.exclude import is_gitignored, should_skip_path


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def test_is_gitignored_detects_ignored_paths(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/**\n")
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("# @tear: 3\n")

    assert is_gitignored(target, tmp_path) is True


def test_should_skip_path_respects_gitignore_toggle(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/**\n")
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("# @tear: 3\n")

    assert should_skip_path(target, tmp_path, patterns=[], respect_gitignore=True) is True
    assert should_skip_path(target, tmp_path, patterns=[], respect_gitignore=False) is False


def test_should_skip_path_still_applies_explicit_excludes(tmp_path: Path) -> None:
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("# @tear: 3\n")

    assert (
        should_skip_path(
            target,
            tmp_path,
            patterns=["generated/**"],
            respect_gitignore=False,
        )
        is True
    )


def test_is_gitignored_is_false_outside_git_repo(tmp_path: Path) -> None:
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("# @tear: 3\n")

    assert is_gitignored(target, tmp_path) is False
    assert should_skip_path(target, tmp_path, patterns=[], respect_gitignore=True) is False
