# @tear: 3
"""`tears` — bare CLI entry point. No subcommands in v1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tears.config import ConfigError
from tears.scan import run_scan


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    repo_root = Path(args.path).resolve()
    try:
        report, output = run_scan(repo_root)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(output)
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
