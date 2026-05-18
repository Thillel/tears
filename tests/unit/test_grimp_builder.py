# @tear: 3
"""Direct tests for the grimp-backed graph builder.

These tests lock down the builder's current discovery semantics separately from
the end-to-end scan snapshots.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tears.config import TearsConfig
from tears.graph import grimp_builder
from tears.graph.grimp_builder import build_grimp_graph


def _write(path: Path, text: str = "# @tear: 1\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path.resolve()


def test_discovers_top_level_packages_and_import_edges(tmp_path: Path) -> None:
    app_init = _write(tmp_path / "app" / "__init__.py")
    app_core = _write(tmp_path / "app" / "core.py", "# @tear: 1\nfrom . import utils\n")
    app_utils = _write(tmp_path / "app" / "utils.py", "# @tear: 2\n")
    other_init = _write(tmp_path / "other" / "__init__.py")

    graph = build_grimp_graph(tmp_path, TearsConfig())

    assert set(graph.files()) == {app_init, app_core, app_utils, other_init}
    assert graph.tier_of(app_core) == 1
    assert graph.tier_of(app_utils) == 2
    assert set(graph.imports_of(app_core)) == {app_utils}
    assert set(graph.importers_of(app_utils)) == {app_core}


def test_source_roots_limit_package_discovery(tmp_path: Path) -> None:
    in_root = _write(tmp_path / "src" / "app" / "__init__.py")
    _write(tmp_path / "not_source" / "ignored" / "__init__.py")

    graph = build_grimp_graph(tmp_path, TearsConfig(source_roots=["src"]))

    assert set(graph.files()) == {in_root}


def test_missing_and_empty_source_roots_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    graph = build_grimp_graph(tmp_path, TearsConfig(source_roots=["missing", "empty"]))

    assert set(graph.files()) == set()


def test_flat_python_files_are_not_discovered(tmp_path: Path) -> None:
    _write(tmp_path / "script.py")

    graph = build_grimp_graph(tmp_path, TearsConfig())

    assert set(graph.files()) == set()


def test_namespace_packages_are_not_discovered(tmp_path: Path) -> None:
    _write(tmp_path / "namespace_pkg" / "module.py")

    graph = build_grimp_graph(tmp_path, TearsConfig())

    assert set(graph.files()) == set()


def test_git_ignored_top_level_package_is_not_discovered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept = _write(tmp_path / "kept" / "__init__.py")
    ignored = _write(tmp_path / "ignored" / "__init__.py")

    def fake_git_ignored(path: Path, repo_root: Path) -> bool:
        assert repo_root == tmp_path.resolve()
        return path.resolve() == ignored.parent

    monkeypatch.setattr(grimp_builder, "_git_ignored", fake_git_ignored)

    graph = build_grimp_graph(tmp_path, TearsConfig())

    assert set(graph.files()) == {kept}


def test_excluded_files_are_omitted_from_files_and_edges(tmp_path: Path) -> None:
    api_init = _write(tmp_path / "api" / "__init__.py")
    routes = _write(tmp_path / "api" / "routes.py", "# @tear: 1\nfrom . import schema\n")
    _write(tmp_path / "api" / "schema.py", "# @tear: 3\n")

    graph = build_grimp_graph(tmp_path, TearsConfig(exclude=["api/schema.py"]))

    assert set(graph.files()) == {api_init, routes}
    assert set(graph.imports_of(routes)) == set()


def test_scan_exclude_omits_files_from_graph(tmp_path: Path) -> None:
    api_init = _write(tmp_path / "api" / "__init__.py")
    schema = _write(tmp_path / "api" / "schema.py")

    graph = build_grimp_graph(tmp_path, TearsConfig(scan_exclude=["api/schema.py"]))

    assert set(graph.files()) == {api_init}
    assert schema not in set(graph.files())


def test_mutate_exclude_does_not_affect_graph(tmp_path: Path) -> None:
    api_init = _write(tmp_path / "api" / "__init__.py")
    schema = _write(tmp_path / "api" / "schema.py")

    graph = build_grimp_graph(tmp_path, TearsConfig(mutate_exclude=["api/schema.py"]))

    assert set(graph.files()) == {api_init, schema}


def test_package_root_with_only_init_is_discovered(tmp_path: Path) -> None:
    empty_pkg_init = _write(tmp_path / "empty_pkg" / "__init__.py")

    graph = build_grimp_graph(tmp_path, TearsConfig())

    assert set(graph.files()) == {empty_pkg_init}
