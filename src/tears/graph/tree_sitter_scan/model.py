# @tear: 3
"""Shared data structures for tree-sitter scanning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceFile:
    path: Path
    language: str
    text: str


@dataclass(frozen=True)
class RepoIndex:
    files: frozenset[Path]
    source_roots: tuple[Path, ...]
    python_modules: Mapping[str, Path]
    python_paths: Mapping[Path, str]
    java_classes: Mapping[str, Path]
    kotlin_packages: Mapping[str, frozenset[Path]]
    csharp_namespaces: Mapping[str, frozenset[Path]]
    go_module: str | None


@dataclass(frozen=True)
class ParseContext:
    repo_root: Path
    source: SourceFile
    root_node: Any
    index: RepoIndex
