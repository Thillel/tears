# @tear: 3
"""`tears` — CLI entry point."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from importlib.metadata import version as _pkg_version
from pathlib import Path

from tears.config import CONFIG_FILENAME, ConfigError, TearsConfig, load_config
from tears.exclude import should_skip_path
from tears.header import parse_tear_level_for_path
from tears.languages import supported_languages_text
from tears.mutate import find_repo_root, process_file
from tears.scan import run_scan

_SUBCOMMANDS = frozenset({"up", "down", "set", "init"})

_DEFAULT_TOML = f"""# @tear: 3
max_tear = 3
respect_gitignore = true

# Supported languages: {supported_languages_text()}
languages = ["python"]

# Soft trial mode: existing files without @tear headers are treated as reviewed.
# Full adoption:
#   1. Run: tears set . --tear 1 --missing-only
#   2. Change default_tear to 3, or remove it and set missing_header = "error".
default_tear = 1
missing_header = "warn"

# Tell tears where your importable Python packages live.
# [imports]
# source_roots = ["src"]

# Require sensitive directories to stay at stricter tiers.
# [directory_requirements]
# "src/auth" = 0
# "src/api" = 1

# Give specific directories an artificial import budget.
# [artificial_tears]
# "tests/unit" = 3

# Configure scan-only exclusions.
# [scan]
# exclude = ["fixtures/**"]
# respect_gitignore = false

# Configure automatic @tear header marking by hooks and set/up/down.
# [mutate]
# exclude = ["vendor/**"]
# respect_gitignore = false
"""


@dataclass(frozen=True)
class _CurrentTier:
    explicit: int | None
    effective: int
    defaulted: bool


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    first_positional = next((a for a in argv if not a.startswith("-")), None)
    if first_positional in _SUBCOMMANDS:
        return _dispatch(argv)
    return _cmd_scan(argv)


def _dispatch(argv: list[str]) -> int:
    cmd, rest = argv[0], argv[1:]
    if cmd == "up":
        return _cmd_up(rest)
    if cmd == "down":
        return _cmd_down(rest)
    if cmd == "set":
        return _cmd_set(rest)
    if cmd == "init":
        return _cmd_init(rest)
    return 2  # unreachable


def _cmd_scan(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="tears",
        description="Tiered Enforcement, Authorship Review System — scan a repo.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Scan root to load config from and scan (defaults to the current directory).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_pkg_version('tears-cli')}",
    )
    parser.add_argument(
        "--default-tear",
        type=int,
        metavar="N",
        dest="default_tear",
        help="Treat files without a @tear header as tier N (overrides config).",
    )
    args = parser.parse_args(argv)

    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    repo_root = Path(args.path).resolve()
    try:
        report, output = run_scan(repo_root, color=color, default_tear=args.default_tear)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(output)
    return report.exit_code


def _parse_mutate_argv(
    argv: list[str], prog: str, desc: str
) -> tuple[Path, int, TearsConfig, Path, bool] | int:
    """Parse path + --tear, load config. Returns (path, target, config, repo_root) or exit code."""
    parser = argparse.ArgumentParser(prog=prog, description=desc)
    parser.add_argument("path", type=Path, help="File or directory to mark.")
    parser.add_argument("--tear", type=int, required=True, metavar="N", help="Target tear level.")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only tag files that do not already have a @tear header.",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    path = args.path.resolve()
    repo_root = find_repo_root(path)
    try:
        config = load_config(repo_root)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    target = args.tear
    if not 0 <= target <= config.max_tear:
        print(f"error: tear {target} out of range [0, {config.max_tear}]", file=sys.stderr)
        return 2

    return path, target, config, repo_root, bool(args.missing_only)


def _cmd_up(argv: list[str]) -> int:
    ctx = _parse_mutate_argv(
        argv,
        "tears up",
        "Mark a file or directory as less trusted (tear number goes up).",
    )
    if isinstance(ctx, int):
        return ctx
    path, target, config, repo_root, missing_only = ctx

    if path.is_file():
        return _apply_up_file(
            path,
            target,
            config,
            repo_root,
            bulk=False,
            missing_only=missing_only,
        )

    for file_path in _walk(path, config, repo_root):
        _apply_up_file(
            file_path,
            target,
            config,
            repo_root,
            bulk=True,
            missing_only=missing_only,
        )
    return 0


def _apply_up_file(
    path: Path,
    target: int,
    config: TearsConfig,
    repo_root: Path,
    *,
    bulk: bool,
    missing_only: bool,
) -> int:
    if _should_skip_mutation(path, config, repo_root):
        return 0
    content = _read_text_or_skip(path)
    if content is None:
        return 0
    current = _current_tier(path, content, config, repo_root)
    if missing_only and current.explicit is not None:
        return 0
    if target < current.effective:
        if not bulk:
            print(
                f"error: {path.name} is already at tear {_tier_label(current)}; "
                f"to lower the number use 'tears down'",
                file=sys.stderr,
            )
            return 1
        return 0  # silently skip in bulk mode
    changed = process_file(
        path, tear=target, exclude=config.excludes_for_mutation(), repo_root=repo_root
    )
    if changed:
        prev = str(current.explicit) if current.explicit is not None else "∅"
        print(f"{path.name}  {prev} → {target}")
    return 0


def _cmd_down(argv: list[str]) -> int:
    ctx = _parse_mutate_argv(
        argv,
        "tears down",
        "Mark a file or directory as more trusted (tear number goes down).",
    )
    if isinstance(ctx, int):
        return ctx
    path, target, config, repo_root, missing_only = ctx

    if path.is_file():
        return _apply_down_file(
            path,
            target,
            config,
            repo_root,
            bulk=False,
            missing_only=missing_only,
        )

    for file_path in _walk(path, config, repo_root):
        _apply_down_file(
            file_path,
            target,
            config,
            repo_root,
            bulk=True,
            missing_only=missing_only,
        )
    return 0


def _apply_down_file(
    path: Path,
    target: int,
    config: TearsConfig,
    repo_root: Path,
    *,
    bulk: bool,
    missing_only: bool,
) -> int:
    if _should_skip_mutation(path, config, repo_root):
        return 0
    content = _read_text_or_skip(path)
    if content is None:
        return 0
    current = _current_tier(path, content, config, repo_root)
    if missing_only and current.explicit is not None:
        return 0
    if target >= current.effective:
        if not bulk:
            print(
                f"error: {path.name} is at tear {_tier_label(current)}; "
                "to raise the number use 'tears up'",
                file=sys.stderr,
            )
            return 1
        return 0  # silently skip in bulk mode
    changed = process_file(
        path, tear=target, exclude=config.excludes_for_mutation(), repo_root=repo_root
    )
    if changed:
        prev = str(current.explicit) if current.explicit is not None else "∅"
        print(f"{path.name}  {prev} → {target}")
    return 0


def _cmd_set(argv: list[str]) -> int:
    ctx = _parse_set_argv(argv)
    if isinstance(ctx, int):
        return ctx
    path, target, config, repo_root, missing_only = ctx

    if path.is_file():
        return _apply_set_file(path, target, config, repo_root, missing_only=missing_only)

    for file_path in _walk(path, config, repo_root):
        _apply_set_file(file_path, target, config, repo_root, missing_only=missing_only)
    return 0


def _parse_set_argv(argv: list[str]) -> tuple[Path, int, TearsConfig, Path, bool] | int:
    parser = argparse.ArgumentParser(
        prog="tears set",
        description="Set a file or directory to an exact tear level (no direction check).",
    )
    parser.add_argument("path", type=Path, help="File or directory to mark.")
    parser.add_argument("--tear", type=int, required=True, metavar="N", help="Target tear level.")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only tag files that do not already have a @tear header.",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    path = args.path.resolve()
    repo_root = find_repo_root(path)
    try:
        config = load_config(repo_root)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    target = args.tear
    if not 0 <= target <= config.max_tear:
        print(f"error: tear {target} out of range [0, {config.max_tear}]", file=sys.stderr)
        return 2

    return path, target, config, repo_root, bool(args.missing_only)


def _apply_set_file(
    path: Path,
    target: int,
    config: TearsConfig,
    repo_root: Path,
    *,
    missing_only: bool,
) -> int:
    if _should_skip_mutation(path, config, repo_root):
        return 0
    content = _read_text_or_skip(path)
    if content is None:
        return 0
    current = _current_tier(path, content, config, repo_root)
    if missing_only and current.explicit is not None:
        return 0
    changed = process_file(
        path, tear=target, exclude=config.excludes_for_mutation(), repo_root=repo_root
    )
    if changed:
        prev = str(current.explicit) if current.explicit is not None else "∅"
        print(f"{path.name}  {prev} → {target}")
    return 0


def _walk(root: Path, config: TearsConfig, repo_root: Path) -> list[Path]:
    results: list[Path] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if ".git" in file_path.parts or "__pycache__" in file_path.parts:
            continue
        if _should_skip_mutation(file_path, config, repo_root):
            continue
        results.append(file_path)
    return results


def _should_skip_mutation(path: Path, config: TearsConfig, repo_root: Path) -> bool:
    return should_skip_path(
        path,
        repo_root,
        patterns=config.excludes_for_mutation(),
        respect_gitignore=config.respect_gitignore_for_mutation(),
    )


def _read_text_or_skip(path: Path) -> str | None:
    try:
        return path.read_text()
    except UnicodeDecodeError:
        return None
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _current_tier(path: Path, content: str, config: TearsConfig, repo_root: Path) -> _CurrentTier:
    explicit = parse_tear_level_for_path(path, content, max_tear=config.max_tear)
    if explicit is not None:
        return _CurrentTier(explicit=explicit, effective=explicit, defaulted=False)
    effective, defaulted = config.resolve_missing_tier(_relative_posix(path, repo_root))
    return _CurrentTier(explicit=None, effective=effective, defaulted=defaulted)


def _tier_label(current: _CurrentTier) -> str:
    if current.explicit is not None:
        return str(current.explicit)
    return f"∅ (implicit {current.effective})"


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _cmd_init(argv: list[str]) -> int:
    """Scaffold .tears.toml without rewriting source files."""
    parser = argparse.ArgumentParser(
        prog="tears init",
        description="Scaffold .tears.toml for low-churn adoption.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Repo root (default: .).",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    repo_root = args.path.resolve()

    config_path = repo_root / CONFIG_FILENAME
    if not config_path.exists():
        config_path.write_text(_DEFAULT_TOML)
        print(f"created {config_path.name}")
    else:
        print(f"{config_path.name} already exists, skipping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
