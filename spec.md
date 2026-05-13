<!-- @tear: 3 -->

# tears — Full Specification

**Tiered Enforcement, Authorship Review System**

*No tears. No tiers. Gentle on your codebase.*

## Overview

`tears` is a lightweight system for enforcing tiered code review policies in monorepos. Files declare their trust level via a `@tear` header comment. AI tools (Claude Code) mechanically set edited files to the lowest tier. Humans attest to review quality by manually restoring the tier before committing. A CI linter enforces import rules and directory requirements based on these headers.

The system is self-enforcing by design: if you didn't notice the tier dropped in your diff, you didn't review the code.

---

## 1. Tear Levels

| Tear | Name | Meaning |
|------|------|---------|
| 0 | Deeply reviewed | Two reviewers or one reviewer + domain owner. Reserved for auth, security, payments, core business logic. Zero tears. |
| 1 | Reviewed | One qualified human read and understood every line. Standard production code. |
| 2 | Eyeballed | Someone confirmed no exfiltration, no obfuscated strings, no unexpected network calls. No logic review. |
| 3 | Unreviewed | AI-generated or unreviewed code. Default for new files and any file touched by AI tooling. May cause tears. |

Tear 0 is highest trust. Tear 3 is lowest.

---

## 2. File Header Format

Every tracked source file must contain a `@tear` declaration in its first 5 lines. The format adapts to the file's comment syntax:

```python
# @tear: 1
```

```javascript
// @tear: 1
```

```html
<!-- @tear: 1 -->
```

```sql
-- @tear: 1
```

```css
/* @tear: 1 */
```

The regex pattern to match across all formats:

```
@tear:\s*([0-3])
```

The linter scans the first 5 lines of the file for this pattern. If no match is found, the file is treated as tear 3.

### Excluded files

The following are excluded from tear enforcement entirely (they don't need headers):

- Binary files (images, fonts, compiled assets)
- Lock files (`package-lock.json`, `yarn.lock`, `poetry.lock`, etc.)
- Generated files explicitly listed in `.tears.toml` under `exclude`
- Files matching patterns in `.gitattributes` marked as binary
- Markdown files, unless opted in via config
- Config/dotfiles (`.eslintrc`, `tsconfig.json`, etc.), unless opted in via config

---

## 3. Import Rule

**Default rule: a file can only import from files at its own tear level or better (lower number).**

| Importing file | Can import from |
|----------------|-----------------|
| Tear 0 | Tear 0 only |
| Tear 1 | Tear <= 1 |
| Tear 2 | Tear <= 2 |
| Tear 3 | Tear <= 3 |

This default means tear 0 code is the most protected — nothing untrusted can sneak into its dependency chain. Tear 3 code can use anything because it's already untrusted; restricting its imports doesn't add safety.

### Custom import rules

The default rule is a single integer comparison: `target_tear <= importer_tear`. When no `import_rules` are configured, this is the fast path — no lookups, no sets, just one `<=`.

For teams that need custom import ceilings, `import_rules` in `.tears.toml` overrides the defaults. Each key is a tear level; its value is the maximum tier it may import from — all tiers from 0 up to that value are permitted. Partial overrides are supported — unspecified tiers fall back to the default rule.

```toml
# Default (import_rules omitted — uses "<=" rule):
# [import_rules]
# "0" = 0
# "1" = 1
# "2" = 2
# "3" = 3

# Example: relax tier 1 to allow importing from tier 2
[import_rules]
"1" = 2    # only override the tier that needs it
```

```toml
# Example: 6-tier system where 0-2 are a trusted zone
[import_rules]
"0" = 2
"1" = 2
"2" = 2
"3" = 3
"4" = 4
"5" = 5
```

**Implementation:** when `import_rules` is present, the config loader resolves the full matrix at load time (filling in defaults for unspecified tiers) and converts each max value to a `frozenset(range(max + 1))`. The per-import check becomes a single set membership test. When `import_rules` is absent (the common case), the check is just `target_tear <= importer_tear`.

**Validation rules:**
- Every tier from 0 to `max_tear` must have an entry (missing entries fall back to the default rule for that tier).
- Values must be valid tear levels (0 to `max_tear`). A max below the tier itself is allowed — it means that tier may only import from more-trusted code.

### What counts as an import

The linter recognizes these import forms:

**Python:**
```python
import foo.bar
from foo.bar import baz
from . import sibling
from ..parent import thing
```
and in the future:
**JavaScript/TypeScript:**
```javascript
import { x } from './auth/tokens'
import x from '../core/db'
const x = require('./auth/tokens')
```

**Go:**
```go
import "myproject/auth/tokens"
```

**Additional languages can be added via config (see Section 6).**

### Import resolution

The linter maps import paths to files using straightforward file-system resolution relative to the project root. It does NOT:

- Resolve third-party/external packages (these are ignored — no `@tear` header = not enforced)
- Follow re-exports through barrel files (it checks the directly imported file only)
- Evaluate dynamic imports or runtime requires

If an import cannot be resolved to a file in the repo, it is skipped. The linter is conservative: it only flags what it can definitively resolve.

---

## 4. Directory Requirements

The config file `.tears.toml` at the repo root can declare minimum tear levels for directories:

```toml
[directory_requirements]
"src/auth" = 0
"src/db" = 0
"src/core/models" = 0
"src/api" = 1
"src/services" = 1
"scripts" = 3        # anything goes
"tests" = 3          # anything goes
"tools/internal" = 2
```

A file at `src/auth/tokens.py` with `# @tear: 2` would fail the check — the directory requires tear 0.

When a file's declared tear level doesn't meet the directory's minimum, the linter reports a violation. This catches cases where a file was correctly demoted to tear 3 by AI tooling but now lives in a directory that demands better — the file must be properly reviewed and promoted before the PR can merge.

If no directory requirement is configured for a path, any tear level is acceptable.

### Directory matching

The most specific (longest) matching prefix wins. Given:

```toml
[directory_requirements]
"src" = 1
"src/auth" = 0
```

A file at `src/auth/tokens.py` must be tear 0.  
A file at `src/utils/helpers.py` must be tear 1.

---

## 5. Claude Code Hook

A Claude Code post-edit hook that fires after every file write. Its behavior is simple and mechanical:

1. After Claude Code writes or edits any file, the hook reads the first 5 lines.
2. If a `@tear` header exists, overwrite the value to `3`.
3. If no header exists, insert `# @tear: 3` (with appropriate comment syntax) as the first line of the file.

### Implementation: `.claude/hooks/post-edit.sh`

This is a shell script registered as a Claude Code hook. It receives the path of the edited file as an argument.

**Behavior:**

- Detects the file's comment syntax from its extension.
- Uses `sed` or equivalent to find and replace the tear value, or prepend the header.
- Runs synchronously before the edit is presented to the user.
- Does NOT modify binary files, lock files, or files matching exclude patterns from `.tears.toml`.

**The key design point**: this is not Claude cooperating by instruction. It's a mechanical hook that runs outside Claude's context. Claude's system prompt / CLAUDE.md should ALSO instruct it to set tear 3 on new files, but the hook is the enforcement backstop — it doesn't rely on prompt compliance.

### What the human sees

After Claude edits `src/utils/parser.py` (previously tear 1), the diff in the commit will show:

```diff
- # @tear: 1
+ # @tear: 3
```

The human can then:

- **Leave it** — they accept the file is now tear 3. Fast, no review needed.
- **Change it back to 1** — they're attesting they read every line Claude wrote and take responsibility. The diff will show no tier change (the `-1 +3 +1` collapses to no net change).
- **Set it to 2** — they glanced at it, confirmed no security issues, but didn't deeply review the logic.

### CLAUDE.md addition

In addition to the mechanical hook, the project's `CLAUDE.md` should include:

```markdown
## tears Review Policy

Every source file has a `@tear` header (0-3). When you create a new file, 
add `# @tear: 3` as the first line (using the appropriate comment syntax).

Do not modify existing `@tear` headers to any value other than 3.

Tear levels:
- 0: Deeply reviewed, security-critical
- 1: Reviewed by a human
- 2: Eyeballed for security
- 3: Unreviewed (this is what your output is)
```

---

## 6. Configuration: `.tears.toml`

Full configuration schema. Fields marked **(future)** are planned but not yet implemented in v1.

```toml
# .tears.toml

# Maximum tear level (default 3). Extend to 5 for a 6-tier system.
max_tear = 3

# Files/patterns excluded from tear enforcement entirely
exclude = [
  "**/*.generated.py",
  "migrations/**",
]

# Minimum tear level required per directory
[directory_requirements]
"src/auth" = 0
"src/db" = 0
"src/core" = 1
"src/api" = 1
"scripts" = 3

# Import resolution settings
[imports]
# Root directories for import resolution (relative to repo root)
source_roots = ["src", "lib"]

# Import rules override (optional — if omitted, uses default "<= tier" rule)
# Keys are tier numbers (as strings); values are the max tier that tier may import from.
# [import_rules]
# "1" = 2    # tier 1 may also import from tier 2

# Missing header behavior
missing_header = "warn"    # "warn" | "error"
```

The following config keys are **planned for future versions** and not yet implemented in v1:

- `include_extensions` — limit scanning to specific file extensions (v2, multi-language)
- `imports.aliases` — TypeScript/Babel path aliases like `"@/" = "src/"` (v2)
- `strict_promotion` — require tier promotions to be in separate commits (v1.5)
- `test_policy` — special handling for test files: `"exclude"` | `"inherit"` | `"enforce"` (v1.5)

---

## 7. CLI Interface

### `tears [PATH]` *(v1 — implemented)*

The only command in v1. Runs a full scan of `PATH` (default: current directory).

```
tears              # scan the repo from cwd
tears src/         # scan a specific subdirectory
```

Checks every `.py` file for:

1. **Header presence** — every included file has a `@tear` header in its first 5 lines. Missing = treated as `max_tear`, reported as warning or error per config.
2. **Directory compliance** — file's tear level meets the `directory_requirements` for its path.
3. **Import compliance** — every resolvable in-repo import targets a file at equal or better tier.

Exit code 0 = all checks pass. Exit code 1 = violations found. Exit code 2 = config error.

Output format:

```
FAIL  src/auth/tokens.py (tear 2)
  - directory requires tear 0, file is tear 2

FAIL  src/utils/parser.py (tear 3)
  - imports src/core/models.py (tear 1): tear 3 cannot import from tear 1

WARN  src/utils/helpers.py
  - missing @tear header (treated as tear 3)

OK    src/api/routes.py (tear 1)

3 files checked, 2 failures, 1 warning
```

---

The following commands are **planned for future versions** and not yet implemented.

### `tears init` *(planned — v1.0)*

Bootstraps the system in an existing repo:

1. Creates a default `.tears.toml`.
2. Scans all files and adds `# @tear: 1` headers to existing files (on the theory that existing code was previously reviewed by humans under the old process).
3. Optionally registers the Claude Code hook in `.claude/settings.json`.
4. Prints a summary of what it did and next steps.

The initial tear level is configurable (`--default-tear 1`). You might want everything to start at 2 if you're not confident in prior review quality.

### `tears promote FILE TEAR` *(planned — v1.5)*

Helper command for explicit promotion. Modifies the working tree to change a file's `@tear` header. This creates a clean audit trail when committed separately from code changes.

```bash
tears promote src/utils/parser.py 1
# Changes the header from whatever it was to tear 1
# The developer commits this change, signaling they've reviewed the file
```

### `tears report` *(planned — v1.5)*

Generates a summary of the repo's tear distribution:

```
Tear 0:  45 files  (12%)  — src/auth, src/db, src/core
Tear 1: 203 files  (54%)  — src/api, src/services, lib
Tear 2:  67 files  (18%)  — src/utils, tools
Tear 3:  59 files  (16%)  — scripts, recent AI output
Missing: 12 files          — config files (excluded)
```

---

## 8. GitHub Action *(planned — v1.0)*

> **Not yet implemented.** `tears` is not on PyPI and `tears --changed` (diff mode) is not
> yet implemented. This section describes the planned integration.

A GitHub Action that runs `tears` on every PR, checking only the files changed in the PR.

### `.github/workflows/tears.yml`

```yaml
name: tears
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  tears:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # need full history for diff

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install tears
        run: pip install tears-cli  # package name TBD; not yet on PyPI

      - name: Run tears on changed files
        run: tears --changed origin/${{ github.base_ref }}
```

### PR comment integration (optional enhancement)

The Action can optionally post a PR comment summarizing tear status of changed files:

```
## tears Summary

| File | Tear | Directory Req | Import Issues |
|------|------|---------------|---------------|
| src/auth/tokens.py | ❌ 2 (req: 0) | FAIL | — |
| src/utils/parser.py | ⚠️ 3 | OK | imports tear 1 |
| src/api/routes.py | ✅ 1 | OK | — |

**2 failures** must be resolved before merge.
```

---

## 9. Edge Cases and Design Decisions

### New files without headers

Treated as tear 3. The linter warns but does not hard-fail (configurable via `missing_header`). The Claude Code hook will add the header to any new file it creates, and `tears init` will add headers to existing files during adoption.

### Files with multiple tear headers (shouldn't happen)

If multiple `@tear` lines exist in the first 5 lines, the linter takes the WORST (highest number) and warns about the duplicate.

### Tear promotion in the same PR as code changes

Allowed by default. If a human edits code AND changes the tear from 3 to 1 in the same PR, they're attesting that the whole file is reviewed. The diff makes this visible to other reviewers. Some teams may want to require promotion in a separate PR — this can be configured via `strict_promotion: true` *(planned — v1.5; not yet implemented)*.

### Circular imports

Not this tool's problem. tears only checks the direction of the tear relationship on each import edge, not graph structure. Use your language's existing tooling for circular dependency detection.

### Test files importing from higher-tier code

Tests typically need to import the code they're testing. Three options configurable via `test_policy` *(planned — v1.5; not yet implemented — work around by adding `tests/` to `exclude`)*:

1. **`exclude`** — list `tests/` in the exclude patterns. Tests don't have `@tear` headers and aren't subject to import checks.
2. **`inherit`** — a test file for `src/auth/tokens.py` (tear 0) should also be tear 0, because someone who reviews auth code should also review its tests.
3. **`enforce`** — tests are treated like any other file. They need appropriate `@tear` headers and follow import rules.

### Monorepo with multiple languages

The linter resolves imports per-language. A Python file importing a protobuf-generated file doesn't cross-check tear levels because the generated file is excluded. A TypeScript file importing from a shared TypeScript library does get checked. Cross-language boundaries (e.g., a Python service calling a Go service via API) are out of scope — those aren't file-level imports.

### Performance

The linter's work per file:
1. Read first 5 lines → extract tear level. O(1) per file.
2. Regex-scan for import statements → list of import paths. O(n) where n is lines in file, but short-circuits after the import block in most languages.
3. Resolve each import to a file path → read that file's first 5 lines. O(1) per import.
4. Compare tear levels. O(1).

For a PR touching 20 files, each importing 10 things on average, that's ~200 file header reads. Sub-second. For a full repo scan of 5,000 files, still under 5 seconds.

No AST parsing. No dependency graph construction. No package resolution. Just string matching and file reads.

---

## 10. Adoption Strategy

### Phase 1: Visibility (week 1)

- Run `tears init --default-tear 1` to add headers to all existing files *(requires `tears init`, planned for v1.0)*.
- Add the Claude Code hook.
- Add the CLAUDE.md instructions.
- Run `tears` to see current state. Fix violations or adjust `directory_requirements`.
- Let the team see the `@tear` annotations and get used to them.

### Phase 2: Import enforcement (week 2-3)

- Turn on import compliance checking (exit 1 on violations).
- Configure directory requirements for the most critical directories (`src/auth`, `src/db`).
- Run `tears` to surface existing violations and fix them.

### Phase 3: Full enforcement (week 4+)

- Enable directory requirements across all configured paths.
- Enable `strict_promotion` if desired *(planned — v1.5)*.
- Enable `missing_header: error`.
- Periodic `tears report` to track tear distribution over time *(planned — v1.5)*.

---

## 11. Future Considerations (Not in v1)

- **Git blame integration**: auto-detect if a file's last significant edit was by an AI tool (by author email or commit trailer) and flag files that are tear 1+ but were last substantially modified by AI without a subsequent human promotion.
- **Tear decay**: files that haven't been reviewed in N months could auto-demote (e.g., tear 1 → tear 2) to force periodic re-review of critical code.
- **PR-level tear summary**: a dashboard showing what percentage of the codebase is at each tear level, trending over time.
- **IDE integration**: VS Code / JetBrains extensions that show the tear level in the gutter or file tab, and highlight imports that would violate tear rules before you even commit.
- **Promotion ceremony**: require a specific PR label or review comment (`/promote tear-0`) to move a file to tear 0, enforced by a GitHub bot, so that tear 0 promotions are always a deliberate act.
