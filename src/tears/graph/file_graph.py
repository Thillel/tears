# @tear: 3
"""In-memory file import graph implementation."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class FileImportGraph:
    """`ImportGraph` backed by explicit file/tier/import mappings."""

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
