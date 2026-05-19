# @tear: 2
"""Tests for the tree-sitter-backed graph builder."""

from __future__ import annotations

from pathlib import Path

from tears.config import TearsConfig
from tears.graph.tree_sitter_builder import build_tree_sitter_graph


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path.resolve()


def test_default_language_set_scans_python_only(tmp_path: Path) -> None:
    script = _write(tmp_path / "script.py", "# @tear: 1\n")
    _write(tmp_path / "main.ts", "// @tear: 1\n")

    graph = build_tree_sitter_graph(tmp_path, TearsConfig())

    assert set(graph.files()) == {script}


def test_opted_in_typescript_imports_are_resolved(tmp_path: Path) -> None:
    main = _write(
        tmp_path / "src" / "main.ts",
        '// @tear: 0\nimport { value } from "./util";\n',
    )
    util = _write(tmp_path / "src" / "util.ts", "// @tear: 3\nexport const value = 1;\n")

    graph = build_tree_sitter_graph(
        tmp_path,
        TearsConfig(source_roots=["src"], languages=["typescript"]),
    )

    assert set(graph.files()) == {main, util}
    assert set(graph.imports_of(main)) == {util}


def test_cpp_language_includes_h_headers(tmp_path: Path) -> None:
    main = _write(tmp_path / "src" / "main.cpp", '// @tear: 0\n#include "secret.h"\n')
    secret = _write(tmp_path / "src" / "secret.h", "// @tear: 3\n")

    graph = build_tree_sitter_graph(
        tmp_path,
        TearsConfig(source_roots=["src"], languages=["cpp"]),
    )

    assert set(graph.files()) == {main, secret}
    assert set(graph.imports_of(main)) == {secret}
