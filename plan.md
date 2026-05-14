<!-- @tear: 3 -->

# tears v0.1.0 — Implementation Plan

A focused build plan for v0.1.0. Captures the scope cuts, behavioral decisions, and test strategy
agreed during spec review. Where this document conflicts with `spec.md`, this document wins.

---

## 1. Scope

**v0.1.0 is:**
- A single CLI command: `tears` (bare, no subcommand — matches mypy/pyright/black/flake8/pylint)
- A `.tears.toml` config
- A Claude Code `PostToolUse` hook with **asymmetric scope**: replaces existing
  `@tear` headers in *any* comment style (`#`, `//`, `--`, `<!--`, `/*`, `;`);
  inserts new headers in many known file types (`.py`, `.js`, `.ts`, `.go`,
  `.rs`, `.rb`, `.sh`, `.toml`, `.yml`, `.sql`, `.html`, `.md`, `.css`, ... plus
  `Makefile`, `Dockerfile`, `.gitignore`, etc.)
- **Scanning** Python source files only (`.py`) — multi-language enforcement is v2

**v0.1.0 is not:**
- `tears promote`, `tears report` — cut
- `tears check --files` or `tears scan` — no diff-based mode
- TypeScript / JavaScript / Go / SQL / etc. — Python first, prove the model
- Diff-aware reverse-dep checking — full scan covers this naturally
- `test_policy: inherit` — convention is project-specific, hard to define generically
- IDE integrations, PR comment bots, dashboards

Phase 2 picks one or two cut items based on real friction. Don't speculate further.

---

## 2. Behavioral Specification

### 2.1 Header parsing

A file's tier is determined by the first valid `@tear` header in its first 5 lines.

**Match rules:**
- The header must appear on a line that starts (after optional whitespace) with the comment
  marker for the file's language. For Python, `#`. This is what prevents
  `x = "# @tear: 0"` from being misread.
- Capture is `\d+`, validated against `0..max_tear` (default `0..3`). `# @tear: 4` with
  `max_tear=3` is malformed, not a valid tier 4.
- `# @tear: 1.5` must NOT match as `1` — require a word boundary after the digits.
  `# @tear: -1` must NOT match — no leading sign.
- Whitespace tolerance: any spaces/tabs between `@tear:` and the digit; leading whitespace
  before `#` allowed; extra spaces between `#` and `@tear` allowed.
- Multiple headers in the first 5 lines: take the worst (highest number).
- No valid header found: file is treated as missing-header. Behavior is config-driven
  (`missing_header: warn | error`, default `warn`).

### 2.2 Import handling architecture

**Two layers, separated by an abstraction (DIP).** The checker depends on an
`ImportGraph` protocol; concrete builders are interchangeable.

```python
from typing import Protocol
from collections.abc import Iterable
from pathlib import Path

class ImportGraph(Protocol):
    def files(self) -> Iterable[Path]:
        """All in-scope files in the repo."""

    def tier_of(self, file: Path) -> int | None:
        """Tier from the file's @tear header, or None if missing/malformed."""

    def imports_of(self, file: Path) -> Iterable[Path]:
        """Files this file directly imports — resolved to repo files; unresolvable
        and excluded targets omitted."""

    def importers_of(self, file: Path) -> Iterable[Path]:
        """Files that directly import this file. Optional — used only if we re-add
        reverse-dep checks. Builders may raise NotImplementedError."""
```

The **checker** (`tears.checker`) takes `ImportGraph + TearsConfig`, returns a list of
violations. It doesn't know or care how the graph was built. It has its own unit tests
using an **in-memory fake graph** — no filesystem, no parsing, just nodes and edges.

The **builders** below are interchangeable implementations of `ImportGraph`. Pick one
for v0.1.0; the other (or a future tree-sitter builder) can be added later without touching
the checker.

**Decision: Builder B1 (grimp + custom checker + own CLI).** A and B2 remain documented
as alternatives — they satisfy the same `ImportGraph` Protocol, so swapping later is a
single-module change. The comparison below is preserved for posterity / re-evaluation.

Regex-based extraction is out either way — every serious Python linter uses AST.

#### Builder A: stdlib `ast` + custom resolver

**Extractor** (~20 lines):

```python
import ast
tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name                              # "foo.bar"
    elif isinstance(node, ast.ImportFrom):
        yield ("." * node.level) + (node.module or "")   # "..pkg" for relatives
```

**Resolver** (~150 lines): implements the rules in §2.3. Maps extracted import strings to
file paths.

**Extractor output (before resolution):**
- `import foo` → `["foo"]`
- `from foo import bar` → `["foo"]` (resolver tries `foo.bar` as a file first)
- `from . import sibling` → `[".sibling"]`
- `from ..pkg import thing` → `["..pkg"]`

`import os` flows through to the resolver, which fails to find `os.py` in `source_roots`
and returns `None`; the edge is omitted from the graph. **No stdlib list anywhere.**

#### Builder B: grimp

```python
import grimp
graph = grimp.build_graph("mypackage")
```

Wrapped in a small adapter that satisfies the `ImportGraph` protocol — maps grimp's
module names back to file paths and applies the exclude list.

**Adjacent prior art — import-linter** (built on grimp) has three contract types:
`forbidden`, `layers`, `independence`. The `layers` contract is *conceptually* identical
to tears' default tier rule (higher layers may import from lower, not vice versa).

But the `layers` field requires literal module names and **does not support wildcards**:

```ini
[importlinter:contract:my-layers-contract]
type = layers
layers =
    mypackage.high
    mypackage.medium
    mypackage.low
```

This doesn't map cleanly to tears' file-level `@tear` headers, since tier groupings cross
package boundaries — there's no single module that *is* "tier 0" the way `mypackage.high`
is the high layer.

#### Sub-option B2: tears as a custom import-linter contract type

import-linter supports custom contract types via `subclass importlinter.Contract`:

```python
def check(self, graph):  # graph is a grimp ImportGraph
    # iterate edges, read @tear from each module's source file, check rule
    return importlinter.ContractCheck(kept=..., metadata={"violations": ...})

def render_broken_contract(self, check):
    # format violations to stdout
```

~100–150 LOC plugin + the Claude hook. tears reuses import-linter's CLI, config loader,
output formatting, ignore lists.

**Tradeoff:** users invoke `lint-imports` (with a `.importlinter` config that loads our
contract type) instead of `tears`. tears stops being a brand and becomes a plugin.
For a tool whose pitch leans on the `@tear` header semantics and the Claude hook flow,
owning the CLI matters.

**Default recommendation:** B1 (grimp + own checker, own CLI) over B2.

#### Comparison

| Dimension | Builder A (`ast`) | Builder B (grimp) |
|---|---|---|
| LOC in tears | ~250 | ~50 |
| Dependencies | 0 | 1 (grimp) |
| Python import semantics correctness | Our problem | Solved upstream |
| Namespace packages (PEP 420) | Our problem | Solved upstream |
| Reverse-dep queries (`importers_of`) | Build it | Free |
| Multi-top-level-package repos | Trivial (we walk the fs) | Native: `grimp.build_graph('pkg1', 'pkg2', ...)` |
| Future language support | New builder per language | grimp is Python-only |
| When something is wrong | Local fix | Upstream bug, or workaround |
| Bus factor | Us | grimp + import-linter community |

**Pre-decision homework:** ~1 hour with import-linter's contract types. If tier rules map
naturally to a contract, lean B (and possibly build *on* import-linter rather than
beside it). If they don't, A is honest and tractable.

**Either way:** Milestone 1 only needs the builder to satisfy the protocol for
`fixtures/01_clean_repo/`. Start with the `ast` builder — throwaway if you end up
picking grimp.

**Out of scope under either builder:** `__import__`, `importlib.import_module`,
runtime/dynamic imports, conditional imports inside `if TYPE_CHECKING:` (treated as
regular imports — fine).

#### Future: tree-sitter for multi-language

If tears ever supports JS/TS/Go/etc., the path is a tree-sitter-based builder. Same
`ImportGraph` protocol; per-language extraction queries; per-language resolvers (each
language's module system is different — no avoiding that). The architecture makes this a
drop-in: the checker doesn't change.

### 2.3 Import resolution behavior

Behavioral expectations regardless of which option in §2.2 we pick. Under A we implement
them; under B grimp handles most of them and we wrap with the exclude check.

1. **Absolute imports** (`foo.bar`): try each entry in `source_roots`, in order:
   - `<root>/foo/bar.py`
   - `<root>/foo/bar/__init__.py`

   First match wins.

2. **Relative imports** (`.sibling`, `..pkg.module`): resolve relative to the importing
   file's directory. Each leading dot moves up one level.

3. **`from X import Y` ambiguity:** try `X.Y` as a file *first* (`<root>/foo/bar/baz.py`
   or `<root>/foo/bar/baz/__init__.py`); fall back to resolving `X` if missing. Catches
   the case where `Y` is a submodule with its own tier. **Verify grimp does this** if
   choosing Option B; wrap if not.

4. **Excluded targets:** if the resolved file matches any `exclude` pattern, skip the
   import check. Always our wrapper, regardless of option.

5. **Unresolvable:** skip. Conservative by design — only flag what can be definitively
   resolved.

### 2.4 Tier comparison

**Default:** `target_tear <= importer_tear`.

**Custom rules** (`import_rules` in config): explicit allow-list per tier. Loader resolves
the full matrix at config-load time (filling in defaults for unspecified tiers) and
converts each allow-list to a `frozenset[int]`. Per-edge check is one set membership.

**Validation (at config load, not per check):**
- Every tier in `import_rules` is in `0..max_tear`.
- Every tier includes itself in its allow list.

### 2.5 Directory requirements

A file's tier must be `<=` the requirement of its longest-prefix-matching directory.

- **Path-segment aware.** `src/auth` matches `src/auth/tokens.py` but NOT
  `src/authentic/foo.py`. Compare by `/`-split segments, never `startswith`.
- Trailing slashes in config keys are normalized.
- Files with no matching directory are unrestricted.

### 2.6 Config loading

`.tears.toml` at repo root. All fields optional. Parsed with stdlib `tomllib` (no
third-party deps).

```toml
max_tear = 3
exclude = []
missing_header = "warn"          # "warn" | "error"

[directory_requirements]
# "src/auth" = 0

[imports]
source_roots = ["."]

# Optional — omit for the default "<=" rule. TOML keys are strings; we convert
# integer-valued strings to ints at load time.
# [import_rules]
# "1" = [0, 1, 2]
```

**Validation at load time:**
- `max_tear >= 1`
- All tier ints in `directory_requirements` and `import_rules` in `0..max_tear`
- Every tier in `import_rules` includes itself
- `import_rules` keys must be integer-valued strings (`"0"`, `"1"`, etc.)
- Malformed TOML or schema failure → **hard fail with a clear error naming the file and
  the problem.** Never silently fall back to defaults.

### 2.7 `tears` behavior

Bare `tears [path]` scans. Subcommands (`up`, `down`, `set`, `init`) handle mutation.

**Usage:**
- `tears` — scan the repo from cwd
- `tears src/` — scan a specific path
- `tears file.py` — scan a single file *(not yet implemented; deferred to v0.2.0 per roadmap §17)*
- `tears init [path]` — scaffold `.tears.toml`, tag all headerless files at `max_tear`
- `tears down FILE/DIR --tear N` — promote: mark as more trusted (number goes down)
- `tears up FILE/DIR --tear N` — demote: mark as less trusted (number goes up)
- `tears set FILE/DIR --tear N` — set exact level with no direction check

**Pipeline:**
1. Discover all `.py` files in the repo via grimp over configured `source_roots`. Note:
   `.gitignore` filtering is **not yet implemented** (deferred to Phase 1 per roadmap §10);
   use `exclude` patterns in `.tears.toml` as a workaround.
2. Parse the header from each → tier or missing.
3. For each file: extract imports → resolve each → look up target tier → check rule.
4. For each file: check directory requirement.
5. Emit human-readable results to stdout. Exit 0 on no failures; exit 1 on any failure.

**Output format** (from `spec.md`, refined by snapshot tests):

```
FAIL  src/auth/tokens.py
  - directory requires tear 0, file is tear 2

FAIL  src/utils/parser.py (tear 3)
  - imports src/core/models.py (tear 1): tear 3 cannot import from tear 1

WARN  src/utils/helpers.py
  - missing @tear header (treated as tear 3)

OK    src/api/routes.py (tear 1)

3 files checked, 2 failures, 1 warning
```

The exact format is pinned by the snapshot tests, not by this document.

---

## 3. Claude Code Hook

A `PostToolUse` hook registered in `.claude/settings.json`.

### 3.1 Registration

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          { "type": "command", "command": "uv run python -m tears.hook" }
        ]
      }
    ]
  }
}
```

The hook reads the affected file path from a JSON payload on stdin (`tool_input.file_path`).

### 3.2 Behavior

For each affected file:

1. If the file matches `exclude` patterns or is missing, skip.
2. **Replacement (universal).** Scan the first 5 lines for any `@tear: <digit>` in a
   comment-like position (after optional indent, prefixed by non-alphanumeric comment
   chars: `#`, `//`, `--`, `;`, `<!--`, `/*`, etc.). For every matching line, rewrite
   the digit to `max_tear`. Idempotent, preserves indentation, comment markers,
   trailing tokens (`-->`, `*/`), and line endings.
3. **Insertion (type-specific).** If no header was found AND the file's extension is
   in `COMMENT_STYLES` (or its name is in `FILENAME_STYLES` for extensionless files
   like `Makefile`/`Dockerfile`/`.gitignore`), insert a new header in the right
   comment style — `# @tear: 3` for hash-comment families, `// @tear: 3` for
   slash-comment, `-- @tear: 3` for SQL/Lua, `<!-- @tear: 3 -->` for HTML/Markdown/XML,
   `/* @tear: 3 */` for CSS, `; @tear: 3` for INI. Insertion position:
   - **After any shebang** (`#!...`) on line 1.
   - **After any encoding declaration** (`# -*- coding: ... -*-`). PEP 263 requires the
     declaration on line 1 or 2 — pushing it down breaks Python's encoding detection.
   - Otherwise as line 1.
4. If no header was found AND the file type isn't known, **no-op**.
5. Write the file back if changed.

**Asymmetric scope is deliberate.** Replacement is cheap (one regex, no language
knowledge needed) and works across every comment syntax. Insertion needs to know the
comment marker per-extension — but the table is small and additive, so we cover ~50
common dev file types. The *scanner* (`tears`) is still Python-only in v0.1.0 because
resolving imports requires full language semantics; the *hook* doesn't need those.

Idempotent: running the hook twice produces the same content as running it once.

### 3.3 CLAUDE.md

Project's `CLAUDE.md` should include the policy text from `spec.md` §5. The hook is the
enforcement; the CLAUDE.md note is a courtesy so Claude doesn't fight the hook.

---

## 4. Test Strategy

Two layers, neither replacing the other.

### 4.1 Unit tests — `tests/unit/`

Inline strings or trivial `tmp_path` fixtures. Parametrized tables. Fast. The "regex
passes its torture suite" backstop.

| File | What it tests |
|---|---|
| `test_header.py` | `parse_tear_level` over malformed headers, comment styles, position in first 5 lines, whitespace tolerance, in-string false positives, multiple headers, custom `max_tear` |
| `test_rules.py` | `can_import` (default matrix + custom rules: relaxed, islands, strict, open) and `check_directory_requirement` (exact, exceeds, fails, longest-prefix, path-segment matching, trailing slashes) |
| `test_checker.py` | The checker against an **in-memory fake graph** — assert violations from constructed node/edge sets. No filesystem, no parsing. Covers tier rule violations, directory violations, missing-header (warn vs error), excludes, custom `max_tear`. |
| `test_config.py` | `load_config` — defaults, TOML parsing, validation errors (`max_tear` bounds, tier references, self-import, malformed TOML, non-integer rule keys), partial `import_rules` filling defaults |
| `test_hook.py` | `apply_hook` — replace existing, insert when missing, preserve shebang, preserve encoding declaration, idempotency, custom `max_tear`, multiple-header collapse |
| `test_grimp_builder.py` | The grimp adapter — verifies the `ImportGraph` Protocol is satisfied, file-path mapping is correct, exclude wrapper applies, multi-package repos work via `grimp.build_graph(*pkgs)`. Most semantic correctness is grimp's responsibility. |

If Builder A is ever added, its `test_ast_builder.py` covers the `ast` extractor and
custom resolver in the same pattern (parametrized strings + `tmp_path` mini-trees).

### 4.2 Integration tests — `tests/scan/`

A single parametrized test that walks `tests/scan/fixtures/`, runs `tears` against
each, and compares stdout + exit code to `expected.txt`.

```
tests/scan/
├── test_scan.py
└── fixtures/
    ├── 01_clean_repo/
    │   ├── .tears.toml
    │   ├── src/auth/tokens.py
    │   ├── src/api/routes.py
    │   └── expected.txt
    ├── 02_tear0_imports_tear3/
    ├── 03_directory_violation/
    ├── 04_missing_header_warn/
    ├── 05_missing_header_error/
    ├── 06_stdlib_ignored/
    ├── 07_relative_imports/
    ├── 08_submodule_resolution/      # from foo import bar where bar is a file
    ├── 09_island_rules/
    ├── 10_strict_rules/
    ├── 11_six_tier_system/           # custom max_tear
    ├── 12_excludes/
    ├── 13_excluded_target_skipped/
    ├── 14_path_segment_matching/     # src/auth vs src/authentic
    └── 15_malformed_config/          # exits non-zero with clear error
```

Each fixture is a complete, runnable repo. The test runner copies the fixture to
`tmp_path` (so tests can't mutate fixtures), runs `tears` from there, and compares
stdout + exit code.

**Snapshot format:** `expected.txt` is the literal expected stdout, followed by
`--- exit: N ---` on its own line. Snapshot regen is deliberate
(`pytest --update-snapshots` or equivalent) — reviewer eyeballs the diff in PR.

**Adding a regression test for a real bug:** copy the user's repro into a new numbered
fixture dir, generate the snapshot, commit. The fixture *is* the spec for that scenario.

---

## 5. Implementation Order

Drive the work from integration tests. Drop into unit tests when something's hard to
debug from a fixture dir alone.

**Milestone 1: `fixtures/01_clean_repo/` passes.** This forces the whole pipeline to exist.

1. Set up `tests/scan/test_scan.py` — parametrized loop + snapshot comparison.
2. Build `fixtures/01_clean_repo/` — tiny but realistic clean repo with `.tears.toml`,
   source files, `expected.txt`.
3. Implement the minimum to make it pass:
   - `tears.config.load_config` (just enough to load the TOML)
   - `tears.header.parse_tear_level` — write `tests/unit/test_header.py` here for edge cases
   - `tears.graph.ImportGraph` Protocol + `tears.graph.grimp_builder` — just enough for this fixture. Protocol stays so A or B2 can swap in later.
   - `tears.rules.can_import` + `check_directory_requirement` — write `tests/unit/test_rules.py` here
   - `tears.checker` — takes `ImportGraph + config` → violations. Write `tests/unit/test_checker.py` with an in-memory fake graph here.
   - `tears.scan.scan` — orchestration: build graph → run checker → format output
   - `tears.cli.main` — argparse for bare `tears`

**Milestone 2: `fixtures/02_tear0_imports_tear3/` passes.** Adds violation detection.

**Milestones 3+:** add fixtures one at a time, each pinning a new behavior (the order in
the fixture list above is roughly the order to add them).

**Hook is independent.** Write `tests/unit/test_hook.py` and `tears.hook` whenever — no
shared code with the scan pipeline.

---

## 6. Module Layout

```
tears/
├── __init__.py
├── __main__.py            # `python -m tears` entry
├── cli.py                 # argparse + dispatch; subcommands: up, down, set, init
├── config.py              # TearsConfig, load_config, validation
├── header.py              # parse_tear_level (used by builders)
├── styles.py              # comment-style constants and lookup tables
├── mutate.py              # set_tear, process_file, find_repo_root — shared primitives
├── graph/                 # ImportGraph protocol + concrete builder
│   ├── __init__.py        # the Protocol
│   └── grimp_builder.py   # v0.1.0 builder (B1). Adding ast_builder.py later = one new file.
├── rules.py               # can_import, check_directory_requirement (pure)
├── checker.py             # ImportGraph + config → list of violations
├── scan.py                # orchestration + reporter
└── hook.py                # entry point only; delegates to mutate.process_file
```

`graph/` is the only subpackage — justified by having a Protocol + multiple
implementations behind it. Everything else stays flat.

---

## 7. Decision Log

| Question | Decision |
|---|---|
| Diff-based check or full scan? | Full scan only |
| Languages in v0.1.0? | Python only |
| `init` / `promote` / `report`? | Cut |
| `test_policy: inherit`? | Cut |
| Architecture? | `ImportGraph` Protocol + checker, separated by DIP. Builders are interchangeable (§2.2) |
| CLI shape? | Bare `tears [path]` scans; `up`, `down`, `set`, `init` are subcommands. |
| Import extraction tech? | AST, not regex |
| Import handling builder for v0.1.0? | **B1: grimp + own checker + own CLI.** Behind the `ImportGraph` Protocol — A or B2 can swap in as one new module. See §2.2. |
| Stdlib filtering? | No — extractor returns verbatim, resolver returns `None` for non-`source_roots` paths |
| `from X import Y` resolution? | Try `X.Y` as file first, fall back to `X` (verify under Option B) |
| Snapshot format? | Plain text, `expected.txt` + optional `--- stderr ---` block + `--- exit: N ---` line |
| Config file format? | TOML (`.tears.toml`), parsed via stdlib `tomllib`. No third-party YAML dep. |
| Malformed config handling? | `tears` hard-fails with exit code 2; hook falls back to defaults so Claude Code never breaks. |
| Repo root resolution (hook)? | `.git/` preferred over `.tears.toml` (nested configs are legitimate — e.g. test fixtures). |
| Per-directory exemption? | `.notears` marker file. v0.1.0: not parsed — purely a human marker. Exclude patterns in root `.tears.toml` do the actual scan/hook exclusion. Future: tears may read `.notears` content (uses `# @tear: N` format) as directory-level attestation. |
| Hook on duplicate headers? | Replace all (idempotent) |
| Hook scope? | Asymmetric: replacement works across any comment style; insertion for ~50 known file types (line + block comment families, plus filename-based for Makefile/Dockerfile/.gitignore/etc.). |
| Header insertion preserves shebang? | Yes |
| Header insertion preserves encoding declaration? | Yes (PEP 263 — must stay on line 1 or 2) |
| Excludes as laundering vector? | Accepted, documented |

---

## 8. Known Limitations (v0.1.0, by choice)

- **Excludes are a tier-laundering vector.** A tier-0 file importing through an excluded
  shim effectively imports anything the shim re-exports. Acceptable; document.
- **Re-exports through `__init__.py` are not followed.** If `auth/__init__.py` (tier 0)
  re-exports from `auth/_internal.py` (tier 3), an importer of `auth` only sees the tier
  of `__init__.py`. Document.
- **No detection of dynamic imports.** `importlib.import_module("untrusted")` is invisible
  to tears.
- **No reverse-dep cache.** Full scan reads every file's header on every run. For a
  5,000-file repo this is sub-5s; if it ever isn't, add an mtime-keyed tier cache.
