# @tear: 3
"""Scan orchestration and output formatting.

Loads the config, builds the import graph, runs the checker, prints a
human-readable report. The exact output format here is pinned by snapshot tests
in `tests/scan/fixtures/`.
"""

from __future__ import annotations

from dataclasses import replace
from io import StringIO
from pathlib import Path

from tears.checker import CheckReport, FileReport, check
from tears.config import TearsConfig, load_config
from tears.exclude import should_skip_path
from tears.graph.tree_sitter_builder import build_tree_sitter_graph

_ANSI = {
    "ok": "\033[32m",
    "warn": "\033[33m",
    "fail": "\033[31m",
    "reset": "\033[0m",
}

_EMPTY_SCAN_WARNING = (
    "warning: no files were checked, but source files exist under this scan root.\n"
    "         Check scan configuration, source roots, and current language/layout support.\n"
)


def run_scan(
    repo_root: Path,
    *,
    color: bool = False,
    default_tear: int | None = None,
) -> tuple[CheckReport, str]:
    """Run a full scan of `repo_root`. Returns the report and formatted output."""
    config = load_config(repo_root)
    if default_tear is not None:
        config = replace(config, default_tear=default_tear)
    graph = build_tree_sitter_graph(repo_root, config)
    report = check(graph, config, repo_root=repo_root)
    output = format_report(report, repo_root=repo_root, color=color)
    if should_warn_empty_scan(report, repo_root=repo_root, config=config):
        output += _EMPTY_SCAN_WARNING
    return report, output


def should_warn_empty_scan(
    report: CheckReport,
    *,
    repo_root: Path,
    config: TearsConfig,
) -> bool:
    """True when no files were checked but candidate source files exist."""
    return len(report.files) == 0 and _has_candidate_source_files(repo_root, config=config)


def format_report(report: CheckReport, *, repo_root: Path, color: bool = False) -> str:
    """Format a `CheckReport` for human consumption."""
    out = StringIO()
    for fr in report.files:
        out.write(_format_file(fr, repo_root=repo_root, color=color))
    out.write(_format_summary(report))
    return out.getvalue()


def _format_file(fr: FileReport, *, repo_root: Path, color: bool = False) -> str:
    label = {"ok": "OK   ", "warn": "WARN ", "fail": "FAIL "}[fr.status]
    if color:
        label = f"{_ANSI[fr.status]}{label}{_ANSI['reset']}"
    rel = _relative(fr.path, repo_root)
    show_tier = fr.tier is not None or fr.is_defaulted
    tier_suffix = f" (tear {fr.effective_tier})" if show_tier else ""
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


def _has_candidate_source_files(repo_root: Path, *, config: TearsConfig) -> bool:
    if not repo_root.is_dir():
        return False
    for path in repo_root.rglob("*.py"):
        if not path.is_file():
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if should_skip_path(
            path,
            repo_root,
            patterns=config.excludes_for_scan(),
            respect_gitignore=config.respect_gitignore_for_scan(),
        ):
            continue
        return True
    return False


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
