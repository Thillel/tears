<!-- @tear: 3 -->

# Roadmap

## Phase 0: Truth & docs

| # | What | Why |
|---|------|-----|
| 1 | **Update spec.md** — change `.tears.yml` → `.tears.toml` everywhere; fix CLI description to match the real `tears [path]`; add explicit "future" markers on init/promote/report/include_extensions/aliases/strict_promotion | The spec describes a different tool than what exists. Every other decision flows from having a single source of truth. |
| 2 | **Fix README config example** — the YAML-in-TOML syntax is broken | First impression of the tool. |
| 3 | **Mark ghost features in plan.md** — `.gitignore` (unimplemented), `tears file.py` (broken). Either fix or mark deferred. | Plan claims drive contributor expectations. |
| 4 | **Fill missing `expected.txt` files** for fixtures 07–15 | 9 of 15 integration test paths are unpinned. End-to-end confidence. |
| 5 | **Add GitHub Actions CI** — run `make check` on PR | No CI at all is a red flag. |

*Phase 0 is complete.*

---

### Phase 1: v0.1.0 — ship to PyPI

| # | What | Status | Why |
|---|------|--------|-----|
| 6 | **`tears init`** — scaffolds `.tears.toml`, adds `@tear: N` headers to all existing files, optionally registers the hook | ✅ done | The #1 onboarding gate. Less urgent now that `default_tear` lets you scan without tagging every file, but still needed for teams that want explicit headers everywhere. |
| 6a | **`default_tear` / `default_tears` / `--default-tear`** — assume a tier for headerless files, globally or per folder | ✅ done | Lets teams try tears on an existing codebase in minutes without touching a single source file. |
| 7 | **PyPI package** — `uv build && uv publish` as `tears-cli` | ✅ deployed (`0.1.0a1`; targeting `v0.1.0`) | Can't be installed outside this repo. |
| 8 | **Pre-commit hook** — `.pre-commit-hooks.yaml` + `tears pre-commit` entry point | ✅ done | Catches violations in milliseconds, not CI-minutes. Reaches teams without Claude Code. |
| 9 | **GitHub Action** — reusable workflow that runs `tears` on PRs | ✅ done | Required for CI integration. |
| 10 | **Fix `.gitignore` handling** — add `git check-ignore` filtering in the graph builder, or formally document the deferral | ✅ done | Scanning `.venv/` or `node_modules/` is broken and slow. |
| 11 | **ANSI colored output** — red FAIL / yellow WARN / green OK | ✅ done | 20-line change, big impact on perceived quality. |
| 12 | **`--version` flag** | ✅ done | Baseline CLI hygiene. |

---

### Phase 2: v0.2.0 — usability

| # | What | Why |
|---|------|-----|
| 13 | **`tears promote FILE TIER`** — superseded by `tears down FILE --tear N` (already shipped) | — |
| 14 | **`tears report`** — tier distribution summary | The "look, 80% of our code is reviewed" evidence for team buy-in. |
| 15 | **`--changed` / `--diff` mode** — compare against git base branch, check only touched files | Fast CI for PRs. Without this, a full scan is the only option. |
| 16 | **`test_policy`** — at minimum auto-exclude `test_*` files from import violations | The #1 false positive in any real codebase. |
| 17 | **AST-based builder** (Builder A from plan §2.2) — zero-dependency fallback alongside grimp | Handles flat scripts, namespace packages, single files. Reduces grimp coupling. |
| 18 | **`tears file.py`** — per-file mini-check that bypasses grimp | Unblocks editor integration and pre-commit for individual files. |
| 19 | **JSON output** (`--format json`) | Machine-parseable output for GitHub annotations, IDE plugins. |
| 20 | **`test_grimp_builder.py`** — direct adapter unit tests | The sole ImportGraph implementation has zero direct tests. |

---

### Phase 3: Community infrastructure

| # | What | Why |
|---|------|-----|
| 21 | **CONTRIBUTING.md** — dev setup, test conventions, PR workflow | Lowers bar for external contributors. |
| 22 | **Good-first-issue labels + issue templates** | Signal that the project is open for contributions. |
| 23 | **CHANGELOG.md** | Shows momentum. |
| 24 | **PyPI README badges** — build status, Python versions, license | Trust signal on package page. |
| 25 | **`conftest.py` with `RepoBuilder` fixture** | Makes adding integration tests easy for contributors. |

---

### Phase 4: v1.0 — multi-language & advanced

| # | What | Why |
|---|------|-----|
| 26 | **JS/TS import extraction** — tree-sitter or regex-based builder | Python-only limits addressable market. The hook already handles JS/TS headers. |
| 27 | **`imports.aliases` support** — `@/` → `src/` path mapping | Required for real-world JS/TS/Babel projects. Spec'd but not implemented. |
| 28 | **`include_extensions` config** — scan only `.py .js .ts` etc. | Foundation for multi-language. |
| 29 | **Git blame integration** — flag AI-written files marked tier 1+ without human promotion | Closes the loop the hook started. |
| 30 | **VS Code extension** — gutter tier indicators, violation highlights | Best-in-class DX. |
| 31 | **Tear decay** — auto-demote files not reviewed in N months | Forces periodic re-review of critical code. |
| 32 | **PR comment bot** — posts tier summary on every PR | Social accountability; makes tiers visible to whole team. |

---

## Build order

Within each phase, build top-down. Each item assumes everything above it is done.

Phase 1 is complete. All items shipped: `init`, PyPI , pre-commit, GitHub Action, `.gitignore` filtering, colors, and `--version`. Next: cut `v0.1.0` stable.

Phase 2 rounds out usability gaps that emerge from real usage.

Phase 3 enables external contributors to help with everything above.

Phase 4 is the big expansion.

---

## What NOT to do

- **Tear decay.** Complex semantics, unclear value proposition.
- **PR comment bot.** Only helps teams already using tears. Build the core first.
- **Hook insertion for more file types.** 50+ is enough.
- **Shell completions.** Premature optimization.
- **`strict_promotion`.** Config noise with unclear benefit.
