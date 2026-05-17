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
- **Silent on bad input.** Empty stdin, malformed JSON, missing fields, paths
  that don't exist, and excluded paths all return 0 with no output.
- **Broken `.tears.toml` is non-fatal.** Falls back to `TearsConfig()` defaults.

The mutation logic lives in `tears.mutate`; this module is the entry point only.
`set_tear` and `process_file` are re-exported here for backward compatibility.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, cast

from tears.config import ConfigError, TearsConfig, load_config
from tears.mutate import find_repo_root, process_file


def main(argv: list[str] | None = None) -> int:
    """Entry point. Reads file paths from argv, or stdin JSON if none provided."""
    if argv is None:
        argv = sys.argv[1:]

    paths: list[Path] = [Path(arg) for arg in argv] if argv else _paths_from_stdin()
    return process_paths(paths)


def process_paths(paths: list[Path]) -> int:
    """Demote @tear headers for concrete paths."""
    if not paths:
        return 0

    repo_root = find_repo_root(paths[0])
    try:
        config = load_config(repo_root)
    except ConfigError:
        config = TearsConfig()

    for path in paths:
        try:
            process_file(
                path,
                tear=config.max_tear,
                exclude=config.exclude,
                repo_root=repo_root,
            )
        except OSError:
            continue
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
