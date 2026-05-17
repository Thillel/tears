<!-- @tear: 1 -->

# Roadmap

This roadmap tracks future work only. Shipped behavior belongs in [README.md](./README.md);
durable design rationale belongs in [DESIGN.md](./DESIGN.md).

## Near Term

1. Add direct grimp builder tests.

   Lock down current discovery behavior before changing scan semantics: package discovery,
   source roots, ignored directories, excluded files, empty package roots, flat files, and
   namespace packages.

2. Make `tears init` non-mutating by default and add `--missing-only`.

   `tears init` should create `.tears.toml` only, using `default_tear = 1` so existing
   headerless files can be scanned immediately without a large mechanical diff. Rewriting
   existing files should require an explicit follow-up command.

   The generated TOML should explain both adoption modes:

   ```toml
   # Soft trial mode: existing files without @tear headers are treated as reviewed.
   # Full adoption:
   #   1. Run: tears set . --tear 1 --missing-only
   #   2. Change default_tear to 3, or remove it and set missing_header = "error".
   default_tear = 1
   missing_header = "warn"
   ```

   Add `--missing-only` to `tears set` so full adoption can tag only files that lack a
   header, without overwriting existing deliberate `0`, `2`, or `3` tiers.

3. Fix scan target semantics and make empty scans suspicious.

   `tears PATH` should find the repo root, load config from that root, build the graph
   from the repo root, and filter results to `PATH`. Today `PATH` is treated as the scan
   root.

   `tears file.py` should either check that file directly or fail with a clear message.
   It must not silently report `0 files checked` for an existing Python file.

   If a directory contains Python files and `tears` checks zero files, emit a warning or
   fail with an explanation.

4. Decide and implement consistent `.gitignore` handling.

   Today the scanner partially respects gitignore during top-level package discovery,
   while the hook only honors `.tears.toml` `exclude`. Decide the policy explicitly,
   then make scanner and hook behavior match. The likely default is: scanner ignores
   gitignored files, hook does not mutate gitignored files, and `exclude` remains for
   tracked files that are intentionally outside tears enforcement.

5. Add an AST/file-walking builder.

   The current grimp builder is useful for importable Python packages but misses flat
   scripts and namespace packages. A fallback builder should cover ordinary Python files
   and reduce dependency on package layout.

6. Promote this repo's own tiers after review.

   As development chores, review and lower tears on tests first, then implementation
   files. Test fixtures use `.notears` markers for now to record their reviewedness
   without normalizing deliberate fixture headers.

## Usability

1. Add `tears report`.

   Show tier distribution across the repo so teams can see review debt.

2. Add JSON output.

   Machine-readable output is needed for GitHub annotations, IDE integrations, and
   downstream automation.

3. Add changed-file mode.

   A `--changed` or `--diff` mode can make CI faster once scan target semantics are
   correct.

4. Add test policy support.

   Real projects need explicit handling for tests, such as excluding tests from import
   checks or applying separate defaults.

5. Improve onboarding output.

   `tears init` should print next steps: add hook, add pre-commit, run `tears`, then
   tighten directory requirements.

## Hooks and Integrations

1. Package the Codex hook for reuse.

   The committed `.codex/config.toml` gives this repo a working Codex hook, and Codex
   asks on startup whether to enable it. Longer term, document or package the install
   path so users can add the hook without copying internal repo files.

2. Harden the OpenCode plugin.

   Remove debug logging, handle all files in multi-file patches, and pass paths without
   shell interpolation risk.

3. Improve GitHub Action self-tests.

   Test the local action implementation in PRs instead of always testing `@main`.

4. Add GitHub annotation support.

   This likely depends on JSON output.

5. Add editor integration.

   Useful features: gutter tier display, quick demote/promote commands, and inline import
   violation diagnostics.

## Larger Scope

1. Multi-language scanning.

   JS/TS and Go are plausible next targets, but each language needs real import
   resolution. Header insertion alone is not enough.

2. Import aliases.

   JS/TS projects need path alias support such as `@/` to `src/`.

3. Promotion policy options.

   Teams may want stricter workflows for tier-0 promotions, separate promotion commits,
   or domain-owner approvals.

4. Trust history.

   Git blame or commit metadata could detect suspicious promotions, but this should come
   after the basic scanner is precise.
