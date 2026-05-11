# @tear: 3
"""Scan orchestration and output formatting.

Loads the config, builds the import graph via grimp, runs the checker, prints a
human-readable report. The exact output format here is pinned by snapshot tests
in `tests/scan/fixtures/`.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from tears.checker import CheckReport, FileReport, check
from tears.config import load_config
from tears.graph.grimp_builder import build_grimp_graph


def run_scan(repo_root: Path) -> tuple[CheckReport, str]:
    """Run a full scan of `repo_root`. Returns the report and formatted output."""
    config = load_config(repo_root)
    graph = build_grimp_graph(repo_root, config)
    report = check(graph, config, repo_root=repo_root)
    return report, format_report(report, repo_root=repo_root)


def format_report(report: CheckReport, *, repo_root: Path) -> str:
    """Format a `CheckReport` for human consumption."""
    out = StringIO()
    for fr in report.files:
        out.write(_format_file(fr, repo_root=repo_root))
    out.write(_format_summary(report))
    return out.getvalue()


def _format_file(fr: FileReport, *, repo_root: Path) -> str:
    label = {"ok": "OK   ", "warn": "WARN ", "fail": "FAIL "}[fr.status]
    rel = _relative(fr.path, repo_root)
    tier_suffix = f" (tear {fr.tier})" if fr.tier is not None else ""
    line = f"{label} {rel}{tier_suffix}\n"
    issues = "".join(f"  - {i.message}\n" for i in fr.issues)
    suffix = "\n" if fr.issues else ""
    return line + issues + suffix


def _format_summary(report: CheckReport) -> str:
    n = len(report.files)
    failures = report.failure_count
    warnings = report.warning_count
    return (
        f"{n} {_plural(n, 'file', 'files')} checked, "
        f"{failures} {_plural(failures, 'failure', 'failures')}, "
        f"{warnings} {_plural(warnings, 'warning', 'warnings')}\n"
    )


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
