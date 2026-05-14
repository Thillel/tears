# @tear: 3
"""`tears` — CLI entry point."""

from __future__ import annotations

import argparse
import os
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

from tears.config import ConfigError, TearsConfig, load_config
from tears.exclude import is_excluded
from tears.header import parse_tear_level
from tears.mutate import find_repo_root, process_file, set_tear
from tears.scan import run_scan

_SUBCOMMANDS = frozenset({"up", "down", "set", "init"})

_DEFAULT_TOML = "# @tear: 3\nmax_tear = 3\n"


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
        help="Path to scan (defaults to the current directory).",
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
) -> tuple[Path, int, TearsConfig, Path] | int:
    """Parse path + --tear, load config. Returns (path, target, config, repo_root) or exit code."""
    parser = argparse.ArgumentParser(prog=prog, description=desc)
    parser.add_argument("path", type=Path, help="File or directory to mark.")
    parser.add_argument("--tear", type=int, required=True, metavar="N", help="Target tear level.")
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

    return path, target, config, repo_root


def _cmd_up(argv: list[str]) -> int:
    ctx = _parse_mutate_argv(
        argv,
        "tears up",
        "Mark a file or directory as less trusted (tear number goes up).",
    )
    if isinstance(ctx, int):
        return ctx
    path, target, config, repo_root = ctx

    if path.is_file():
        return _apply_up_file(path, target, config, repo_root, bulk=False)

    for file_path in _walk(path, config, repo_root):
        _apply_up_file(file_path, target, config, repo_root, bulk=True)
    return 0


def _apply_up_file(
    path: Path, target: int, config: TearsConfig, repo_root: Path, *, bulk: bool
) -> int:
    try:
        content = path.read_text()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    current = parse_tear_level(content, max_tear=config.max_tear)
    if current is not None and target < current:
        if not bulk:
            print(
                f"error: {path.name} is already at tear {current}; "
                f"to lower the number use 'tears down'",
                file=sys.stderr,
            )
            return 1
        return 0  # silently skip in bulk mode
    changed = process_file(path, tear=target, exclude=config.exclude, repo_root=repo_root)
    if changed:
        prev = str(current) if current is not None else "∅"
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
    path, target, config, repo_root = ctx

    if path.is_file():
        return _apply_down_file(path, target, config, repo_root, bulk=False)

    for file_path in _walk(path, config, repo_root):
        _apply_down_file(file_path, target, config, repo_root, bulk=True)
    return 0


def _apply_down_file(
    path: Path, target: int, config: TearsConfig, repo_root: Path, *, bulk: bool
) -> int:
    try:
        content = path.read_text()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    current = parse_tear_level(content, max_tear=config.max_tear)
    effective_current = current if current is not None else config.max_tear
    if target >= effective_current:
        if not bulk:
            noun = str(current) if current is not None else f"∅ (implicit {config.max_tear})"
            print(
                f"error: {path.name} is at tear {noun}; to raise the number use 'tears up'",
                file=sys.stderr,
            )
            return 1
        return 0  # silently skip in bulk mode
    changed = process_file(path, tear=target, exclude=config.exclude, repo_root=repo_root)
    if changed:
        prev = str(current) if current is not None else "∅"
        print(f"{path.name}  {prev} → {target}")
    return 0


def _cmd_set(argv: list[str]) -> int:
    ctx = _parse_mutate_argv(
        argv,
        "tears set",
        "Set a file or directory to an exact tear level (no direction check).",
    )
    if isinstance(ctx, int):
        return ctx
    path, target, config, repo_root = ctx

    if path.is_file():
        return _apply_set_file(path, target, config, repo_root)

    for file_path in _walk(path, config, repo_root):
        _apply_set_file(file_path, target, config, repo_root)
    return 0


def _apply_set_file(path: Path, target: int, config: TearsConfig, repo_root: Path) -> int:
    try:
        content = path.read_text()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    current = parse_tear_level(content, max_tear=config.max_tear)
    changed = process_file(path, tear=target, exclude=config.exclude, repo_root=repo_root)
    if changed:
        prev = str(current) if current is not None else "∅"
        print(f"{path.name}  {prev} → {target}")
    return 0


def _walk(root: Path, config: TearsConfig, repo_root: Path) -> list[Path]:
    results: list[Path] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if ".git" in file_path.parts or "__pycache__" in file_path.parts:
            continue
        if is_excluded(file_path, repo_root, config.exclude):
            continue
        results.append(file_path)
    return results


def _cmd_init(argv: list[str]) -> int:
    """Scaffold .tears.toml and tag all headerless files."""
    parser = argparse.ArgumentParser(
        prog="tears init",
        description="Scaffold .tears.toml and insert @tear headers on untagged files.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Repo root (default: .).",
    )
    parser.add_argument(
        "--tear",
        type=int,
        default=None,
        metavar="N",
        help="Tear level to assign (default: max_tear from config).",
    )
    args = parser.parse_args(argv)

    repo_root = args.path.resolve()

    config_path = repo_root / ".tears.toml"
    if not config_path.exists():
        config_path.write_text(_DEFAULT_TOML)
        print(f"created {config_path.name}")
    else:
        print(f"{config_path.name} already exists, skipping")

    try:
        config = load_config(repo_root)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.tear is not None:
        target = args.tear
        if not 0 <= target <= config.max_tear:
            print(f"error: tear {target} out of range [0, {config.max_tear}]", file=sys.stderr)
            return 2
    elif sys.stdin.isatty():
        target = _prompt_init_tear(config.max_tear)
    else:
        target = config.max_tear

    count = 0
    for file_path in _walk(repo_root, config, repo_root):
        try:
            content = file_path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        if parse_tear_level(content, max_tear=config.max_tear) is not None:
            continue
        new_content = set_tear(
            content,
            tear=target,
            extension=file_path.suffix,
            filename=file_path.name,
        )
        if new_content != content:
            file_path.write_text(new_content)
            count += 1

    noun = "file" if count == 1 else "files"
    print(f"tagged {count} {noun} at tear {target}")
    return 0


def _prompt_init_tear(max_tear: int) -> int:
    print()
    print("What tear level should untagged files start at?")
    print()
    print("  1 — Reviewed    human-written, has passed code review    (recommended)")
    print("  2 — Eyeballed   checked for obvious issues, not line-by-line")
    print("  3 — Unreviewed  AI-generated or vibe-coded")
    print()
    while True:
        try:
            raw = input("tear level [1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        level = 1 if not raw else None
        if level is None:
            try:
                level = int(raw)
            except ValueError:
                print(f"  Enter a number between 0 and {max_tear}.")
                continue
        if not 0 <= level <= max_tear:
            print(f"  Enter a number between 0 and {max_tear}.")
            continue
        return level


if __name__ == "__main__":
    raise SystemExit(main())
