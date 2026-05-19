# @tear: 3
"""Language-specific import extraction strategies."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from tears.graph.tree_sitter_scan.model import ParseContext
from tears.graph.tree_sitter_scan.resolution import (
    python_imported_modules,
    python_imported_names,
    resolve_csharp_using,
    resolve_go_import,
    resolve_java_import,
    resolve_kotlin_import,
    resolve_python_from_import,
    resolve_python_module,
    resolve_relative,
)
from tears.graph.tree_sitter_scan.syntax import kind, node_text, top_level_children, walk

Extractor = Callable[[ParseContext], Iterable[Path]]


def extract_python(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        node_kind = kind(node)
        text = node_text(ctx.source, node)
        if node_kind == "import_statement":
            for module_name in python_imported_modules(text):
                target = resolve_python_module(ctx.index, module_name)
                if target is not None:
                    yield target
        elif node_kind == "import_from_statement":
            match = re.match(
                r"\s*from\s+([.\w]+)\s+import\s+(.+)",
                text,
                flags=re.DOTALL,
            )
            if match is None:
                continue
            target = resolve_python_from_import(
                ctx,
                match.group(1),
                python_imported_names(match.group(2)),
            )
            if target is not None:
                yield target


def extract_js_like(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        node_kind = kind(node)
        text = node_text(ctx.source, node)
        specifiers: list[str] = []
        if node_kind in {"import_statement", "export_statement"}:
            from_match = re.search(r"\bfrom\s*(['\"])([^'\"]+)\1", text)
            if from_match is not None:
                specifiers.append(from_match.group(2))
            side_effect_match = re.search(r"^\s*import\s*(['\"])([^'\"]+)\1", text)
            if side_effect_match is not None:
                specifiers.append(side_effect_match.group(2))
        elif node_kind == "call_expression":
            specifiers.extend(
                match.group(2)
                for match in re.finditer(r"\b(?:require|import)\s*\(\s*(['\"])([^'\"]+)\1", text)
            )

        for specifier in specifiers:
            target = resolve_relative(ctx.source.path, specifier, ctx.source.language)
            if target is not None:
                yield target


def extract_c_like(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        if kind(node) != "preproc_include":
            continue
        match = re.search(r'#\s*include\s*"([^"]+)"', node_text(ctx.source, node))
        if match is None:
            continue
        target = resolve_relative(ctx.source.path, match.group(1), ctx.source.language)
        if target is not None:
            yield target


def extract_dart(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        if kind(node) not in {"import_or_export", "part_directive"}:
            continue
        match = re.search(
            r"\b(?:import|export|part)\s*(['\"])([^'\"]+)\1",
            node_text(ctx.source, node),
        )
        if match is None:
            continue
        target = resolve_relative(ctx.source.path, match.group(2), "dart")
        if target is not None:
            yield target


def extract_go(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        if kind(node) != "import_spec":
            continue
        match = re.search(r"(['\"])([^'\"]+)\1", node_text(ctx.source, node))
        if match is None:
            continue
        target = resolve_go_import(ctx, match.group(2))
        if target is not None:
            yield target


def extract_java(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        if kind(node) != "import_declaration":
            continue
        text = node_text(ctx.source, node)
        match = re.search(r"\bimport\s+(static\s+)?([A-Za-z_][A-Za-z0-9_.*]*)\s*;", text)
        if match is None:
            continue
        target = resolve_java_import(
            ctx.index, match.group(2), is_static=match.group(1) is not None
        )
        if target is not None:
            yield target


def extract_kotlin(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        if kind(node) != "import_header":
            continue
        match = re.search(
            r"\bimport\s+([A-Za-z_][A-Za-z0-9_.]*)(?:\s+as\s+\w+)?",
            node_text(ctx.source, node),
        )
        if match is None:
            continue
        target = resolve_kotlin_import(ctx.index, match.group(1))
        if target is not None:
            yield target


def extract_csharp(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        if kind(node) != "using_directive":
            continue
        text = node_text(ctx.source, node)
        match = re.search(r"\busing\s+(static\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*;", text)
        if match is None:
            continue
        target = resolve_csharp_using(
            ctx.index, match.group(2), is_static=match.group(1) is not None
        )
        if target is not None:
            yield target


def extract_php(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        if kind(node) not in {
            "require_expression",
            "require_once_expression",
            "include_expression",
            "include_once_expression",
        }:
            continue
        text = node_text(ctx.source, node)
        for match in re.finditer(r"(['\"])([^'\"]+\.php)\1", text):
            specifier = match.group(2).lstrip("/") if "__DIR__" in text else match.group(2)
            target = resolve_relative(ctx.source.path, specifier, "php")
            if target is not None:
                yield target


def extract_ruby(ctx: ParseContext) -> Iterable[Path]:
    for node in walk(ctx.root_node):
        if kind(node) != "call":
            continue
        text = node_text(ctx.source, node)
        match = re.search(r"\brequire_relative\s*(?:\(?\s*)?(['\"])([^'\"]+)\1", text)
        if match is None:
            continue
        target = resolve_relative(ctx.source.path, match.group(2), "ruby")
        if target is not None:
            yield target


def extract_rust(ctx: ParseContext) -> Iterable[Path]:
    pending_path: str | None = None
    for node in top_level_children(ctx.root_node):
        text = node_text(ctx.source, node)
        if kind(node) == "attribute_item":
            pending_match = re.search(r"#\[\s*path\s*=\s*\"([^\"]+)\"\s*\]", text)
            pending_path = pending_match.group(1) if pending_match is not None else None
            continue
        if kind(node) != "mod_item":
            pending_path = None
            continue
        if "{" in text:
            pending_path = None
            continue
        if pending_path is not None:
            target = resolve_relative(ctx.source.path, pending_path, "rust")
            pending_path = None
            if target is not None:
                yield target
            continue
        match = re.search(r"\bmod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", text)
        if match is None:
            continue
        for candidate in (
            ctx.source.path.parent / f"{match.group(1)}.rs",
            ctx.source.path.parent / match.group(1) / "mod.rs",
        ):
            resolved = candidate.resolve()
            if resolved in ctx.index.files:
                yield resolved
                break


EXTRACTORS: Mapping[str, Extractor] = {
    "python": extract_python,
    "typescript": extract_js_like,
    "javascript": extract_js_like,
    "c": extract_c_like,
    "cpp": extract_c_like,
    "dart": extract_dart,
    "go": extract_go,
    "java": extract_java,
    "kotlin": extract_kotlin,
    "csharp": extract_csharp,
    "php": extract_php,
    "ruby": extract_ruby,
    "rust": extract_rust,
}
