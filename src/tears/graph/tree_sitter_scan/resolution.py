# @tear: 3
"""Import target resolution helpers for tree-sitter scanning."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from tears.graph.tree_sitter_scan.model import ParseContext, RepoIndex, SourceFile
from tears.languages import SOURCE_SUFFIXES_BY_LANGUAGE


def resolve_relative(importer: Path, specifier: str, language: str) -> Path | None:
    candidate = (importer.parent / specifier).resolve()
    suffixes = SOURCE_SUFFIXES_BY_LANGUAGE[language]
    candidates = [candidate]
    if candidate.suffix == "":
        candidates.extend(candidate.with_suffix(suffix) for suffix in suffixes)
    if language in {"typescript", "javascript"}:
        candidates.extend(candidate / f"index{suffix}" for suffix in suffixes)
    for possible in candidates:
        if possible.is_file():
            return possible.resolve()
    return None


def resolve_python_module(index: RepoIndex, module_name: str) -> Path | None:
    parts = module_name.split(".")
    for size in range(len(parts), 0, -1):
        target = index.python_modules.get(".".join(parts[:size]))
        if target is not None:
            return target
    return None


def resolve_python_from_import(
    ctx: ParseContext,
    module_name: str,
    imported_names: tuple[str, ...],
) -> Path | None:
    absolute_module = python_absolute_from_module(ctx, module_name)
    if absolute_module is None:
        return None
    for imported_name in imported_names:
        if imported_name == "*":
            continue
        target = resolve_python_module(ctx.index, f"{absolute_module}.{imported_name}")
        if target is not None:
            return target
    return resolve_python_module(ctx.index, absolute_module)


def python_absolute_from_module(ctx: ParseContext, module_name: str) -> str | None:
    if not module_name.startswith("."):
        return module_name
    importer_module = ctx.index.python_paths.get(ctx.source.path)
    if importer_module is None:
        return None
    package = (
        importer_module if ctx.source.path.name == "__init__.py" else parent_module(importer_module)
    )
    level = len(module_name) - len(module_name.lstrip("."))
    rest = module_name[level:]
    parts = package.split(".") if package else []
    if level > 1:
        if level - 1 > len(parts):
            return None
        parts = parts[: -(level - 1)]
    if rest:
        parts.extend(rest.split("."))
    return ".".join(parts)


def python_imported_modules(text: str) -> tuple[str, ...]:
    names = text.removeprefix("import").split(",")
    return tuple(name.strip().split()[0] for name in names if name.strip())


def python_imported_names(text: str) -> tuple[str, ...]:
    names = text.strip()
    if names.startswith("(") and names.endswith(")"):
        names = names[1:-1]
    return tuple(name.strip().split()[0] for name in names.split(",") if name.strip())


def python_module_name(path: Path, source_roots: tuple[Path, ...]) -> str | None:
    for source_root in source_roots:
        try:
            rel = path.relative_to(source_root)
        except ValueError:
            continue
        parts = rel.with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None
    return None


def parent_module(module_name: str) -> str:
    return module_name.rsplit(".", 1)[0] if "." in module_name else ""


def resolve_go_import(ctx: ParseContext, import_path: str) -> Path | None:
    module = ctx.index.go_module
    if module is None or not import_path.startswith(f"{module}/"):
        return None
    rel = import_path[len(module) + 1 :]
    directory = (ctx.repo_root / rel).resolve()
    if not directory.is_dir():
        return None
    for candidate in sorted(directory.glob("*.go")):
        resolved = candidate.resolve()
        if resolved in ctx.index.files:
            return resolved
    return None


def resolve_java_import(index: RepoIndex, import_name: str, *, is_static: bool) -> Path | None:
    name = import_name.removesuffix(".*")
    parts = name.split(".")
    prefixes = range(len(parts), 0, -1) if is_static else (len(parts),)
    for size in prefixes:
        candidate = ".".join(parts[:size])
        target = index.java_classes.get(candidate)
        if target is not None:
            return target
    return None


def resolve_kotlin_import(index: RepoIndex, import_name: str) -> Path | None:
    parts = import_name.removesuffix(".*").split(".")
    for size in range(len(parts), 0, -1):
        package_name = ".".join(parts[:size])
        targets = index.kotlin_packages.get(package_name)
        if targets is not None and len(targets) == 1:
            return next(iter(targets))
    return None


def resolve_csharp_using(index: RepoIndex, using_name: str, *, is_static: bool) -> Path | None:
    parts = using_name.split(".")
    prefixes = range(len(parts), 0, -1) if is_static else (len(parts),)
    for size in prefixes:
        namespace = ".".join(parts[:size])
        targets = index.csharp_namespaces.get(namespace)
        if targets is not None and len(targets) == 1:
            return next(iter(targets))
    return None


def java_class_names(source: SourceFile) -> Iterable[str]:
    package = first_match(r"(?m)^\s*package\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;", source.text)
    for match in re.finditer(
        r"\b(?:class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)", source.text
    ):
        name = match.group(1)
        yield f"{package}.{name}" if package is not None else name


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match is not None else None


def read_go_module(repo_root: Path) -> str | None:
    go_mod = repo_root / "go.mod"
    if not go_mod.is_file():
        return None
    return first_match(r"(?m)^\s*module\s+(\S+)", go_mod.read_text())
