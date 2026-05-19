# @tear: 3
"""Parse the `@tear` header from a source file."""

from __future__ import annotations

import re
from pathlib import Path

from tears.styles import COMMENT_STYLES, FILENAME_STYLES, CommentStyle

MAX_LINES = 5


def parse_tear_level(content: str, *, max_tear: int = 3) -> int | None:
    """Return the worst valid Python/hash-style tier in the first 5 lines, else None."""
    return _parse_tear_level_with_style(content, ("#", None), max_tear=max_tear)


def parse_tear_level_for_path(path: Path, content: str, *, max_tear: int = 3) -> int | None:
    """Return the worst valid tier using the comment style for `path`.

    A valid header is a line whose first non-whitespace token is the file type's
    configured comment opener, followed by `@tear: <digits>`, where digits parse as an
    integer in [0, max_tear]. Out-of-range values are treated as malformed. `1.5` and
    `-1` do not match.
    """
    style = _comment_style_for_path(path)
    if style is None:
        return None
    return _parse_tear_level_with_style(content, style, max_tear=max_tear)


def _parse_tear_level_with_style(
    content: str,
    style: CommentStyle,
    *,
    max_tear: int,
) -> int | None:
    header_re = _header_re_for_style(style)
    worst: int | None = None
    for line in content.splitlines()[:MAX_LINES]:
        match = header_re.match(line)
        if match is None:
            continue
        value = int(match.group(1))
        if value < 0 or value > max_tear:
            continue
        if worst is None or value > worst:
            worst = value
    return worst


def _comment_style_for_path(path: Path) -> CommentStyle | None:
    return FILENAME_STYLES.get(path.name) or COMMENT_STYLES.get(path.suffix.lower())


def _header_re_for_style(style: CommentStyle) -> re.Pattern[str]:
    opener, closer = style
    opener_re = re.escape(opener)
    closer_re = "" if closer is None else rf"(?:[ \t]*{re.escape(closer)})?"
    return re.compile(rf"^[ \t]*{opener_re}[ \t]*@tear:[ \t]*(\d+)(?![\w.]){closer_re}")
