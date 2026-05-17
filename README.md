<!-- @tear: 1 -->

# Tears

**Tiered Enforcement, Authorship Review System.**

*Vibe-Code Responsibly*

`tears` lets teams use AI coding tools without losing track of what has actually
been reviewed.

AI edits demote files to `@tear: 3`. Humans promote them after review. CI enforces
that higher-trust Python code cannot import lower-trust Python code.

The useful mechanic is the diff:

```diff
- # @tear: 1
+ # @tear: 3
```

The diff is the attestation. If the tier dropped and nobody restored it, the file is
still unreviewed.

## Why

AI-assisted teams need a cheap way to answer:

- Which files were touched by AI?
- Which files have actually been reviewed?
- Can sensitive code accidentally depend on unreviewed code?

`tears` keeps that signal in source control, where reviewers already look.

## Installation

```bash
pip install tears-cli
```

or:

```bash
uv add --dev tears-cli
```

## Quick Start

Create `.tears.toml`:

```toml
# @tear: 3
# Soft trial mode: existing files without @tear headers are treated as reviewed.
default_tear = 1
missing_header = "warn"

[directory_requirements]
"src/auth" = 0
"src/api" = 1

[imports]
source_roots = ["src"]
```

Run a full scan:

```bash
tears
```

Add the AI edit hook, pre-commit hook, or GitHub Action below when you are ready to
enforce it automatically.

## Adoption Modes

Soft trial mode uses `default_tear = 1`, so existing headerless files can be treated as
reviewed without rewriting the repo.

Full adoption will use a missing-only tagging flow once implemented:

```bash
tears set . --tear 1 --missing-only
```

Then change `default_tear` to `3`, or remove it and set:

```toml
missing_header = "error"
```

Current note: `tears init` still tags existing files. Before stable release, init will
become a low-churn config-only command that writes `default_tear = 1` instead. Until
then, create `.tears.toml` directly if you want to try `tears` without rewriting source
files.

## Hooks

Hooks demote files after AI tool edits. They mutate headers; they do not run the scanner.
They require `uv run python -m tears.hook` to work from the repo where the edit happens.

### Claude Code

Add this to `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python -m tears.hook"
          }
        ]
      }
    ]
  }
}
```

The hook reads the edited file path from Claude Code's stdin JSON payload. It runs after
`Edit`, `Write`, and `MultiEdit` tool calls. Manual editor changes are not demoted.

### OpenCode

This repo includes an OpenCode plugin at `.opencode/plugins/tears-hook.js`. Place that
file in the same path in another repo to enable the hook there.

The plugin listens for `edit`, `write`, and `apply_patch` tool calls and passes edited
file paths to:

```bash
uv run python -m tears.hook FILE
```

Current OpenCode plugin limitations:

- it is repo-local rather than a packaged installer;
- it currently handles one path from an `apply_patch`;
- it still needs cleanup before being treated as polished integration code.

## Pre-commit and CI

### Pre-commit

Add this to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Thillel/tears
    rev: v0.1.0
    hooks:
      - id: tears
```

The published hook intentionally ignores filenames and runs a full repo scan. This matches
the current scanner model.

### GitHub Actions

Use the bundled action in a workflow:

```yaml
name: tears

on:
  pull_request:
  push:
    branches: [main]

jobs:
  tears:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Thillel/tears/.github/actions@v0.1.0
        with:
          path: .
```

The GitHub Action accepts a `path` input, but with the current scanner that path should
be the repo root.

## Tear Levels

| Tear | Meaning |
| --- | --- |
| `0` | Deeply reviewed. Security-critical or domain-owner reviewed. |
| `1` | Reviewed by a human, line by line. |
| `2` | Eyeballed for exfiltration, network calls, and obvious security issues. |
| `3` | Unreviewed. AI-generated or AI-touched. |

Lower numbers are more trusted.

## Rules

By default, a file may import from files at its own tier or a more trusted tier:

| Importer | May import |
| --- | --- |
| `0` | `0` |
| `1` | `0`, `1` |
| `2` | `0`, `1`, `2` |
| `3` | `0`, `1`, `2`, `3` |

Directory requirements can require sensitive paths to stay at a higher trust tier.

## Header Format

Python files use:

```python
# @tear: 1
```

Other supported hook insertion styles include:

```js
// @tear: 1
```

```md
<!-- @tear: 1 -->
```

Only Python files are mechanically scanned in the current release.

## Commands

```bash
tears                            # scan the repo
tears down FILE_OR_DIR --tear 1  # promote: more trusted
tears up FILE_OR_DIR --tear 3    # demote: less trusted
tears set FILE_OR_DIR --tear 2   # exact level
```

## Configuration

`tears` reads `.tears.toml` from the scan root.

```toml
# @tear: 3
max_tear = 3
missing_header = "warn"
exclude = ["tests/scan/fixtures/**", "**/*.generated.py"]
default_tear = 3

[default_tears]
"tests" = 3

[directory_requirements]
"src/auth" = 0
"src/api" = 1

[imports]
source_roots = ["src"]

[import_rules]
"1" = 2
```

Config fields:

- `max_tear`: highest tier number. Defaults to `3`.
- `missing_header`: `warn` or `error`. Defaults to `warn`.
- `exclude`: glob patterns ignored by scanner and hook.
- `default_tear`: tier to assume for headerless files without warning.
- `default_tears`: path-specific defaults for headerless files.
- `directory_requirements`: path-specific maximum allowed tier.
- `imports.source_roots`: roots used for Python package discovery.
- `import_rules`: optional per-tier import relaxation or restriction.

## Current Scope

`tears` is early. Today, it enforces Python package imports only. The hook can insert or
demote headers in many file types, but the scanner currently checks `.py` files discovered
through Python package roots.

Current scanner limitations:

- `tears` is a full-repo scan.
- `tears PATH` currently treats `PATH` as the repo root, not as a subpath filter.
- Single-file scans such as `tears src/foo.py` are not implemented.
- Flat scripts and namespace packages may be missed by the current grimp-backed scanner.

See [DESIGN.md](./DESIGN.md) for the design rationale and [roadmap.md](./roadmap.md)
for planned fixes.

## Development

```bash
git clone https://github.com/Thillel/tears
cd tears
uv sync
make check
make test
make fmt
```

`make check` runs formatting, linting, strict type checking, and tests.

## License

MIT. See [LICENSE](./LICENSE).
