<!-- @tear: 1 -->

# Tears

**Tiered Enforcement, Authorship Review System.**

*Vibe-Code Responsibly*

Not everything in your repo needs the same level of scrutiny. You should be able to
vibe-code a dashboard, prototype a feature, iterate on a script — without giving each
one the same ceremony as your auth layer. But they live in the same repo, and right now
nothing stops a carelessly imported module from pulling unreviewed code into your most
sensitive systems.

`tears` lets you vibe-code where it's safe and stay careful where it matters. Files
declare a trust tier via a `@tear` header. Agents automatically demote files they
touch. Humans restore the tier after review — or don't.
CI enforces that trusted code can't depend on untrusted code.

The useful mechanic is the diff:

```diff
- # @tear: 1
+ # @tear: 3
```

If you saw this in your diff and changed it back, you reviewed the code. If you
didn't notice, you didn't — and the tier stays where it belongs.

## Why

You want to prototype fast. You want to vibe-code that internal tool, iterate on that
analytics page, let AI write the first draft of a migration script. You want to ship
things that are changing quickly — maybe a POC, maybe an eval, maybe a little
dashboard — without treating every file like it's launch-day production code.

But you also want to know that your auth logic, your payment flow, your core business
rules haven't quietly started depending on code that nobody actually read.

`tears` makes both possible at once:

- **Iterate freely on the periphery.** Scripts, tools, dashboards, prototypes — leave
  them at `@tear: 3` or `@tear: 2`. Vibe-code them, change them daily, they don't need
  a ceremony.
- **Stay rigorous at the core.** Auth, payments, security — these stay at `@tear: 0`.
  The import rule guarantees they can only depend on equally reviewed code.
- **Know what's what.** The tier lives in the file, in source control, in the diff.
  No separate tracking system, no stale spreadsheet, no guessing.

The tiers aren't a judgment about code quality. Tier 3 code might be perfectly fine.
It just hasn't been through the process yet — and until it has, it stays in its lane.

## Quick Start

```bash
pip install tears-cli
tears init  # create default config
tears       # scan your repo
```

No more tears!

## Adoption Modes

Soft trial mode uses `default_tear = 1`, so existing headerless files are treated as
reviewed while you try the tool. The starter config also includes commented examples for
source roots and directory requirements; uncomment and edit them when you are ready to
enforce project-specific boundaries.

If the scan checks `0 files`, uncomment `source_roots` in `.tears.toml` and point it at
your importable Python package root.

Full adoption tags only files that do not already have a deliberate tier:

```bash
tears set . --tear 1 --missing-only
```

Then change `default_tear` to `3`, or remove it and set:

```toml
missing_header = "error"
```

Then set up your agent hook, pre-commit, and GitHub Actions.

## Hooks

Hooks demote files after agents edit. They mutate headers; they do not run the scanner.
They require `uv run python -m tears.hook` or the tool-specific wrapper to work from the
repo where the edit happens.

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

### Codex

This repo includes a Codex hook config at `.codex/config.toml`. Place that file in the
same path in another repo to enable the hook there.

On startup, Codex will ask whether to enable the hook. Enable it if you want Codex edits
made through `apply_patch` to demote touched files automatically.

The Codex config runs:

```bash
uv run python -m tears.codex_hook
```

The wrapper reads Codex's PostToolUse stdin payload, extracts file paths from the patch,
and delegates header mutation to the shared hook logic.

Current Codex hook limitations:

- it is repo-local rather than a packaged installer;
- it currently handles `apply_patch` edits only;
- Codex prompts to enable the hook on startup, so a user must opt in before it runs.

### OpenCode

This repo includes an OpenCode plugin at `.opencode/plugins/tears-hook.js`. Place that
file in the same path in another repo to enable the hook there.

The plugin listens for `edit`, `write`, and `apply_patch` tool calls and passes edited
file paths to:

```bash
uv run python -m tears.hook FILE
```

Current OpenCode plugin limitation:

- it is repo-local rather than a packaged installer.

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
| `3` | Vibe Coded. |

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
tears set . --tear 1 --missing-only
```

`--missing-only` is available for `up`, `down`, and `set`; it tags only files that lack
an existing `@tear` header.

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

[scan]
exclude = ["fixtures/**"]

[mutate]
exclude = [".env"]

[import_rules]
"1" = 2
```

Config fields:

- `max_tear`: highest tier number. Defaults to `3`.
- `missing_header`: `warn` or `error`. Defaults to `warn`.
- `exclude`: glob patterns ignored by scanner and hook.
- `scan.exclude`: additional glob patterns ignored only by scanner.
- `mutate.exclude`: additional glob patterns ignored only by hooks and mutation commands
  (`set`, `up`, and `down`).
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
```

`make check` runs formatting, linting, strict type checking, and tests.

## License

MIT. See [LICENSE](./LICENSE).
