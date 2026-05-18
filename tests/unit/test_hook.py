# @tear: 2
"""Tests for tears.hook.main — the Claude Code PostToolUse entry point.

Covers the argv path, the stdin JSON path, and config-error resilience.
The set_tear / process_file logic is tested in test_mutate.py.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from tears.hook import main


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def test_main_with_argv_path(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("import os\n")
    assert main([str(target)]) == 0
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_main_with_stdin_claude_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "x.py"
    target.write_text("import os\n")
    payload = json.dumps({"tool_input": {"file_path": str(target)}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert main([]) == 0
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_main_with_empty_stdin_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main([]) == 0


def test_main_with_malformed_stdin_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    assert main([]) == 0


def test_main_with_broken_config_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".tears.toml").write_text("max_tear: : :\n  nope\n")
    target = tmp_path / "x.py"
    target.write_text("import os\n")
    monkeypatch.chdir(tmp_path)
    assert main([str(target)]) == 0
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_main_respects_mutate_exclude(tmp_path: Path) -> None:
    (tmp_path / ".tears.toml").write_text('[mutate]\nexclude = ["generated/**"]\n')
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")

    assert main([str(target)]) == 0
    assert target.read_text() == "import os\n"


def test_main_respects_global_exclude(tmp_path: Path) -> None:
    (tmp_path / ".tears.toml").write_text('exclude = ["generated/**"]\n')
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")

    assert main([str(target)]) == 0
    assert target.read_text() == "import os\n"


def test_main_ignores_scan_exclude(tmp_path: Path) -> None:
    (tmp_path / ".tears.toml").write_text('[scan]\nexclude = ["generated/**"]\n')
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")

    assert main([str(target)]) == 0
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_main_respects_gitignore_by_default(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/**\n")
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")

    assert main([str(target)]) == 0
    assert target.read_text() == "import os\n"


def test_main_mutate_gitignore_override_allows_marking(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/**\n")
    (tmp_path / ".tears.toml").write_text("[mutate]\nrespect_gitignore = false\n")
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")

    assert main([str(target)]) == 0
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_main_global_gitignore_override_allows_marking(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/**\n")
    (tmp_path / ".tears.toml").write_text("respect_gitignore = false\n")
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")

    assert main([str(target)]) == 0
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_main_mutate_gitignore_section_override_beats_global_false(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/**\n")
    (tmp_path / ".tears.toml").write_text(
        "respect_gitignore = false\n\n[mutate]\nrespect_gitignore = true\n"
    )
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")

    assert main([str(target)]) == 0
    assert target.read_text() == "import os\n"


def test_main_explicit_exclude_wins_when_gitignore_disabled(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("generated/**\n")
    (tmp_path / ".tears.toml").write_text('respect_gitignore = false\nexclude = ["generated/**"]\n')
    target = tmp_path / "generated" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")

    assert main([str(target)]) == 0
    assert target.read_text() == "import os\n"
