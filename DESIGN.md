<!-- @tear: 1 -->

# Design

## Product Idea

`tears` makes review trust visible in source files. A file's `@tear` header says how
carefully that file has been reviewed. AI tooling demotes files it touches. Humans promote
files only after review.

The design goal is not perfect provenance. The design goal is to make review debt visible
in the same place teams already review code: the diff.

## Non-goals

`tears` is not a security boundary. It does not prevent manual edits, malicious tier
changes, or same-PR promotion after code changes. It is a review-attestation convention
backed by lint checks.

`tears` also does not try to prove authorship. The hook records that an AI tool touched a
file by demoting the tier, but humans remain responsible for the final tier committed.

## Tier Model

Lower tiers are more trusted:

- `0`: deeply reviewed, usually security-critical or domain-owner reviewed.
- `1`: reviewed by a human line by line.
- `2`: eyeballed for obvious security issues.
- `3`: unreviewed or AI-touched.

The default import rule is:

```text
target_tier <= importer_tier
```

This protects higher-trust code from depending on lower-trust code.

## Architecture

The current module layout is deliberately small:

| Module | Role |
| --- | --- |
| `cli.py` | argparse and command dispatch |
| `config.py` | `.tears.toml` parsing and validation |
| `header.py` | Python `@tear` header parsing |
| `styles.py` | comment styles for hook insertion |
| `mutate.py` | shared header mutation primitives |
| `hook.py` | shared AI-tool hook entry point |
| `codex_hook.py` | Codex PostToolUse wrapper for `apply_patch` payloads |
| `rules.py` | pure tier and directory rule functions |
| `checker.py` | composes rules over an import graph |
| `scan.py` | scan orchestration and text reporting |
| `graph/__init__.py` | `ImportGraph` protocol |
| `graph/grimp_builder.py` | current grimp-backed Python package graph |

The important boundary is `ImportGraph`. The checker does not care how imports are
discovered. This should allow an AST/file-walking builder to be added without changing
the core rule logic.

## Current Scanner

The current scanner uses grimp:

1. Load `.tears.toml`.
2. Discover Python packages under configured `imports.source_roots`.
3. Build a grimp import graph.
4. Map modules back to source files.
5. Parse `@tear` headers.
6. Apply directory and import rules.
7. Format a human-readable report.

This is good for package import semantics, but it means discovery is limited by package
layout. Flat scripts and namespace packages are a known gap.

## Hooks

The hook path is separate from the scan path. Hooks do not validate imports. They only
set or insert `@tear` headers.

Shared hook behavior:

1. Find the repo root.
2. Load `.tears.toml`, falling back to defaults on config errors.
3. Skip excluded files.
4. Replace existing headers in the first five lines.
5. Insert a header for known file types when missing.

The hook is intentionally tolerant. AI edit hooks should not break normal editing because
of a malformed config file.

Tool integrations are thin adapters around that shared mutation path:

- Claude Code runs `tears.hook` from a PostToolUse hook and passes the edited path in
  stdin JSON.
- Codex uses `.codex/config.toml` to run `tears.codex_hook` after `apply_patch`. Codex
  asks on startup whether to enable the hook before it runs.
- OpenCode uses `.opencode/plugins/tears-hook.js` to pass edited paths to `tears.hook`.

## Configuration

`.tears.toml` is parsed with stdlib `tomllib`. Schema errors are hard failures for scans
and non-fatal for hooks.

Important config choices:

- `missing_header` lets teams start with warnings and later tighten to errors.
- `default_tear` and `default_tears` let teams try the tool without editing every file.
- `exclude` is shared by scanner and hook.
- `import_rules` can relax or restrict the default import matrix.

## Testing Strategy

The test suite has two layers:

- Unit tests cover config, header parsing, pure rules, checker behavior, CLI mutation
  commands, and hook mutation.
- Integration tests run complete fixture repos and compare stdout plus exit code against
  snapshots.

The checker is tested against an in-memory fake graph. This keeps rule tests independent
from grimp and filesystem behavior.

The main missing test layer is direct coverage for `graph/grimp_builder.py`.

## Known Limitations

- Scanner support is Python-only.
- Discovery is currently grimp/package-layout dependent.
- `tears PATH` currently treats `PATH` as the scan root.
- Single-file checks are not implemented.
- `.gitignore` handling is asymmetric today. The scanner skips gitignored top-level
  package directories during discovery, but does not apply gitignore checks uniformly to
  every discovered file. The hook honors `.tears.toml` `exclude`, but does not currently
  skip files just because they are gitignored.
- Re-exports through `__init__.py` are not followed as transitive trust checks.
- Dynamic imports are invisible.
- Excluded files can be a trust-laundering vector if teams exclude shims that re-export
  lower-trust code.

## Gitignore Policy

The intended policy still needs to be made explicit before stable release. The likely
rule is:

- the scanner should ignore files ignored by git, unless a user explicitly opts into
  scanning them;
- the hook should avoid mutating gitignored files by default, because generated,
  vendored, cache, and environment files should not receive repo trust headers;
- `.tears.toml` `exclude` remains the explicit project-level policy for files that are
  tracked but should be outside tears enforcement.

This is separate from `.notears`, which is currently a human marker in fixtures rather
than an enforced exclusion mechanism.

## Design Direction

The next architectural step is an AST/file-walking builder that can handle ordinary
Python files outside package layouts. After that, path filtering and JSON output become
straightforward.

Multi-language support should wait until Python scan semantics are precise. Each new
language needs real import resolution, not just header parsing.
