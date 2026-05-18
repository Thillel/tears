<!-- @tear: 3 -->

# Roadmap

This roadmap tracks future work only. Shipped behavior belongs in [README.md](./README.md);
durable design rationale belongs in [DESIGN.md](./DESIGN.md).

## Near Term

1. Add an AST/file-walking builder.

   The current grimp builder is useful for importable Python packages but misses flat
   scripts and namespace packages. A fallback builder should cover ordinary Python files
   and reduce dependency on package layout.

2. Define target-filtering semantics.

   `tears PATH` is now documented as config/scan-root mode. Target filtering remains
   future work. A later release should decide whether to add an explicit form such as
   `tears --target PATH` or `tears check PATH`, where config is loaded from the repo root
   and results are filtered to a subpath.

3. Promote this repo's own tiers after review.

   As development chores, review and lower tears on tests first, then implementation
   files. Test fixtures use `.notears` markers for now to record their reviewedness
   without normalizing deliberate fixture headers.

4. Define remaining scope semantics in the design.

   The current docs cover root-mode scanning, gitignore policy, excludes, fixture
   dogfooding, and empty-scan warnings. Before broadening scanner coverage, finish the
   design for target filtering, unsupported files, mixed-language repos, and future
   single-file behavior.

5. Decide and enforce excluded-import semantics.

   Excluded files currently disappear from the graph, so trusted in-scope code can import
   excluded repo code without warning. Decide whether that should warn, fail, or be
   explicitly allowed by configuration, then expose enough graph information for the
   checker to report it.

6. Keep future-behavior fixtures ahead of scanner work.

   Fixture repos are grouped by suite under `tests/scan/fixtures/<suite>/`. Continue
   adding strict xfailed fixtures for scanner behavior before implementation, especially
   where language import resolution has policy choices.

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

6. Make the README more task-oriented.

   Organize public docs around real adoption tasks: try without rewriting files, adopt
   fully, protect sensitive directories, install AI edit hooks, run in CI, interpret
   failures, and promote after review.

7. Document promotion workflows.

   Define recommended expectations for tier-0 and tier-1 promotions, same-PR promotion,
   separate promotion commits, domain-owner review, and what tier-2 review means in
   practice.

8. Add dry-run mode for mutation commands.

   Bulk `init`, `set`, `up`, and `down` workflows should be previewable before rewriting
   files, especially during adoption.

9. Align Makefile targets and docs.

   `make lint`, README, and agent instructions should agree on which commands check only
   and which commands mutate formatting or apply fixes.

10. Add `promote` and `demote` aliases.

   Keep `down` and `up` as short forms, but expose intent-revealing aliases for users
   who do not yet think in tear-number direction.

11. Improve CLI help safety guidance.

   Help output should call out the core caveats users need before trusting results,
   especially path semantics, empty scans, and Python package-layout scope until those
   behaviors are fixed.

## Hooks and Integrations

1. Package the Codex hook for reuse.

   The committed `.codex/config.toml` gives this repo a working Codex hook, and Codex
   asks on startup whether to enable it. Longer term, document or package the install
   path so users can add the hook without copying internal repo files.

2. Improve GitHub Action self-tests.

   Test the local action implementation in PRs instead of always testing `@main`.

3. Add GitHub annotation support.

   This likely depends on JSON output.

4. Add editor integration.

   Useful features: gutter tier display, quick demote/promote commands, and inline import
   violation diagnostics.

5. Add CI coverage/scope checks.

   CI should be able to fail on suspiciously small scan coverage, including accidental
   `0 files checked` runs once scan scope diagnostics exist.

6. Add hook install and doctor commands.

   Provide a reliable installation and verification path for Codex, Claude, and OpenCode
   hooks so users can confirm AI edits are actually being demoted.

## Larger Scope

1. Multi-language scanning.

   JS/TS and Go are plausible next targets, but each language needs real import
   resolution. Header insertion alone is not enough. The TypeScript fixture suite already
   records first-pass expectations for relative imports, side-effect imports, export-from
   dependencies, `index.ts` resolution, and `import type` trust dependencies.

2. Import aliases.

   JS/TS projects need path alias support such as `@/` to `src/`.

3. Promotion policy options.

   Teams may want stricter workflows for tier-0 promotions, separate promotion commits,
   or domain-owner approvals.

4. Trust history.

   Git blame or commit metadata could detect suspicious promotions, but this should come
   after the basic scanner is precise.

5. Config compatibility story.

   Before stable releases, decide whether `.tears.toml` needs a schema version or another
   compatibility mechanism for future config changes.

6. Re-export and transitive trust analysis.

   Decide whether imports through package `__init__.py` re-exports need deeper trust
   analysis beyond direct grimp edges.
