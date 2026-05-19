# @tear: 3
"""Tree-sitter-backed import graph builder for file-oriented languages."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from tears.config import TearsConfig
from tears.exclude import should_skip_path
from tears.graph.file_graph import FileImportGraph
from tears.graph.tree_sitter_scan.extractors import EXTRACTORS
from tears.graph.tree_sitter_scan.model import ParseContext, RepoIndex, SourceFile
from tears.graph.tree_sitter_scan.resolution import (
    first_match,
    java_class_names,
    python_module_name,
    read_go_module,
)
from tears.graph.tree_sitter_scan.syntax import parse_root
from tears.header import parse_tear_level_for_path
from tears.languages import enabled_language_for_suffix


def build_tree_sitter_graph(repo_root: Path, config: TearsConfig) -> FileImportGraph:
    """Build a file-oriented graph for languages handled by tree-sitter."""
    repo_root = repo_root.resolve()
    source_roots = tuple(
        path for root in config.source_roots if (path := (repo_root / root).resolve()).is_dir()
    )
    sources = _discover_sources(repo_root, source_roots, config)

    files = {
        source.path: parse_tear_level_for_path(source.path, source.text, max_tear=config.max_tear)
        for source in sources
    }
    imports: dict[Path, set[Path]] = {path: set() for path in files}
    importers: dict[Path, set[Path]] = {path: set() for path in files}

    index = _build_index(repo_root, source_roots, sources)
    for source in sources:
        root_node = parse_root(source.language, source.text)
        if root_node is None:
            continue
        ctx = ParseContext(
            repo_root=repo_root,
            source=source,
            root_node=root_node,
            index=index,
        )
        extractor = EXTRACTORS.get(source.language)
        if extractor is None:
            continue
        for target in extractor(ctx):
            if target not in files:
                continue
            imports[source.path].add(target)
            importers[target].add(source.path)

    return FileImportGraph(
        files=files,
        imports={k: frozenset(v) for k, v in imports.items()},
        importers={k: frozenset(v) for k, v in importers.items()},
    )


def _discover_sources(
    repo_root: Path, source_roots: tuple[Path, ...], config: TearsConfig
) -> list[SourceFile]:
    sources: list[SourceFile] = []
    seen: set[Path] = set()
    for source_root in source_roots:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            language = enabled_language_for_suffix(path.suffix.lower(), config.languages)
            if language is None:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            if should_skip_path(
                resolved,
                repo_root,
                patterns=config.excludes_for_scan(),
                respect_gitignore=config.respect_gitignore_for_scan(),
            ):
                continue
            seen.add(resolved)
            sources.append(
                SourceFile(
                    path=resolved,
                    language=language,
                    text=resolved.read_text(),
                )
            )
    return sources


def _build_index(
    repo_root: Path,
    source_roots: tuple[Path, ...],
    sources: Iterable[SourceFile],
) -> RepoIndex:
    source_list = tuple(sources)
    python_modules: dict[str, Path] = {}
    python_paths: dict[Path, str] = {}
    java_classes: dict[str, Path] = {}
    kotlin_packages: dict[str, set[Path]] = {}
    csharp_namespaces: dict[str, set[Path]] = {}

    for source in source_list:
        if source.language == "python":
            module = python_module_name(source.path, source_roots)
            if module is not None:
                python_modules[module] = source.path
                python_paths[source.path] = module
        elif source.language == "java":
            for name in java_class_names(source):
                java_classes[name] = source.path
        elif source.language == "kotlin":
            package_name = first_match(r"(?m)^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)", source.text)
            if package_name is not None:
                kotlin_packages.setdefault(package_name, set()).add(source.path)
        elif source.language == "csharp":
            namespace = first_match(
                r"(?m)^\s*namespace\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;?", source.text
            )
            if namespace is not None:
                csharp_namespaces.setdefault(namespace, set()).add(source.path)

    return RepoIndex(
        files=frozenset(source.path for source in source_list),
        source_roots=source_roots,
        python_modules=python_modules,
        python_paths=python_paths,
        java_classes=java_classes,
        kotlin_packages={k: frozenset(v) for k, v in kotlin_packages.items()},
        csharp_namespaces={k: frozenset(v) for k, v in csharp_namespaces.items()},
        go_module=read_go_module(repo_root),
    )
