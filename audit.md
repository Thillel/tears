<!-- @tear: 3 -->

# Plan vs. Implementation Audit

Snapshot of `src/tears/` and `tests/` against `plan.md`. **Valid as of 2026-05-11.**
Will go stale as work progresses — re-run when significant changes land.

## Verdict

Implementation is **very faithful to the plan**. The big decisions (DIP/Protocol, B1
grimp builder, bare `tears`, in-memory fake graph for checker tests, snapshot fixtures,
validation at config load, path-segment-aware directory matching) all show up correctly.
A few gaps (mostly Milestone 2+ work), a few deviations worth flagging, one plan entry
that's wrong and should be corrected.

---

## Matches the plan

**Architecture.** `graph/__init__.py` defines the `ImportGraph` Protocol as drafted in
§2.2; `grimp_builder.py` is the only concrete implementation; `checker.check()` depends
on the Protocol, not on grimp; `test_checker.py` uses an in-memory `FakeGraph` (with
`importers_of` raising `NotImplementedError`), no filesystem.

**Header parsing.** Regex is `^[ \t]*#[ \t]*@tear:[ \t]*(\d+)(?![\w.])`. Comment-marker-
at-line-start kills the `x = "# @tear: 0"` case. Negative lookahead kills `1.5`; absence
of leading-sign handling kills `-1`. Out-of-range values are rejected, not silently
clamped. Multi-header takes the worst.

**Rules.** `can_import` is `target_tier in resolved_rules[importer_tier]` — one set
membership. `check_directory_requirement` uses tuple-segment comparison, not
`startswith`. Trailing slashes normalized. Longest-prefix wins.

**Config.** Validation at `__post_init__`. `ConfigError` raised on malformed YAML,
non-mapping top level, missing self-import, `max_tear` overflow.
`resolved_import_rules()` fills defaults for unspecified tiers.

**Checker.** Composes header + rules over the graph. Missing-header treats file as
`max_tear` for downstream checks but emits a separate warn/fail per `missing_header`
config. Returns a structured `CheckReport` with `exit_code` / `failure_count` /
`warning_count`.

**CLI.** Bare `tears`, optional path arg, exit codes 0/1. `pyproject.toml` registers
`tears = "tears.cli:main"`.

**Fixture test.** `tests/scan/test_scan.py` copies fixtures into `tmp_path`, runs
`cli_main`, compares against `expected.txt` + `--- exit: N ---`.

---

## Gaps — specified by plan, not yet implemented

1. **`hook.py` missing.** The Claude Code `PostToolUse` hook is the actual differentiator
   of tears as a system — without it, the demotion mechanic doesn't work. Plan §3
   specifies it; §5 says "hook is independent — write whenever." No `tests/unit/test_hook.py`
   either. **Should be on the near-term todo list.**

2. **`test_grimp_builder.py` missing.** Plan §4.1 specifies it. Currently the only
   coverage of `grimp_builder.py` is implicit via the one fixture in `test_scan.py`.
   The adapter has real logic — `_build_module_index`, `_is_excluded`, glob translation
   with `**`, sys.path injection — that's worth direct tests, especially the
   multi-package case (`grimp.build_graph(*pkgs)`).

3. **Only 1 of 15 fixtures.** `01_clean_repo` exists. Plan lists 02 through 15 (tear
   violations, dir violations, missing headers, custom rules, excludes, path-segment
   matching, malformed config). Adding these is the actual Milestone 2+ work.

---

## Deviations from the plan — positive

- **`TEARS_UPDATE_SNAPSHOTS=1`** env var for regenerating `expected.txt`. Plan said
  "snapshot regen is a deliberate workflow"; this implements it cleanly.
- **Exit code 2 for config errors** (vs. 1 for violations, 0 for clean). Standard Unix
  convention; the plan didn't specify but this is the right call. **Worth adding to plan §7.**
- **Pyright strict mode** + ruff config + `Makefile` (`make lint test fmt check`). Plan
  didn't mandate but it's the right baseline for a strict-typing project.
- **`pyproject.toml` console script** registers `tears` as a real installable command, so
  `uv run tears` or `pipx install tears` works without `python -m`.

---

## Deviations worth flagging

1. **`.gitignore` is not respected.** Plan §2.7 says "respect `.gitignore` if `git` is
   available." Implementation walks `source_roots` via grimp + `rglob("*.py")` for the
   module index, and only filters by the explicit `exclude` config. In practice probably
   fine (grimp won't pick up files outside source roots), but a repo with `.gitignore`d
   temp files inside source roots would still be scanned. Decide whether to add
   `git check-ignore` filtering or drop the `.gitignore` mention from the plan.

2. **`tears file.py` with a file path is untested and probably broken.** Implementation
   passes any path to `grimp.build_graph(*package_names)`, which expects package names
   rooted in source_roots. Single-file scans aren't actually supported. Plan §2.7 had it
   as "TBD whether useful" — either implement (per-file mini-check) or remove from docs.

3. **Plan §8 says "Re-exports through `__init__.py` are not followed."** This is **wrong**
   under the current implementation. grimp creates the edge
   `auth/__init__.py → auth/tokens.py` from a `from .tokens import verify` statement.
   Concretely: if `auth/__init__.py` is tier 0 and re-exports from a tier-3
   `auth/_internal.py`, the edge `auth/__init__.py (tier 0) → auth/_internal.py (tier 3)`
   is in the graph and **gets flagged** — tier 0 cannot import from tier 3. The barrel-
   file wrapper fails its own contract. The only way to launder is to mark
   `auth/__init__.py` as excluded — which is the *excludes* laundering vector, still
   real. **The plan §8 entry about `__init__.py` re-exports should be removed.**

---

## Suggested next steps

1. **Build `hook.py` + `test_hook.py`.** The differentiator. Per plan §3: read affected
   file path from env, replace `@tear` value with `max_tear`, insert if missing (after
   shebang / encoding declaration), idempotent, no-op for excluded/non-`.py`.

2. **Add `test_grimp_builder.py`.** Cover: multi-package via `build_graph(*pkgs)`,
   exclude wrapper, `_build_module_index` edge cases, glob translation with `**`,
   namespace package handling, files with same name across packages.

3. **Add fixtures 02, 03** (tear violation, dir violation) at the integration boundary.
   These confirm the unhappy paths the unit tests already cover, but end-to-end.

4. **Update `plan.md` §8 and §7.** Remove the inaccurate `__init__.py` re-export
   limitation. Add exit code 2 for config errors to the decision log. Decide and
   document `.gitignore` behavior.
