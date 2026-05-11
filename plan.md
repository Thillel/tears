<!-- @tear: 3 -->

# tears v1 — Implementation Plan

A focused build plan for v1. Captures the scope cuts, behavioral decisions, and test strategy
agreed during spec review. Where this document conflicts with `spec.md` or `test-spec.md`,
this document wins.

---

## 1. Scope

**v1 is:**
- A single CLI command: `tears` (bare, no subcommand — matches mypy/pyright/black/flake8/pylint)
- A `.tears.yml` config
- A Claude Code `PostToolUse` hook
- Python source files only (`.py`)

**v1 is not:**
- `tears init`, `tears promote`, `tears report` — cut
- `tears check --files` or `tears scan` — no diff-based mode and no subcommands; bare `tears` is the only mode
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
for v1; the other (or a future tree-sitter builder) can be added later without touching
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

`.tears.yml` at repo root. All fields optional.

```yaml
max_tear: 3
directory_requirements: {}
exclude: []
imports:
  source_roots: ["."]
import_rules: null            # null = default "<=" rule
missing_header: warn          # warn | error
```

**Validation at load time:**
- `max_tear >= 1`
- All tier ints in `directory_requirements` and `import_rules` in `0..max_tear`
- Every tier in `import_rules` includes itself
- Malformed YAML or schema failure → **hard fail with a clear error naming the file and
  the problem.** Never silently fall back to defaults.

### 2.7 `tears` behavior

Bare command, no subcommand. Matches mypy/pyright/black/flake8/pylint. v1 has one mode;
if init/promote/report return, they'd start as `python -m tears.X` invocations. Promotion
to subcommands only if/when a mode proves popular enough to justify migration.

**Usage:**
- `tears` — scan the repo from cwd
- `tears src/` — scan a specific path
- `tears file.py` — scan a single file (TBD whether useful)

**Pipeline:**
1. Discover all `.py` files in the repo (respect `.gitignore` if `git` is available;
   otherwise walk and apply `exclude` + extension filter).
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
          { "type": "command", "command": "python -m tears.hook" }
        ]
      }
    ]
  }
}
```

The hook reads the affected file path from the env var Claude Code provides (verify the
exact name against current Claude Code hook docs at implementation time).

### 3.2 Behavior

For each affected file:

1. If the file matches `exclude` patterns or isn't `.py` (v1), skip.
2. If a valid `@tear` header exists in the first 5 lines, replace its value with `max_tear`.
3. If multiple `@tear` headers exist, replace **all** of them with `max_tear`
   (idempotent + collapses ambiguity).
4. If no header exists, insert one. Insertion order:
   - **After any shebang** (`#!...`) on line 1.
   - **After any encoding declaration** (`# -*- coding: ... -*-`). PEP 263 requires the
     declaration on line 1 or 2 — pushing it down breaks Python's encoding detection.
   - Otherwise as line 1.
5. Write the file back.

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
| `test_config.py` | `load_config` — defaults, YAML parsing, validation errors (`max_tear` bounds, tier references, self-import, malformed YAML), partial `import_rules` filling defaults |
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
    │   ├── .tears.yml
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
2. Build `fixtures/01_clean_repo/` — tiny but realistic clean repo with `.tears.yml`,
   source files, `expected.txt`.
3. Implement the minimum to make it pass:
   - `tears.config.load_config` (just enough to load the YAML)
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
├── cli.py                 # argparse + dispatch for bare `tears`
├── config.py              # TearsConfig, load_config, validation
├── header.py              # parse_tear_level (used by builders)
├── graph/                 # ImportGraph protocol + concrete builder
│   ├── __init__.py        # the Protocol
│   └── grimp_builder.py   # v1 builder (B1). Adding ast_builder.py later = one new file.
├── rules.py               # can_import, check_directory_requirement (pure)
├── checker.py             # ImportGraph + config → list of violations
├── scan.py                # orchestration + reporter
└── hook.py                # apply_hook + `python -m tears.hook` entry
```

`graph/` is the only subpackage — justified by having a Protocol + multiple
implementations behind it. Everything else stays flat.

---

## 7. Decision Log

| Question | Decision |
|---|---|
| Diff-based check or full scan? | Full scan only |
| Languages in v1? | Python only |
| `init` / `promote` / `report`? | Cut |
| `test_policy: inherit`? | Cut |
| Architecture? | `ImportGraph` Protocol + checker, separated by DIP. Builders are interchangeable (§2.2) |
| CLI shape? | Bare `tears` (no subcommand) — matches mypy/pyright/black/flake8/pylint. Future modes start as `python -m tears.X`; promotion to subcommands only if/when one proves popular. |
| Import extraction tech? | AST, not regex |
| Import handling builder for v1? | **B1: grimp + own checker + own CLI.** Behind the `ImportGraph` Protocol — A or B2 can swap in as one new module. See §2.2. |
| Stdlib filtering? | No — extractor returns verbatim, resolver returns `None` for non-`source_roots` paths |
| `from X import Y` resolution? | Try `X.Y` as file first, fall back to `X` (verify under Option B) |
| Snapshot format? | Plain text, `expected.txt` + `--- exit: N ---` line |
| Malformed config handling? | Hard fail with clear error |
| Hook on duplicate headers? | Replace all (idempotent) |
| Header insertion preserves shebang? | Yes |
| Header insertion preserves encoding declaration? | Yes (PEP 263 — must stay on line 1 or 2) |
| Excludes as laundering vector? | Accepted, documented |

---

## 8. Known Limitations (v1, by choice)

- **Excludes are a tier-laundering vector.** A tier-0 file importing through an excluded
  shim effectively imports anything the shim re-exports. Acceptable; document.
- **Re-exports through `__init__.py` are not followed.** If `auth/__init__.py` (tier 0)
  re-exports from `auth/_internal.py` (tier 3), an importer of `auth` only sees the tier
  of `__init__.py`. Document.
- **No detection of dynamic imports.** `importlib.import_module("untrusted")` is invisible
  to tears.
- **No reverse-dep cache.** Full scan reads every file's header on every run. For a
  5,000-file repo this is sub-5s; if it ever isn't, add an mtime-keyed tier cache.
