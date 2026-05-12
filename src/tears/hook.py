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

Behavior:
- **Matcher.** `.claude/settings.json` matches `Edit|Write|MultiEdit` only. Doesn't
  catch `NotebookEdit` or any future file-touching tool — extend the matcher if
  you need them.
- **One file per invocation.** `Edit`, `Write`, and `MultiEdit` each operate on a
  single `tool_input.file_path` (MultiEdit applies multiple edits to one file).
  The stdin parser returns a 1-element list. A future bulk-edit tool with a list
  payload would need parser changes.
- **Silent on bad input.** Empty stdin, malformed JSON, missing fields, paths
  that don't exist, non-`.py` files, and excluded paths all return 0 with no
  output. The hook never breaks Claude Code's flow.
- **Broken `.tears.yml` is non-fatal.** Falls back to `TearsConfig()` defaults so
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

# Loose match: anything that looks like a @tear header, even malformed values.
# Captures the leading indentation so we preserve it when rewriting.
HEADER_LIKE_RE = re.compile(r"^([ \t]*)#[ \t]*@tear:.*$")
SHEBANG_RE = re.compile(r"^#!")
ENCODING_RE = re.compile(r"coding[=:]\s*[-\w.]+")
LINE_ENDING_RE = re.compile(r"(\r?\n)$")

MAX_LINES = 5


def apply_hook(content: str, *, max_tear: int = 3) -> str:
    """Return `content` with the `@tear` header rewritten to `max_tear`.

    - Replaces *every* `@tear`-looking line in the first 5 lines (idempotent +
      collapses any duplicates to a consistent value).
    - If no header is present, inserts one after any shebang and any PEP 263
      encoding declaration. Otherwise at line 1.
    - Preserves indentation and line endings of existing headers.
    """
    lines = content.splitlines(keepends=True)
    header_indices = [
        i
        for i, line in enumerate(lines[:MAX_LINES])
        if HEADER_LIKE_RE.match(line.rstrip("\r\n"))
    ]

    if header_indices:
        for idx in header_indices:
            line = lines[idx]
            ending_match = LINE_ENDING_RE.search(line)
            ending = ending_match.group(1) if ending_match else ""
            indent_match = HEADER_LIKE_RE.match(line.rstrip("\r\n"))
            indent = indent_match.group(1) if indent_match else ""
            lines[idx] = f"{indent}# @tear: {max_tear}{ending}"
        return "".join(lines)

    insert_at = 0
    if lines and SHEBANG_RE.match(lines[0]):
        insert_at = 1
    if insert_at < len(lines) and ENCODING_RE.search(lines[insert_at]):
        insert_at += 1

    ending = _detect_line_ending(lines)
    lines.insert(insert_at, f"# @tear: {max_tear}{ending}")
    return "".join(lines)


def process_file(
    path: Path,
    *,
    max_tear: int,
    exclude: list[str],
    repo_root: Path,
) -> bool:
    """Apply the hook to a single file. Returns True iff the file was modified."""
    if not path.is_file() or path.suffix != ".py":
        return False
    if is_excluded(path, repo_root, exclude):
        return False
    content = path.read_text()
    new_content = apply_hook(content, max_tear=max_tear)
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

    `.git/` wins over `.tears.yml` because nested `.tears.yml` files exist
    legitimately (test fixtures, monorepo subprojects). The canonical repo
    marker is `.git/`. Only fall back to `.tears.yml` for repos that haven't
    been git-init'd yet.
    """
    here = start.resolve()
    if here.is_file():
        here = here.parent
    ancestors = (here, *here.parents)
    for ancestor in ancestors:
        if (ancestor / ".git").exists():
            return ancestor
    for ancestor in ancestors:
        if (ancestor / ".tears.yml").exists():
            return ancestor
    return Path.cwd()


if __name__ == "__main__":
    raise SystemExit(main())
