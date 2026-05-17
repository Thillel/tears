# @tear: 3
"""Codex PostToolUse hook entry point for tears.

Codex sends provider-specific JSON on stdin. For file edits performed through
`apply_patch`, the changed paths are embedded in `tool_input.command`; this
module extracts those paths and delegates the actual mutation to `tears.hook`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

from tears.hook import process_paths

PATCH_PATH_RE = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$")


def main() -> int:
    """Read a Codex hook payload from stdin and demote touched files."""
    paths = _paths_from_stdin()
    return process_paths(paths)


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
    tool_name = cast(dict[str, Any], payload).get("tool_name")
    tool_input = cast(dict[str, Any], payload).get("tool_input")
    if tool_name != "apply_patch" or not isinstance(tool_input, dict):
        return []
    command = cast(dict[str, Any], tool_input).get("command")
    if not isinstance(command, str):
        return []
    return paths_from_apply_patch(command)


def paths_from_apply_patch(command: str) -> list[Path]:
    paths: list[Path] = []
    for line in command.splitlines():
        match = PATCH_PATH_RE.match(line)
        if match is not None:
            paths.append(Path(match.group(1)))
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
