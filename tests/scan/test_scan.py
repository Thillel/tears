# @tear: 3
"""Snapshot-based integration tests.

Each directory under `tests/scan/fixtures/` is a complete mini-repo. The runner
copies the fixture into a temp dir (so tests can't mutate fixtures), runs the
bare `tears` CLI against it, and compares the output + exit code against
`expected.txt`.

Snapshot format: literal stdout, then (if non-empty) `--- stderr ---` followed by
stderr, then `--- exit: N ---` on its own line.

Regenerate by re-saving expected.txt or with `TEARS_UPDATE_SNAPSHOTS=1`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tears.cli import main as cli_main

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXIT_MARKER = "--- exit:"


def _discover_fixtures() -> list[str]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(p.name for p in FIXTURES_DIR.iterdir() if p.is_dir())


@pytest.mark.parametrize("fixture", _discover_fixtures())
def test_fixture(fixture: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_src = FIXTURES_DIR / fixture
    expected_path = fixture_src / "expected.txt"
    updating = bool(os.environ.get("TEARS_UPDATE_SNAPSHOTS"))
    if not updating:
        assert expected_path.exists(), f"{fixture}: missing expected.txt"

    work = tmp_path / fixture
    shutil.copytree(fixture_src, work)
    if (work / "expected.txt").exists():
        (work / "expected.txt").unlink()

    exit_code = cli_main([str(work)])
    captured = capsys.readouterr()
    stderr_block = f"--- stderr ---\n{captured.err}" if captured.err else ""
    actual = f"{captured.out}{stderr_block}{EXIT_MARKER} {exit_code} ---\n"

    if os.environ.get("TEARS_UPDATE_SNAPSHOTS"):
        expected_path.write_text(actual)
        return

    expected = expected_path.read_text()
    assert actual == expected, (
        f"snapshot mismatch for {fixture}.\n--- expected ---\n{expected}\n--- actual ---\n{actual}"
    )
