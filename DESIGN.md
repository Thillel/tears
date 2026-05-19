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
| `header.py` | `@tear` header parsing |
| `languages.py` | supported-language and file-suffix metadata |
| `styles.py` | comment styles for hook insertion |
| `mutate.py` | shared header mutation primitives |
| `hook.py` | shared AI-tool hook entry point |
| `codex_hook.py` | Codex PostToolUse wrapper for `apply_patch` payloads |
| `rules.py` | pure tier and directory rule functions |
| `checker.py` | composes rules over an import graph |
| `scan.py` | scan orchestration and text reporting |
| `graph/__init__.py` | `ImportGraph` protocol |
| `graph/file_graph.py` | in-memory file graph |
| `graph/tree_sitter_builder.py` | public tree-sitter graph entry point |
| `graph/tree_sitter_scan/` | tree-sitter discovery, extraction, and resolution |
| `graph/grimp_builder.py` | retained grimp-backed Python package graph |

The important boundary is `ImportGraph`. The checker does not care how imports are
discovered, which keeps scanner backends separate from tier policy.

## Current Scanner

The current scanner uses a tree-sitter-backed file graph:

1. Load `.tears.toml`.
2. Discover enabled-language source files under configured `imports.source_roots`.
3. Parse each file with its tree-sitter grammar.
4. Resolve conservative local import edges.
5. Parse `@tear` headers.
6. Apply directory and import rules.
7. Format a human-readable report.

The default language set is `["python"]`. Other supported languages opt in through
`languages`. The grimp builder remains in the codebase while tree-sitter parity settles.

The optional CLI path is currently a scan root, not a target filter. For example,
`tears some/repo` loads configuration from `some/repo` and scans from there. It does
not mean "load the current repo config and report only files under `some/repo`."
This very much might change in future versions, stay tuned.
Target filtering remains future work.

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
- `scan.exclude` and `mutate.exclude` add consumer-specific exclusions without changing
  the shared `exclude` behavior.
- `respect_gitignore` defaults to skipping gitignored files, with `[scan]` and
  `[mutate]` overrides for scanner and header-marking behavior.
- `import_rules` can relax or restrict the default import matrix.
- `artificial_tears` gives importer paths a deliberate import budget. This keeps a
  file's real review tier intact while allowing test directories to import lower-trust
  code they need to exercise.

## Testing Strategy

The test suite has two layers:

- Unit tests cover config, header parsing, pure rules, checker behavior, CLI mutation
  commands, and hook mutation.
- Integration tests run complete fixture repos and compare stdout plus exit code against
  snapshots.

Integration fixtures are grouped by language or suite under
`tests/scan/fixtures/<suite>/<fixture>/`. Each fixture directory is a complete mini-repo
with its own config, source files, and expected output. Future-behavior fixtures use
strict xfail markers so they fail as XPASS once implementation catches up.

The checker is tested against an in-memory fake graph. This keeps rule tests independent
from grimp and filesystem behavior.

The grimp-backed graph builder has direct unit coverage for discovery, excludes,
gitignore handling, and import-edge behavior.

## Dogfooding Policy

There are two kinds of test files in this repo:

- real test code under `tests/unit/` and `tests/scan/test_scan.py`;
- scan fixture input data under `tests/scan/fixtures/**`.

Real test code should dogfood `tears` normally. The repo includes `.` in
`[imports].source_roots` so test packages can be discovered, and uses
`[artificial_tears]` for `tests/unit` so reviewed tests can import lower-trust code
when they need to exercise checker and mutation behavior. Artificial tears are an import
budget only; they do not change a test file's own review tier.

Scan fixtures are not project code. They are mini-repositories used as linter inputs,
and they deliberately contain missing headers, invalid configurations, xfailed future
expectations, and unusual tear values. Excluding those fixture trees from both scan and
header marking is part of the test design, not an escape hatch from dogfooding. The
snapshot diff is the review surface for fixture behavior.

The current fixture suites include Python fixtures and opt-in multi-language fixtures.
Fixture `.tears.toml` files set `languages` explicitly when the mini-repo is not Python.

`.notears` files in fixture trees are human-readable markers. They document that a tree
is intentionally outside normal repo reviewedness policy, but `tears` does not enforce
`.notears` automatically in this milestone.

## Known Limitations

- Scanner support is Python-only.
- Discovery is currently grimp/package-layout dependent.
- `tears PATH` currently treats `PATH` as the config/scan root, not a target filter.
- Single-file checks are not implemented.
- `.gitignore` handling is configurable and symmetric by default: scanner and
  header-marking paths skip gitignored files unless the global or section-specific
  config opts into them.
- Re-exports through `__init__.py` are not followed as transitive trust checks.
- Dynamic imports are invisible.
- Excluded files can be a trust-laundering vector if teams exclude shims that re-export
  lower-trust code.

## Gitignore Policy

Gitignore handling is policy, not discovery accident:

- the scanner ignores files ignored by git unless a user explicitly opts into scanning
  them;
- the hook and `tears set/up/down` avoid marking gitignored files by default, because
  generated, vendored, cache, and environment files should not receive repo trust
  headers;
- `.tears.toml` `exclude` remains the explicit project-level policy for tracked files
  that should be outside tears enforcement.

The config shape follows the same global-plus-section pattern as excludes:

```toml
respect_gitignore = true

[scan]
respect_gitignore = true

[mutate]
respect_gitignore = true
```

## Artificial Tears

Artificial tears are path-specific import budgets. They let files in a directory import
targets up to a configured tear without changing the files' real `@tear` headers.

The motivating case is tests. A reviewed test may need to import unreviewed code to
assert that the checker reports a violation, or to exercise header mutation behavior.
Promoting the test to tear 3 would erase its reviewedness signal; relaxing tier 1
globally would weaken the policy everywhere. An artificial tear is scoped to the
importer path instead:

```toml
[artificial_tears]
"tests/unit" = 3
```

This means files under `tests/unit` may import targets at tear 0, 1, 2, or 3. It does
not change those test files' own tiers, and it does not affect files outside that path.

This is separate from `.notears`, which is currently a human marker in fixtures rather
than an enforced exclusion mechanism.

## Design Direction

The next architectural step is an AST/file-walking builder that can handle ordinary
Python files outside package layouts. After that, path filtering and JSON output become
straightforward.

Multi-language support should wait until Python scan semantics are precise. Each new
language needs real import resolution, not just header parsing. Strict-xfailed fixtures
record first-pass resolver expectations for TypeScript plus basic dependency edges in
C, C++, C#, Dart, Go, Java, JavaScript, Kotlin, PHP, Ruby, and Rust.
