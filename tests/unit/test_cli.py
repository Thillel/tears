# @tear: 3
"""Tests for CLI flags that are distinct from config-file behavior.

These test the wire-up between argparse and run_scan — not the full scan logic,
which is covered by the fixture-based integration tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tears.cli import main as cli_main


def _make_repo(tmp_path: Path, *, pkg_content: str = "", toml: str = "") -> Path:
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(pkg_content)
    base_toml = '[imports]\nsource_roots = ["src"]\n'
    (tmp_path / ".tears.toml").write_text(base_toml + toml)
    return tmp_path


def test_default_tear_flag_suppresses_missing_header_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path)  # __init__.py has no @tear header
    exit_code = cli_main(["--default-tear", "1", str(repo)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "missing @tear header" not in out
    assert "(tear 1)" in out


def test_default_tear_flag_overrides_config_default_tear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, toml="default_tear = 3\n")
    exit_code = cli_main(["--default-tear", "1", str(repo)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "(tear 1)" in out  # flag wins over config's default_tear = 3


def test_default_tear_flag_exceeding_max_tear_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path)  # max_tear defaults to 3
    exit_code = cli_main(["--default-tear", "99", str(repo)])
    assert exit_code == 2
    assert "default_tear" in capsys.readouterr().err
