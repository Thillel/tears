# @tear: 3
"""Tests for the checker against an in-memory fake ImportGraph.

No filesystem, no parsing — just construct graphs with known tiers and edges,
and verify the violations the checker produces.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from tears.checker import check
from tears.config import TearsConfig


@dataclass
class FakeGraph:
    """Minimal in-memory ImportGraph for tests."""

    tiers: dict[Path, int | None] = field(default_factory=lambda: {})
    edges: dict[Path, set[Path]] = field(default_factory=lambda: {})

    def files(self) -> Iterable[Path]:
        return self.tiers.keys()

    def tier_of(self, file: Path) -> int | None:
        return self.tiers.get(file)

    def imports_of(self, file: Path) -> Iterable[Path]:
        return self.edges.get(file, set())

    def importers_of(self, file: Path) -> Iterable[Path]:
        raise NotImplementedError


REPO = Path("/repo").resolve()


def p(rel: str) -> Path:
    return REPO / rel


def test_clean_graph_no_violations() -> None:
    graph = FakeGraph(
        tiers={p("src/a.py"): 0, p("src/b.py"): 1},
        edges={p("src/b.py"): {p("src/a.py")}},
    )
    report = check(graph, TearsConfig(), repo_root=REPO)
    assert report.exit_code == 0
    assert report.failure_count == 0
    assert report.warning_count == 0


def test_import_violation_tier1_imports_tier3() -> None:
    graph = FakeGraph(
        tiers={p("src/a.py"): 1, p("src/b.py"): 3},
        edges={p("src/a.py"): {p("src/b.py")}},
    )
    report = check(graph, TearsConfig(), repo_root=REPO)
    assert report.exit_code == 1
    a_report = next(f for f in report.files if f.path == p("src/a.py"))
    assert any("tear 1 cannot import from tear 3" in i.message for i in a_report.issues)


def test_tear3_importing_tear0_is_fine() -> None:
    graph = FakeGraph(
        tiers={p("src/a.py"): 0, p("scripts/x.py"): 3},
        edges={p("scripts/x.py"): {p("src/a.py")}},
    )
    report = check(graph, TearsConfig(), repo_root=REPO)
    assert report.exit_code == 0


def test_directory_requirement_violation() -> None:
    graph = FakeGraph(tiers={p("src/auth/tokens.py"): 2})
    config = TearsConfig(directory_requirements={"src/auth": 0})
    report = check(graph, config, repo_root=REPO)
    assert report.exit_code == 1
    issues = report.files[0].issues
    assert any("directory requires tear 0" in i.message for i in issues)
    assert any("file is tear 2" in i.message for i in issues)


def test_missing_header_warn_mode_warns_but_does_not_fail() -> None:
    graph = FakeGraph(tiers={p("src/x.py"): None})
    report = check(graph, TearsConfig(missing_header="warn"), repo_root=REPO)
    assert report.exit_code == 0
    assert report.warning_count == 1
    assert "missing @tear header" in report.files[0].issues[0].message


def test_missing_header_error_mode_fails() -> None:
    graph = FakeGraph(tiers={p("src/x.py"): None})
    report = check(graph, TearsConfig(missing_header="error"), repo_root=REPO)
    assert report.exit_code == 1
    assert report.failure_count == 1


def test_missing_header_is_treated_as_max_tear_for_import_check() -> None:
    """A header-less file in default-3 config can't import a tier-1 file."""
    graph = FakeGraph(
        tiers={p("src/a.py"): None, p("src/b.py"): 1},
        edges={p("src/a.py"): {p("src/b.py")}},
    )
    report = check(graph, TearsConfig(missing_header="warn"), repo_root=REPO)
    # No violation: missing -> tier 3, tier 3 can import tier 1.
    a_report = next(f for f in report.files if f.path == p("src/a.py"))
    assert all("cannot import" not in i.message for i in a_report.issues)


def test_custom_import_rules_relaxed_tier() -> None:
    config = TearsConfig(import_rules={1: 2})
    graph = FakeGraph(
        tiers={p("a.py"): 1, p("b.py"): 2, p("c.py"): 3},
        edges={p("a.py"): {p("b.py"), p("c.py")}},
    )
    report = check(graph, config, repo_root=REPO)
    a_report = next(f for f in report.files if f.path == p("a.py"))
    assert not any("cannot import from tear 2" in i.message for i in a_report.issues)
    assert any("cannot import from tear 3" in i.message for i in a_report.issues)


def test_artificial_tears_allow_directory_to_import_lower_trust_targets() -> None:
    graph = FakeGraph(
        tiers={p("tests/unit/test_cli.py"): 1, p("src/tears/cli.py"): 3},
        edges={p("tests/unit/test_cli.py"): {p("src/tears/cli.py")}},
    )
    config = TearsConfig(artificial_tears={"tests/unit": 3})

    report = check(graph, config, repo_root=REPO)

    test_report = next(f for f in report.files if f.path == p("tests/unit/test_cli.py"))
    assert report.exit_code == 0
    assert all("cannot import" not in i.message for i in test_report.issues)


def test_artificial_tears_override_import_rules_for_matching_importers() -> None:
    graph = FakeGraph(
        tiers={p("tests/unit/test_cli.py"): 1, p("src/tears/cli.py"): 3},
        edges={p("tests/unit/test_cli.py"): {p("src/tears/cli.py")}},
    )
    config = TearsConfig(import_rules={1: 1}, artificial_tears={"tests/unit": 3})

    report = check(graph, config, repo_root=REPO)

    test_report = next(f for f in report.files if f.path == p("tests/unit/test_cli.py"))
    assert report.exit_code == 0
    assert all("cannot import" not in i.message for i in test_report.issues)


def test_artificial_tears_use_longest_prefix() -> None:
    graph = FakeGraph(
        tiers={
            p("tests/unit/test_cli.py"): 1,
            p("tests/scan/test_scan.py"): 1,
            p("src/tears/cli.py"): 3,
        },
        edges={
            p("tests/unit/test_cli.py"): {p("src/tears/cli.py")},
            p("tests/scan/test_scan.py"): {p("src/tears/cli.py")},
        },
    )
    config = TearsConfig(artificial_tears={"tests": 2, "tests/unit": 3})

    report = check(graph, config, repo_root=REPO)

    unit_report = next(f for f in report.files if f.path == p("tests/unit/test_cli.py"))
    scan_report = next(f for f in report.files if f.path == p("tests/scan/test_scan.py"))
    assert all("cannot import" not in i.message for i in unit_report.issues)
    assert any(
        "artificial tear allows imports up to tear 2" in i.message for i in scan_report.issues
    )


def test_artificial_tears_are_path_segment_aware() -> None:
    graph = FakeGraph(
        tiers={p("tests/unit_extra/test_cli.py"): 1, p("src/tears/cli.py"): 3},
        edges={p("tests/unit_extra/test_cli.py"): {p("src/tears/cli.py")}},
    )
    config = TearsConfig(artificial_tears={"tests/unit": 3})

    report = check(graph, config, repo_root=REPO)

    test_report = next(f for f in report.files if f.path == p("tests/unit_extra/test_cli.py"))
    assert report.exit_code == 1
    assert any("tear 1 cannot import from tear 3" in i.message for i in test_report.issues)


def test_artificial_tears_can_restrict_directory_imports() -> None:
    graph = FakeGraph(
        tiers={p("src/auth/tokens.py"): 3, p("src/lib/util.py"): 2},
        edges={p("src/auth/tokens.py"): {p("src/lib/util.py")}},
    )
    config = TearsConfig(artificial_tears={"src/auth": 1})

    report = check(graph, config, repo_root=REPO)

    auth_report = next(f for f in report.files if f.path == p("src/auth/tokens.py"))
    assert report.exit_code == 1
    assert any(
        "artificial tear allows imports up to tear 1" in i.message for i in auth_report.issues
    )


def test_artificial_tears_do_not_override_directory_requirements() -> None:
    graph = FakeGraph(
        tiers={p("src/auth/tokens.py"): 1, p("src/lib/util.py"): 3},
        edges={p("src/auth/tokens.py"): {p("src/lib/util.py")}},
    )
    config = TearsConfig(
        directory_requirements={"src/auth": 0},
        artificial_tears={"src/auth": 3},
    )

    report = check(graph, config, repo_root=REPO)

    auth_report = next(f for f in report.files if f.path == p("src/auth/tokens.py"))
    assert report.exit_code == 1
    assert any("directory requires tear 0" in i.message for i in auth_report.issues)
    assert all("cannot import" not in i.message for i in auth_report.issues)
    assert all("artificial tear allows" not in i.message for i in auth_report.issues)


def test_multiple_violations_in_one_file() -> None:
    graph = FakeGraph(
        tiers={p("src/auth/tokens.py"): 2, p("src/x.py"): 3, p("src/y.py"): 3},
        edges={p("src/auth/tokens.py"): {p("src/x.py"), p("src/y.py")}},
    )
    config = TearsConfig(directory_requirements={"src/auth": 0})
    report = check(graph, config, repo_root=REPO)
    tokens = next(f for f in report.files if f.path == p("src/auth/tokens.py"))
    # 1 directory + 2 import = 3 issues
    assert sum(1 for i in tokens.issues if i.severity == "fail") == 3
