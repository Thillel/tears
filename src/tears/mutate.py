# @tear: 3
"""Core tear-mutation primitives shared by the hook and CLI subcommands.

`set_tear` sets a @tear header to an arbitrary level (replacing an existing one
or inserting a new one). `process_file` is the filesystem boundary. `find_repo_root`
locates the nearest .git dir or .tears.toml.

The hook always calls process_file with tear=max_tear. The CLI subcommands
`tears up`, `tears down`, and `tears set` call it after validating direction.
`tears init` calls set_tear directly (it already holds the file content).
"""

from __future__ import annotations

from pathlib import Path

from tears.exclude import is_excluded
from tears.styles import (
    COMMENT_STYLES,
    ENCODING_RE,
    FILENAME_STYLES,
    LINE_HEADER_RE,
    MAX_HEADER_LINES,
    SHEBANG_RE,
    CommentStyle,
)


def set_tear(
    content: str,
    *,
    tear: int = 3,
    extension: str = ".py",
    filename: str = "",
) -> str:
    """Return `content` with the @tear header set to `tear`.

    Replaces any existing @tear line in the first 5 lines. If none is found and
    the file type is known (by extension or filename), inserts a new header
    respecting shebangs and PEP 263 encoding declarations.
    """
    lines = content.splitlines(keepends=True)

    replaced = False
    for i, line in enumerate(lines[:MAX_HEADER_LINES]):
        new_line, n = LINE_HEADER_RE.subn(rf"\g<1>{tear}", line, count=1)
        if n:
            lines[i] = new_line
            replaced = True

    if replaced:
        return "".join(lines)

    style = _resolve_style(extension, filename)
    if style is None:
        return content

    insert_at = 0
    if lines and SHEBANG_RE.match(lines[0]):
        insert_at = 1
    if insert_at < len(lines) and ENCODING_RE.search(lines[insert_at]):
        insert_at += 1

    ending = _detect_line_ending(lines)
    lines.insert(insert_at, _format_header(style, tear) + ending)
    return "".join(lines)


def process_file(
    path: Path,
    *,
    tear: int,
    exclude: list[str],
    repo_root: Path,
) -> bool:
    """Apply `set_tear` to a single file. Returns True iff the file was modified."""
    if not path.is_file():
        return False
    if is_excluded(path, repo_root, exclude):
        return False
    content = path.read_text()
    new_content = set_tear(content, tear=tear, extension=path.suffix, filename=path.name)
    if new_content == content:
        return False
    path.write_text(new_content)
    return True


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` to find the repo root (.git dir wins, then .tears.toml)."""
    here = start.resolve()
    if here.is_file():
        here = here.parent
    ancestors = (here, *here.parents)
    for ancestor in ancestors:
        if (ancestor / ".git").exists():
            return ancestor
    for ancestor in ancestors:
        if (ancestor / ".tears.toml").exists():
            return ancestor
    return Path.cwd()


def _resolve_style(extension: str, filename: str) -> CommentStyle | None:
    style = COMMENT_STYLES.get(extension.lower())
    if style is not None:
        return style
    return FILENAME_STYLES.get(filename)


def _format_header(style: CommentStyle, tear: int) -> str:
    opener, closer = style
    if closer is None:
        return f"{opener} @tear: {tear}"
    return f"{opener} @tear: {tear} {closer}"


def _detect_line_ending(lines: list[str]) -> str:
    for line in lines:
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
    return "\n"
