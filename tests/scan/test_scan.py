# @tear: 3
"""Snapshot-based integration tests.

Each directory under `tests/scan/fixtures/<suite>/` is a complete mini-repo. The
runner copies the fixture into a temp dir (so tests can't mutate fixtures), runs
the bare `tears` CLI against it, and compares the output + exit code against
`expected.txt`.

Future-behavior fixtures may include a `pytest.xfail` file containing a human
reason. Those fixtures still run and compare output, but are marked strict xfail
so they fail as XPASS once the implementation catches up.

Snapshot format: literal stdout, then (if non-empty) `--- stderr ---` followed by
stderr, then `--- exit: N ---` on its own line.

Regenerate by re-saving expected.txt or with `TEARS_UPDATE_SNAPSHOTS=1`.
Xfailed fixtures keep their desired future snapshots and are skipped in update mode.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from tears.cli import main as cli_main

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXIT_MARKER = "--- exit:"
XFAIL_MARKER = "pytest.xfail"


def _discover_fixtures() -> list[object]:
    if not FIXTURES_DIR.exists():
        return []
    params: list[object] = []
    suite_dirs = sorted((p for p in FIXTURES_DIR.iterdir() if p.is_dir()), key=lambda p: p.name)
    for suite_dir in suite_dirs:
        fixture_dirs = sorted((p for p in suite_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
        for fixture_dir in fixture_dirs:
            fixture_id = f"{suite_dir.name}/{fixture_dir.name}"
            xfail_path = fixture_dir / XFAIL_MARKER
            if not xfail_path.exists():
                params.append(fixture_id)
                continue
            reason = xfail_path.read_text().strip() or f"{fixture_id} is expected to fail"
            params.append(
                pytest.param(
                    fixture_id,
                    marks=pytest.mark.xfail(reason=reason, strict=True),
                )
            )
    return params


def test_xfail_fixtures_are_strict() -> None:
    """Future-behavior fixtures must fail as XPASS once their snapshots match."""
    fixture_params = [cast(Any, p) for p in _discover_fixtures() if not isinstance(p, str)]
    flat_script = next(p for p in fixture_params if p.values == ("python/30_flat_script_future",))
    xfail_marks = [mark for mark in flat_script.marks if mark.name == "xfail"]

    assert len(xfail_marks) == 1
    assert xfail_marks[0].kwargs["strict"] is True


@pytest.mark.parametrize("fixture", _discover_fixtures())
def test_fixture(fixture: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_src = FIXTURES_DIR / fixture
    expected_path = fixture_src / "expected.txt"
    updating = bool(os.environ.get("TEARS_UPDATE_SNAPSHOTS"))
    if updating and (fixture_src / XFAIL_MARKER).exists():
        pytest.skip("xfailed future-behavior fixtures are not auto-updated")
    if not updating:
        assert expected_path.exists(), f"{fixture}: missing expected.txt"

    work = tmp_path / fixture
    shutil.copytree(fixture_src, work)
    if (work / "expected.txt").exists():
        (work / "expected.txt").unlink()

    if (work / "_gitignore").exists():
        (work / "_gitignore").rename(work / ".gitignore")
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        subprocess.run(["git", "add", ".gitignore"], cwd=work, check=True)

    exit_code = cli_main([str(work)])
    captured = capsys.readouterr()
    stderr_block = f"--- stderr ---\n{captured.err}" if captured.err else ""
    actual = f"{captured.out}{stderr_block}{EXIT_MARKER} {exit_code} ---\n"

    if updating:
        expected_path.write_text(actual)
        return

    expected = expected_path.read_text()
    assert actual == expected, (
        f"snapshot mismatch for {fixture}.\n--- expected ---\n{expected}\n--- actual ---\n{actual}"
    )
