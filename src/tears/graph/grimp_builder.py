# @tear: 3
"""grimp-backed `ImportGraph` implementation.

Builds the graph by:
1. Walking the configured `source_roots` to discover top-level Python packages.
2. Calling `grimp.build_graph(*pkgs)` to get all imports.
3. Mapping grimp's dotted module names back to absolute repo file paths.
4. Parsing each file's `@tear` header.
5. Applying the `exclude` patterns so excluded files are invisible to the checker.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import grimp

from tears.config import TearsConfig
from tears.exclude import is_excluded
from tears.header import parse_tear_level


class GrimpImportGraph:
    """`ImportGraph` over a real repo, backed by grimp."""

    def __init__(
        self,
        *,
        files: dict[Path, int | None],
        imports: dict[Path, frozenset[Path]],
        importers: dict[Path, frozenset[Path]],
    ) -> None:
        self._files = files
        self._imports = imports
        self._importers = importers

    def files(self) -> Iterable[Path]:
        return self._files.keys()

    def tier_of(self, file: Path) -> int | None:
        return self._files.get(file)

    def imports_of(self, file: Path) -> Iterable[Path]:
        return self._imports.get(file, frozenset())

    def importers_of(self, file: Path) -> Iterable[Path]:
        return self._importers.get(file, frozenset())


def build_grimp_graph(repo_root: Path, config: TearsConfig) -> GrimpImportGraph:
    """Build the import graph for `repo_root` under `config`."""
    repo_root = repo_root.resolve()
    source_root_paths = [(repo_root / r).resolve() for r in config.source_roots]

    packages: list[tuple[str, Path]] = []
    for sr in source_root_paths:
        if not sr.is_dir():
            continue
        for child in sorted(sr.iterdir()):
            if child.is_dir() and (child / "__init__.py").exists():
                packages.append((child.name, sr))

    if not packages:
        return GrimpImportGraph(files={}, imports={}, importers={})

    sys_path_added: list[str] = []
    for sr in source_root_paths:
        sr_str = str(sr)
        if sr_str not in sys.path:
            sys.path.insert(0, sr_str)
            sys_path_added.append(sr_str)

    try:
        package_names = [name for name, _ in packages]
        graph = cast(Any, grimp.build_graph(*package_names))  # pyright: ignore[reportUnknownMemberType]
    finally:
        for sr_str in sys_path_added:
            with contextlib.suppress(ValueError):
                sys.path.remove(sr_str)

    package_roots = {name: sr / name for name, sr in packages}
    module_to_file = _build_module_index(package_roots)

    files: dict[Path, int | None] = {}
    for file_path in module_to_file.values():
        if is_excluded(file_path, repo_root, config.exclude):
            continue
        files[file_path] = parse_tear_level(file_path.read_text(), max_tear=config.max_tear)

    imports: dict[Path, set[Path]] = {f: set() for f in files}
    importers: dict[Path, set[Path]] = {f: set() for f in files}

    file_to_module = {f: m for m, f in module_to_file.items()}

    for file_path in files:
        module = file_to_module[file_path]
        for imported_module in graph.find_modules_directly_imported_by(module):
            target = module_to_file.get(imported_module)
            if target is None or target not in files:
                continue
            imports[file_path].add(target)
            importers[target].add(file_path)

    return GrimpImportGraph(
        files=files,
        imports={k: frozenset(v) for k, v in imports.items()},
        importers={k: frozenset(v) for k, v in importers.items()},
    )


def _build_module_index(package_roots: dict[str, Path]) -> dict[str, Path]:
    """Map every reachable module name to its source file."""
    index: dict[str, Path] = {}
    for pkg_name, pkg_root in package_roots.items():
        for py_file in pkg_root.rglob("*.py"):
            rel = py_file.relative_to(pkg_root)
            parts = rel.with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            module = ".".join((pkg_name, *parts)) if parts else pkg_name
            index[module] = py_file.resolve()
    return index
