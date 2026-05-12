<!-- @tear: 3 -->

# Plan vs. Implementation Audit

Snapshot of `src/tears/` and `tests/` against `plan.md`. **Valid as of 2026-05-12.**
Supersedes the 2026-05-11 audit. Re-run when significant changes land.

## Verdict

Implementation is **fully aligned with the plan for Milestone 1 + most of v1 scope**.
The hook is live, the TOML migration is done, six fixtures pin behavior end-to-end, and
the architecture (DIP via `ImportGraph` Protocol) is unchanged. `make check` passes —
125 tests, ruff clean, pyright strict 0 errors. Remaining work is *coverage expansion*
(more fixtures, the grimp-adapter unit test) rather than load-bearing functionality.

---

## Matches the plan

**Architecture.** `graph/__init__.py` exposes the `ImportGraph` Protocol; `grimp_builder.py`
is the sole implementation; `checker.check()` depends on the Protocol; `test_checker.py`
uses an in-memory `FakeGraph`. SOLID/DIP boundary intact.

**Header parsing.** Regex enforces comment-marker-at-line-start, word-boundary after
digits, range validation against `max_tear`. Multi-header takes worst.

**Rules.** `can_import` is one set membership; `check_directory_requirement` is
path-segment aware; trailing slashes normalized; longest-prefix wins.

**Config.** `.tears.toml` via stdlib `tomllib` — **no third-party YAML dep** in v1.
Validation at `__post_init__`. Hard-fails on malformed TOML, non-integer rule keys,
self-import missing, `max_tear` overflow. Error messages use the *relative* file name
so snapshots stay stable.

**Hook.** `tears.hook` registered in `.claude/settings.json` for `Edit|Write|MultiEdit`.
Stdin-JSON and argv paths both covered. Silent on bad input. Falls back to defaults on
broken config so Claude Code's flow never breaks. `_find_repo_root` prefers `.git/` so
nested `.tears.toml` (test fixtures, monorepo subprojects) don't trick it.

**Checker.** Composes header + rules over the graph. Missing-header treats file as
`max_tear` for downstream checks but emits a separate warn/fail per `missing_header`
config. Structured `CheckReport` with `exit_code`/`failure_count`/`warning_count`.

**CLI.** Bare `tears`, optional path arg, exit codes 0/1/2 (clean/violations/config-error).
`pyproject.toml` registers `tears = "tears.cli:main"`.

**Fixture tests.** `tests/scan/test_scan.py` copies fixtures to `tmp_path`, runs
`cli_main`, compares stdout + optional stderr block + exit code against `expected.txt`.
**Six fixtures** pin: clean repo, tier 0→tier 3 violation, directory violation,
missing-header (warn + error), malformed config.

---

## Gaps — specified by plan, not yet implemented

1. **`test_grimp_builder.py` missing.** The adapter (sys.path injection,
   `_build_module_index`, exclude wrapper, glob translation with `**`, multi-package
   `build_graph(*pkgs)`) is only covered implicitly via the snapshot fixtures.
   Plan §4.1 specifies direct tests.

2. **`tears file.py`** (single-file scan) is untested and almost certainly broken — the
   CLI passes any path to `grimp.build_graph(*package_names)`, which expects package
   names rooted in source_roots. Plan §2.7 listed it as "TBD whether useful." Either
   implement (per-file mini-check that bypasses grimp) or remove from docs.

**Recently closed (since 2026-05-11):**
- All 15 fixtures from plan §4.2 are now in place. `08_submodule_resolution` confirms
  grimp resolves `from pkg import internal` to the submodule when it exists — proves
  the X.Y ambiguity worry was unfounded.
- Hook now demotes existing headers in **any comment style** (not just `.py`). The
  earlier "non-`.py` files have manual headers the hook never touches" gap is gone.
  Insertion stays `.py`-only — see plan §3 for the asymmetric-scope rationale.

---

## Deviations from the plan — positive

- **TOML migration** dropped `pyyaml` + `types-pyyaml`. Zero third-party config deps,
  cleaner error messages, better-defined spec. Recorded in plan §7.
- **`.notears` marker** at each fixture root. v1: pure human marker (tier inside as
  `# @tear: N` comment). Forward-compatible: future tears versions can read these as
  directory-level attestation. Recorded in plan §7.
- **`make update-snapshots`** wraps `TEARS_UPDATE_SNAPSHOTS=1 uv run pytest tests/scan`
  so regen is one command. The right workflow.
- **Exit code 2 for config errors** (0 clean, 1 violations, 2 config). Recorded in plan §7.
- **`_find_repo_root` prefers `.git/`** so the hook can't misidentify a fixture as the
  repo root. Recorded in plan §7.
- **stderr captured in snapshots** when non-empty (`--- stderr ---` block before
  `--- exit: N ---`). Lets the malformed-config fixture pin its error message.
- **Shared `tears/exclude.py`** for glob matching, used by both the graph builder and
  the hook. Avoids duplicated logic.
- **Console script + Makefile + ruff + pyright strict**. Right baseline for the project.

---

## Deviations worth flagging

1. **`.gitignore` is not respected.** Plan §2.7 says "respect `.gitignore` if `git` is
   available." Implementation walks `source_roots` via grimp + `rglob("*.py")`. Probably
   fine in practice (grimp won't pick up files outside source_roots), but worth deciding:
   add `git check-ignore` filtering or drop the `.gitignore` mention from the plan.

2. **Plan §8 still claims `__init__.py` re-exports aren't followed.** They are — grimp
   creates the edge `auth/__init__.py → auth/tokens.py` from `from .tokens import verify`,
   and tears checks it. The barrel-file laundering loophole only exists if `__init__.py`
   itself is excluded. The plan §8 entry should be removed (audit.md flagged this in the
   prior snapshot too — still not fixed).

3. **`tears file.py` single-file invocation.** Same status as the 2026-05-11 audit.

---

## Suggested next steps

1. **Knock out the rest of the fixtures (06–14).** Each is 5–10 minutes — copy a sibling,
   tweak tiers/config, run `TEARS_UPDATE_SNAPSHOTS=1 pytest tests/scan`, eyeball the
   `expected.txt`, commit. Biggest confidence-per-minute payoff.

2. **`test_grimp_builder.py`.** Direct adapter tests so refactoring grimp internals
   doesn't break us silently. Cover: multi-package via `build_graph(*pkgs)`, exclude
   wrapper, `_build_module_index` edge cases (`__init__.py` handling, files with the
   same name across packages), glob translation with `**`.

3. **Plan §8 cleanup.** Remove the wrong `__init__.py` re-exports limitation. Decide
   `.gitignore` behavior. Decide `tears file.py` (implement or drop).

4. **Decide on `.notears` future behavior.** Currently a human marker. v1.5 / v2
   candidates: (a) tears reads the tier and uses it as directory-level attestation,
   (b) tears warns on `.notears` dirs that don't have `# @tear: N` content, (c) a
   `--strict` flag refuses to scan repos with `.notears` directories outside excludes.
