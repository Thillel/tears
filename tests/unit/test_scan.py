# @tear: 3
"""Tests for scan-level diagnostics."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tears.checker import CheckReport, FileReport
from tears.config import TearsConfig
from tears.scan import should_warn_empty_scan


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def test_warns_when_empty_report_but_source_files_exist(tmp_path: Path) -> None:
    (tmp_path / "script.py").write_text("# @tear: 3\n")
    report = CheckReport(files=())

    assert should_warn_empty_scan(report, repo_root=tmp_path, config=TearsConfig()) is True


def test_does_not_warn_when_report_checked_files(tmp_path: Path) -> None:
    file_path = tmp_path / "pkg" / "__init__.py"
    file_path.parent.mkdir()
    file_path.write_text("# @tear: 3\n")
    report = CheckReport(
        files=(
            FileReport(
                path=file_path,
                tier=3,
                effective_tier=3,
            ),
        )
    )

    assert should_warn_empty_scan(report, repo_root=tmp_path, config=TearsConfig()) is False


def test_does_not_warn_when_source_files_are_excluded(tmp_path: Path) -> None:
    generated = tmp_path / "generated" / "schema.py"
    generated.parent.mkdir()
    generated.write_text("# @tear: 3\n")
    report = CheckReport(files=())
    config = TearsConfig(exclude=["generated/**"])

    assert should_warn_empty_scan(report, repo_root=tmp_path, config=config) is False


def test_does_not_warn_when_source_files_are_gitignored(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/**\n")
    generated = tmp_path / "generated" / "schema.py"
    generated.parent.mkdir()
    generated.write_text("# @tear: 3\n")
    report = CheckReport(files=())

    assert should_warn_empty_scan(report, repo_root=tmp_path, config=TearsConfig()) is False


def test_does_not_warn_when_no_python_files_exist(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("<!-- @tear: 3 -->\n")
    report = CheckReport(files=())

    assert should_warn_empty_scan(report, repo_root=tmp_path, config=TearsConfig()) is False
