# @tear: 3
"""Parse the `@tear` header from a Python source file."""

from __future__ import annotations

import re

HEADER_RE = re.compile(r"^[ \t]*#[ \t]*@tear:[ \t]*(\d+)(?![\w.])")

MAX_LINES = 5


def parse_tear_level(content: str, *, max_tear: int = 3) -> int | None:
    """Return the worst (highest) valid tier found in the first 5 lines, else None.

    A valid header is a line whose first non-whitespace token is `#`, followed by
    `@tear: <digits>`, where digits parse as an integer in [0, max_tear]. Out-of-range
    values are treated as malformed (not as that integer). `1.5` and `-1` do not match.
    """
    worst: int | None = None
    for line in content.splitlines()[:MAX_LINES]:
        match = HEADER_RE.match(line)
        if match is None:
            continue
        value = int(match.group(1))
        if value < 0 or value > max_tear:
            continue
        if worst is None or value > worst:
            worst = value
    return worst
