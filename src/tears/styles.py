# @tear: 2
"""Comment-style lookup tables for @tear header insertion.

`COMMENT_STYLES` keys on file extension; `FILENAME_STYLES` keys on bare filename
for extensionless files (Makefile, Dockerfile, etc.). Each value is
`(opener, closer)` — `closer` is None for line comments, a string for block comments.
"""

from __future__ import annotations

import re

LINE_HEADER_RE = re.compile(r"^([ \t]*[^A-Za-z0-9\s]+[ \t]*@tear:[ \t]*)(\d+)")
SHEBANG_RE = re.compile(r"^#!")
ENCODING_RE = re.compile(r"coding[=:]\s*[-\w.]+")

MAX_HEADER_LINES = 5

CommentStyle = tuple[str, str | None]

COMMENT_STYLES: dict[str, CommentStyle] = {
    # Hash line comment
    ".py": ("#", None),
    ".rb": ("#", None),
    ".pl": ("#", None),
    ".sh": ("#", None),
    ".bash": ("#", None),
    ".zsh": ("#", None),
    ".fish": ("#", None),
    ".toml": ("#", None),
    ".yml": ("#", None),
    ".yaml": ("#", None),
    ".r": ("#", None),
    ".ex": ("#", None),
    ".exs": ("#", None),
    # Double-slash line comment
    ".js": ("//", None),
    ".mjs": ("//", None),
    ".cjs": ("//", None),
    ".ts": ("//", None),
    ".tsx": ("//", None),
    ".jsx": ("//", None),
    ".go": ("//", None),
    ".rs": ("//", None),
    ".java": ("//", None),
    ".kt": ("//", None),
    ".swift": ("//", None),
    ".c": ("//", None),
    ".cpp": ("//", None),
    ".cc": ("//", None),
    ".cxx": ("//", None),
    ".h": ("//", None),
    ".hpp": ("//", None),
    ".cs": ("//", None),
    ".scala": ("//", None),
    ".dart": ("//", None),
    ".zig": ("//", None),
    # Double-dash line comment
    ".sql": ("--", None),
    ".lua": ("--", None),
    ".hs": ("--", None),
    ".elm": ("--", None),
    # Semicolon line comment
    ".ini": (";", None),
    ".cfg": (";", None),
    ".clj": (";", None),
    ".lisp": (";", None),
    # HTML / XML / Markdown block comment
    ".html": ("<!--", "-->"),
    ".htm": ("<!--", "-->"),
    ".xml": ("<!--", "-->"),
    ".md": ("<!--", "-->"),
    ".markdown": ("<!--", "-->"),
    ".svg": ("<!--", "-->"),
    # CSS block comment
    ".css": ("/*", "*/"),
    ".scss": ("/*", "*/"),
    ".less": ("/*", "*/"),
}

FILENAME_STYLES: dict[str, CommentStyle] = {
    "Makefile": ("#", None),
    "Dockerfile": ("#", None),
    "Rakefile": ("#", None),
    "Gemfile": ("#", None),
    ".gitignore": ("#", None),
    ".gitattributes": ("#", None),
    ".dockerignore": ("#", None),
    ".env": ("#", None),
    ".notears": ("#", None),
}
