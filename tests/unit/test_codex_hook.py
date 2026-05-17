# @tear: 3
"""Tests for tears.codex_hook.main."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tears.codex_hook import main, paths_from_apply_patch


def test_main_with_apply_patch_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "x.py"
    target.write_text("# @tear: 1\nimport os\n")
    payload = json.dumps(
        {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": f"*** Begin Patch\n*** Update File: {target}\n@@\n"
                "-# @tear: 1\n+# @tear: 3\n*** End Patch\n"
            },
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert main() == 0
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_main_with_multi_file_apply_patch_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("# @tear: 1\nA = 1\n")
    second.write_text("# @tear: 1\nB = 1\n")
    payload = json.dumps(
        {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": f"*** Begin Patch\n"
                f"*** Update File: {first}\n@@\n-# @tear: 1\n+# @tear: 3\n"
                f"*** Update File: {second}\n@@\n-# @tear: 1\n+# @tear: 3\n"
                "*** End Patch\n"
            },
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert main() == 0
    assert first.read_text() == "# @tear: 3\nA = 1\n"
    assert second.read_text() == "# @tear: 3\nB = 1\n"


def test_main_with_mixed_apply_patch_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    added = tmp_path / "added.py"
    edited = tmp_path / "edited.py"
    move_source = tmp_path / "move_source.py"
    moved = tmp_path / "moved.py"
    deleted = tmp_path / "deleted.py"
    added.write_text("# @tear: 1\nADDED = True\n")
    edited.write_text("# @tear: 0\nEDITED = 'after'\n")
    moved.write_text("# @tear: 0\nMOVED = 'after'\n")
    payload = json.dumps(
        {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": f"*** Begin Patch\n"
                f"*** Add File: {added}\n+# @tear: 1\n+ADDED = True\n"
                f"*** Update File: {edited}\n@@\n-# @tear: 1\n+# @tear: 0\n"
                f"*** Update File: {move_source}\n*** Move to: {moved}\n@@\n"
                "-# @tear: 1\n+# @tear: 0\n"
                f"*** Delete File: {deleted}\n"
                "*** End Patch\n"
            },
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert main() == 0
    assert added.read_text() == "# @tear: 3\nADDED = True\n"
    assert edited.read_text() == "# @tear: 3\nEDITED = 'after'\n"
    assert not move_source.exists()
    assert moved.read_text() == "# @tear: 3\nMOVED = 'after'\n"
    assert not deleted.exists()


def test_main_with_non_apply_patch_payload_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "make test"}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert main() == 0


@pytest.mark.parametrize(
    ("header", "path"),
    [
        ("*** Add File: src/new.py", "src/new.py"),
        ("*** Update File: src/existing.py", "src/existing.py"),
        ("*** Delete File: src/old.py", "src/old.py"),
        ("*** Move to: src/moved.py", "src/moved.py"),
    ],
)
def test_paths_from_apply_patch_extracts_patch_headers(header: str, path: str) -> None:
    assert paths_from_apply_patch(header) == [Path(path)]


def test_paths_from_apply_patch_ignores_body_text() -> None:
    command = (
        "*** Begin Patch\n+literal text mentioning *** Add File: not/a/path.py\n*** End Patch\n"
    )
    assert paths_from_apply_patch(command) == []
