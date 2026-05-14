# @tear: 3
"""Tests for CLI flags that are distinct from config-file behavior.

These test the wire-up between argparse and run_scan — not the full scan logic,
which is covered by the fixture-based integration tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tears.cli import main as cli_main


class _FakeTTY:
    def isatty(self) -> bool:
        return True


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


# --- tears up ---


def test_up_inserts_header_when_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("import os\n")
    assert cli_main(["up", str(f), "--tear", "3"]) == 0
    assert f.read_text() == "# @tear: 3\nimport os\n"
    assert "∅ → 3" in capsys.readouterr().out


def test_up_sets_higher_tear_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 1\nimport os\n")
    assert cli_main(["up", str(f), "--tear", "3"]) == 0
    assert f.read_text() == "# @tear: 3\nimport os\n"
    assert "1 → 3" in capsys.readouterr().out


def test_up_intermediate_tear(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 1\nimport os\n")
    assert cli_main(["up", str(f), "--tear", "2"]) == 0
    assert f.read_text() == "# @tear: 2\nimport os\n"


def test_up_rejects_lower_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 2\nimport os\n")
    assert cli_main(["up", str(f), "--tear", "1"]) == 1
    assert f.read_text() == "# @tear: 2\nimport os\n"  # unchanged
    assert "tears down" in capsys.readouterr().err


def test_up_requires_tear_arg(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 3\nimport os\n")
    assert cli_main(["up", str(f)]) == 2
    assert f.read_text() == "# @tear: 3\nimport os\n"  # unchanged
    assert "--tear" in capsys.readouterr().err


def test_up_idempotent_at_max(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 3\nimport os\n")
    assert cli_main(["up", str(f), "--tear", "3"]) == 0
    assert f.read_text() == "# @tear: 3\nimport os\n"


def test_up_dir_marks_all_files(tmp_path: Path) -> None:
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "a.py").write_text("# @tear: 1\nx = 1\n")
    (sub / "b.py").write_text("# @tear: 2\ny = 2\n")
    assert cli_main(["up", str(sub), "--tear", "3"]) == 0
    assert (sub / "a.py").read_text() == "# @tear: 3\nx = 1\n"
    assert (sub / "b.py").read_text() == "# @tear: 3\ny = 2\n"


def test_up_dir_skips_files_where_number_would_go_down(tmp_path: Path) -> None:
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "already_higher.py").write_text("# @tear: 3\nx = 1\n")
    (sub / "lower.py").write_text("# @tear: 1\ny = 2\n")
    assert cli_main(["up", str(sub), "--tear", "2"]) == 0
    assert (sub / "already_higher.py").read_text() == "# @tear: 3\nx = 1\n"  # untouched
    assert (sub / "lower.py").read_text() == "# @tear: 2\ny = 2\n"  # updated


# --- tears down ---


def test_down_lowers_tear(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 3\nimport os\n")
    assert cli_main(["down", str(f), "--tear", "0"]) == 0
    assert f.read_text() == "# @tear: 0\nimport os\n"
    assert "3 → 0" in capsys.readouterr().out


def test_down_requires_tear_arg(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 3\nimport os\n")
    assert cli_main(["down", str(f)]) == 2
    assert f.read_text() == "# @tear: 3\nimport os\n"  # unchanged
    assert "--tear" in capsys.readouterr().err


def test_down_explicit_tear(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 3\nimport os\n")
    assert cli_main(["down", str(f), "--tear", "1"]) == 0
    assert f.read_text() == "# @tear: 1\nimport os\n"


def test_down_rejects_higher_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 1\nimport os\n")
    assert cli_main(["down", str(f), "--tear", "2"]) == 1
    assert f.read_text() == "# @tear: 1\nimport os\n"  # unchanged
    assert "tears up" in capsys.readouterr().err


def test_down_headerless_file_treated_as_max(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("import os\n")
    assert cli_main(["down", str(f), "--tear", "1"]) == 0
    assert f.read_text() == "# @tear: 1\nimport os\n"


def test_down_rejects_same_tear(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 1\nimport os\n")
    assert cli_main(["down", str(f), "--tear", "1"]) == 1
    assert f.read_text() == "# @tear: 1\nimport os\n"  # unchanged
    assert "tears up" in capsys.readouterr().err


def test_down_dir_marks_all_files(tmp_path: Path) -> None:
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "a.py").write_text("# @tear: 3\nx = 1\n")
    (sub / "b.py").write_text("# @tear: 2\ny = 2\n")
    assert cli_main(["down", str(sub), "--tear", "1"]) == 0
    assert (sub / "a.py").read_text() == "# @tear: 1\nx = 1\n"
    assert (sub / "b.py").read_text() == "# @tear: 1\ny = 2\n"


def test_down_dir_skips_files_already_lower(tmp_path: Path) -> None:
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "reviewed.py").write_text("# @tear: 0\nx = 1\n")
    (sub / "draft.py").write_text("# @tear: 3\ny = 2\n")
    assert cli_main(["down", str(sub), "--tear", "1"]) == 0
    assert (sub / "reviewed.py").read_text() == "# @tear: 0\nx = 1\n"  # untouched
    assert (sub / "draft.py").read_text() == "# @tear: 1\ny = 2\n"


# --- tears init ---


def test_init_creates_config_and_tags_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.py").write_text("import os\n")
    (tmp_path / "b.py").write_text("# @tear: 1\nx = 1\n")
    assert cli_main(["init", str(tmp_path)]) == 0
    assert (tmp_path / ".tears.toml").exists()
    assert (tmp_path / "a.py").read_text() == "# @tear: 3\nimport os\n"
    assert (tmp_path / "b.py").read_text() == "# @tear: 1\nx = 1\n"  # untouched
    out = capsys.readouterr().out
    assert "created" in out
    assert "tagged 1 file at tear 3" in out


def test_init_skips_existing_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".tears.toml").write_text("max_tear = 2\n")
    assert cli_main(["init", str(tmp_path)]) == 0
    assert "already exists" in capsys.readouterr().out


def test_init_walks_subdirectories(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sub = tmp_path / "src" / "pkg"
    sub.mkdir(parents=True)
    (sub / "core.py").write_text("import os\n")
    (sub / "util.py").write_text("import os\n")
    assert cli_main(["init", str(tmp_path)]) == 0
    assert (sub / "core.py").read_text() == "# @tear: 3\nimport os\n"
    assert (sub / "util.py").read_text() == "# @tear: 3\nimport os\n"
    assert "tagged 2 files at tear 3" in capsys.readouterr().out


def test_init_default_path_is_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("import os\n")
    assert cli_main(["init"]) == 0
    assert (tmp_path / ".tears.toml").exists()


def test_init_custom_tear_tags_at_specified_level(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import os\n")
    assert cli_main(["init", str(tmp_path), "--tear", "1"]) == 0
    assert (tmp_path / "a.py").read_text() == "# @tear: 1\nimport os\n"


def test_init_custom_tear_skips_existing_headers(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import os\n")
    (tmp_path / "b.py").write_text("# @tear: 2\nx = 1\n")
    assert cli_main(["init", str(tmp_path), "--tear", "1"]) == 0
    assert (tmp_path / "a.py").read_text() == "# @tear: 1\nimport os\n"
    assert (tmp_path / "b.py").read_text() == "# @tear: 2\nx = 1\n"  # untouched


def test_init_tear_exceeding_max_tear_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["init", str(tmp_path), "--tear", "99"]) == 2
    assert "out of range" in capsys.readouterr().err


def test_init_interactive_uses_prompted_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "x.py").write_text("import os\n")

    def _input(prompt: str) -> str:
        return "2"

    monkeypatch.setattr("builtins.input", _input)
    monkeypatch.setattr("sys.stdin", _FakeTTY())
    assert cli_main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "x.py").read_text() == "# @tear: 2\nimport os\n"


def test_init_interactive_empty_input_defaults_to_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "x.py").write_text("import os\n")

    def _input(prompt: str) -> str:
        return ""

    monkeypatch.setattr("builtins.input", _input)
    monkeypatch.setattr("sys.stdin", _FakeTTY())
    assert cli_main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "x.py").read_text() == "# @tear: 1\nimport os\n"


# --- tears set ---


def test_set_inserts_header_when_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "x.py"
    f.write_text("import os\n")
    assert cli_main(["set", str(f), "--tear", "2"]) == 0
    assert f.read_text() == "# @tear: 2\nimport os\n"
    assert "∅ → 2" in capsys.readouterr().out


def test_set_raises_tear_number(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 1\nimport os\n")
    assert cli_main(["set", str(f), "--tear", "3"]) == 0
    assert f.read_text() == "# @tear: 3\nimport os\n"


def test_set_lowers_tear_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 3\nimport os\n")
    assert cli_main(["set", str(f), "--tear", "1"]) == 0
    assert f.read_text() == "# @tear: 1\nimport os\n"
    assert "3 → 1" in capsys.readouterr().out


def test_set_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 2\nimport os\n")
    assert cli_main(["set", str(f), "--tear", "2"]) == 0
    assert f.read_text() == "# @tear: 2\nimport os\n"
    assert capsys.readouterr().out == ""


def test_set_requires_tear_arg(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.py"
    f.write_text("# @tear: 3\nimport os\n")
    assert cli_main(["set", str(f)]) == 2
    assert f.read_text() == "# @tear: 3\nimport os\n"
    assert "--tear" in capsys.readouterr().err


def test_set_dir_marks_all_files(tmp_path: Path) -> None:
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "a.py").write_text("# @tear: 3\nx = 1\n")
    (sub / "b.py").write_text("# @tear: 0\ny = 2\n")
    assert cli_main(["set", str(sub), "--tear", "1"]) == 0
    assert (sub / "a.py").read_text() == "# @tear: 1\nx = 1\n"
    assert (sub / "b.py").read_text() == "# @tear: 1\ny = 2\n"


def test_set_dir_no_direction_constraint(tmp_path: Path) -> None:
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "low.py").write_text("# @tear: 0\nx = 1\n")
    (sub / "high.py").write_text("# @tear: 3\ny = 2\n")
    (sub / "missing.py").write_text("z = 3\n")
    assert cli_main(["set", str(sub), "--tear", "2"]) == 0
    assert (sub / "low.py").read_text() == "# @tear: 2\nx = 1\n"
    assert (sub / "high.py").read_text() == "# @tear: 2\ny = 2\n"
    assert (sub / "missing.py").read_text() == "# @tear: 2\nz = 3\n"
