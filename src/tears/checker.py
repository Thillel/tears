# @tear: 3
"""The pure checker: ImportGraph + TearsConfig -> list of FileReports.

This module knows nothing about the filesystem, parsing, or output formatting.
It composes the rule functions over the data the graph exposes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tears.config import TearsConfig
from tears.graph import ImportGraph
from tears.rules import can_import, check_directory_requirement

Severity = Literal["fail", "warn"]
Status = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class Issue:
    severity: Severity
    message: str


@dataclass(frozen=True)
class FileReport:
    path: Path
    tier: int | None
    effective_tier: int
    is_defaulted: bool = False
    issues: tuple[Issue, ...] = field(default_factory=lambda: ())

    @property
    def status(self) -> Status:
        if any(i.severity == "fail" for i in self.issues):
            return "fail"
        if any(i.severity == "warn" for i in self.issues):
            return "warn"
        return "ok"


@dataclass(frozen=True)
class CheckReport:
    files: tuple[FileReport, ...]

    @property
    def exit_code(self) -> int:
        return 1 if any(f.status == "fail" for f in self.files) else 0

    @property
    def failure_count(self) -> int:
        return sum(1 for f in self.files if f.status == "fail")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.files if f.status == "warn")


def check(
    graph: ImportGraph,
    config: TearsConfig,
    *,
    repo_root: Path,
) -> CheckReport:
    """Run all v1 checks: missing headers, directory requirements, import tiers."""
    resolved_rules = config.resolved_import_rules()
    missing_severity: Severity = "fail" if config.missing_header == "error" else "warn"

    reports: list[FileReport] = []
    for file_path in sorted(graph.files(), key=str):
        tier = graph.tier_of(file_path)
        rel_path = _relative_posix(file_path, repo_root)
        issues: list[Issue] = []

        is_defaulted = False
        if tier is not None:
            effective_tier = tier
        else:
            effective_tier, is_defaulted = config.resolve_missing_tier(rel_path)
            if not is_defaulted:
                issues.append(
                    Issue(
                        severity=missing_severity,
                        message=f"missing @tear header (treated as tear {effective_tier})",
                    )
                )

        if not check_directory_requirement(rel_path, effective_tier, config.directory_requirements):
            required = _required_tier(rel_path, config.directory_requirements)
            issues.append(
                Issue(
                    severity="fail",
                    message=f"directory requires tear {required}, file is tear {effective_tier}",
                )
            )

        for target in sorted(graph.imports_of(file_path), key=str):
            target_tier = graph.tier_of(target)
            if target_tier is not None:
                target_effective = target_tier
            else:
                target_rel_path = _relative_posix(target, repo_root)
                target_effective, _ = config.resolve_missing_tier(target_rel_path)
            artificial_tear = config.artificial_tear_for(rel_path)
            if artificial_tear is not None:
                can_import_target = target_effective <= artificial_tear
            else:
                can_import_target = can_import(effective_tier, target_effective, resolved_rules)
            if can_import_target:
                continue
            target_rel = _relative_posix(target, repo_root)
            if artificial_tear is not None:
                message = (
                    f"imports {target_rel} (tear {target_effective}): "
                    f"artificial tear allows imports up to tear {artificial_tear}"
                )
            else:
                message = (
                    f"imports {target_rel} (tear {target_effective}): "
                    f"tear {effective_tier} cannot import from tear {target_effective}"
                )
            issues.append(
                Issue(
                    severity="fail",
                    message=message,
                )
            )

        reports.append(
            FileReport(
                path=file_path,
                tier=tier,
                effective_tier=effective_tier,
                is_defaulted=is_defaulted,
                issues=tuple(issues),
            )
        )

    return CheckReport(files=tuple(reports))


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _required_tier(rel_path: str, requirements: dict[str, int]) -> int | None:
    file_segments = tuple(p for p in rel_path.strip("/").split("/") if p)
    longest_match: int | None = None
    longest_len = -1
    for dir_key, required_tier in requirements.items():
        dir_segments = tuple(p for p in dir_key.strip("/").split("/") if p)
        if len(dir_segments) > len(file_segments):
            continue
        if file_segments[: len(dir_segments)] != dir_segments:
            continue
        if len(dir_segments) > longest_len:
            longest_len = len(dir_segments)
            longest_match = required_tier
    return longest_match
