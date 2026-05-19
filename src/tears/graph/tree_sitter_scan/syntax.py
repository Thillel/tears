# @tear: 3
"""Small compatibility helpers around tree-sitter-language-pack nodes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from tree_sitter_language_pack import get_parser

from tears.graph.tree_sitter_scan.model import SourceFile


def parse_root(language: str, text: str) -> Any | None:
    try:
        parser = get_parser(language)
        tree = parser.parse(text)
        if tree is None:
            return None
        return tree.root_node()
    except Exception:
        return None


def walk(node: Any) -> Iterator[Any]:
    yield node
    child_count = cast(int, node.child_count())
    for index in range(child_count):
        child = node.child(index)
        if child is not None:
            yield from walk(child)


def top_level_children(node: Any) -> Iterator[Any]:
    child_count = cast(int, node.child_count())
    for index in range(child_count):
        child = node.child(index)
        if child is not None:
            yield child


def kind(node: Any) -> str:
    return cast(str, node.kind())


def node_text(source: SourceFile, node: Any) -> str:
    return source.text[cast(int, node.start_byte()) : cast(int, node.end_byte())]
