# @tear: 3
"""Claude Code PostToolUse hook for tears.

Demotes the `@tear` header in every file Claude writes or edits to `max_tear`
(default 3). This is the enforcement backstop: a human reviewing the resulting
diff must consciously re-promote the tier to attest that they read the code.
If they leave the demotion in place, that's the attestation that they didn't.

Invocation:
- As a Claude Code hook: receives a JSON payload on stdin describing the tool
  call (`{"tool_input": {"file_path": "..."}, ...}`). Register in
  `.claude/settings.json` under `hooks.PostToolUse`.
- Manually: `python -m tears.hook FILE [FILE ...]`. Useful for testing and
  bulk-demoting a list of files.

Scope:
- **Replacement is universal.** Any file with an existing `@tear: <digit>` header
  in any line-comment style (`#`, `//`, `--`, `;`) or block-comment style
  (`<!-- ... -->`, `/* ... */`) gets its digit rewritten to `max_tear`.
- **Insertion is type-specific.** A file *without* a header gets a new one
  inserted if its extension or filename is in `COMMENT_STYLES` /
  `FILENAME_STYLES` — covers most common dev files: Python, JS/TS, Go, Rust,
  C/C++/C#, Java, Kotlin, Swift, Ruby, Shell, TOML, YAML, INI, SQL, Lua,
  HTML/XML/Markdown/SVG, CSS/SCSS, Makefile, Dockerfile, .gitignore, .env, etc.
- **Multi-language scanning is still v2.** The hook covers many comment styles
  cheaply; the *scanner* (`tears`) still only enforces import rules on `.py`.
  See plan §1 for the asymmetric-scope rationale.

Behavior:
- **Matcher.** `.claude/settings.json` matches `Edit|Write|MultiEdit` only. Doesn't
  catch `NotebookEdit` or any future file-touching tool — extend the matcher if
  you need them.
- **One file per invocation.** `Edit`, `Write`, and `MultiEdit` each operate on a
  single `tool_input.file_path` (MultiEdit applies multiple edits to one file).
  The stdin parser returns a 1-element list. A future bulk-edit tool with a list
  payload would need parser changes.
- **Silent on bad input.** Empty stdin, malformed JSON, missing fields, paths
  that don't exist, and excluded paths all return 0 with no output. The hook
  never breaks Claude Code's flow.
- **Broken `.tears.toml` is non-fatal.** Falls back to `TearsConfig()` defaults so
  a malformed config can't stop Claude from editing files. The `tears` CLI
  itself still hard-fails on a broken config — only the hook is lenient.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

from tears.config import ConfigError, TearsConfig, load_config
from tears.exclude import is_excluded

# Match a line whose first non-whitespace token looks like a comment marker
# (one or more non-alphanumeric non-whitespace chars), followed by `@tear:` and
# digits. Captures the full prefix and the digits separately so we can rewrite
# the digit in place. The non-alphanumeric requirement keeps us from matching
# `@tear: 1` inside a string literal like `x = "@tear: 1"`.
LINE_HEADER_RE = re.compile(
    r"^([ \t]*[^A-Za-z0-9\s]+[ \t]*@tear:[ \t]*)(\d+)"
)
SHEBANG_RE = re.compile(r"^#!")
ENCODING_RE = re.compile(r"coding[=:]\s*[-\w.]+")

MAX_LINES = 5

# Extensions where we know how to *insert* a fresh header. Replacement works
# universally; only insertion needs the comment markers. Each value is
# (opener, closer) — `closer` is None for line comments (`#`, `//`, `--`, `;`)
# and a string for block comments (`<!-- ... -->`, `/* ... */`).
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

# Extensionless files keyed by name. Looked up only when `extension` is empty
# or unknown.
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


def apply_hook(
    content: str,
    *,
    max_tear: int = 3,
    extension: str = ".py",
    filename: str = "",
) -> str:
    """Return `content` with the `@tear` header rewritten to `max_tear`.

    Two steps:
    1. **Replacement (universal).** Scan the first 5 lines for any `@tear: <digit>`
       in a comment-like position. Replace each digit with `max_tear`. Preserves
       indentation, comment markers, trailing tokens (`-->`, `*/`), and line
       endings.
    2. **Insertion (type-specific).** If no header was found AND we know the
       comment syntax for the file (looked up by `extension` then `filename`),
       insert a new header. Insertion respects shebangs always; PEP 263 encoding
       declarations are also respected (universally — they look like `# coding:
       utf-8` and similar magic-comment patterns exist outside Python too).
    """
    lines = content.splitlines(keepends=True)

    replaced = False
    for i, line in enumerate(lines[:MAX_LINES]):
        new_line, n = LINE_HEADER_RE.subn(rf"\g<1>{max_tear}", line, count=1)
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
    lines.insert(insert_at, _format_header(style, max_tear) + ending)
    return "".join(lines)


def _resolve_style(extension: str, filename: str) -> CommentStyle | None:
    """Look up the comment style for a file. Extension wins; filename is a
    fallback for extensionless files (Makefile, Dockerfile, .gitignore)."""
    style = COMMENT_STYLES.get(extension.lower())
    if style is not None:
        return style
    return FILENAME_STYLES.get(filename)


def _format_header(style: CommentStyle, max_tear: int) -> str:
    """Render an `@tear: N` header in the appropriate comment style."""
    opener, closer = style
    if closer is None:
        return f"{opener} @tear: {max_tear}"
    return f"{opener} @tear: {max_tear} {closer}"


def process_file(
    path: Path,
    *,
    max_tear: int,
    exclude: list[str],
    repo_root: Path,
) -> bool:
    """Apply the hook to a single file. Returns True iff the file was modified.

    Excluded paths and missing files are silently skipped. The decision about
    *what* to do with the file (replace / insert / no-op) lives in `apply_hook`.
    """
    if not path.is_file():
        return False
    if is_excluded(path, repo_root, exclude):
        return False
    content = path.read_text()
    new_content = apply_hook(
        content, max_tear=max_tear, extension=path.suffix, filename=path.name
    )
    if new_content == content:
        return False
    path.write_text(new_content)
    return True


def main(argv: list[str] | None = None) -> int:
    """Entry point. Reads file paths from argv, or stdin JSON if none provided."""
    if argv is None:
        argv = sys.argv[1:]

    paths: list[Path] = [Path(arg) for arg in argv] if argv else _paths_from_stdin()
    if not paths:
        return 0

    repo_root = _find_repo_root(paths[0])
    try:
        config = load_config(repo_root)
    except ConfigError:
        # Broken config shouldn't break Claude Code. Fall back to defaults.
        config = TearsConfig()

    for path in paths:
        try:
            process_file(
                path,
                max_tear=config.max_tear,
                exclude=config.exclude,
                repo_root=repo_root,
            )
        except OSError:
            continue
    return 0


def _detect_line_ending(lines: list[str]) -> str:
    for line in lines:
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
    return "\n"


def _paths_from_stdin() -> list[Path]:
    raw = sys.stdin.read().strip()
    if not raw:
        return []
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    tool_input = cast(dict[str, Any], payload).get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    file_path = cast(dict[str, Any], tool_input).get("file_path")
    if isinstance(file_path, str):
        return [Path(file_path)]
    return []


def _find_repo_root(start: Path) -> Path:
    """Walk up from `start` for the repo root. Fall back to cwd.

    `.git/` wins over `.tears.toml` because nested configs exist legitimately
    (test fixtures, monorepo subprojects). The canonical repo marker is `.git/`.
    Only fall back to `.tears.toml` for repos that haven't been git-init'd yet.
    """
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


if __name__ == "__main__":
    raise SystemExit(main())
