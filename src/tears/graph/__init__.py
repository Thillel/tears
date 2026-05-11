# @tear: 3
"""Import graph abstraction.

The checker depends on the `ImportGraph` Protocol; concrete builders (currently
`grimp_builder.GrimpImportGraph`) implement it. This lets us swap builders
without touching checker logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol


class ImportGraph(Protocol):
    """Builders provide repo-wide tier and import data."""

    def files(self) -> Iterable[Path]:
        """All in-scope Python files in the repo (excluded files omitted)."""
        ...

    def tier_of(self, file: Path) -> int | None:
        """Tier from the file's @tear header, or None if missing/malformed."""
        ...

    def imports_of(self, file: Path) -> Iterable[Path]:
        """Files this file directly imports — resolved to repo files.

        Unresolvable targets (stdlib, third-party, dynamic) and excluded targets
        are omitted.
        """
        ...

    def importers_of(self, file: Path) -> Iterable[Path]:
        """Files that directly import this file. Builders may raise
        NotImplementedError if reverse-dep queries aren't needed by the checker.
        """
        ...


__all__ = ["ImportGraph"]
