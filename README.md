<!-- @tear: 1 -->

# tears

**Tiered Enforcement, Authorship Review System.**
*Vibe-Code Responsibly*

`tears` is a small linter for repos where humans and AI tools both write code.
Every source file declares its review level via a `@tear` header (0 = deeply
reviewed, 3 = unreviewed AI output). A Claude Code hook mechanically demotes any
file it edits to tier 3. The diff makes the demotion visible — if you didn't
notice the tier dropped in your PR, you didn't review the code. `tears` then
enforces import rules and directory-level requirements based on those headers.

```python
# @tear: 0
import hashlib

def verify(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
```

## The mechanic

1. Every file has a `# @tear: N` header on one of its first 5 lines.
2. A Claude Code `PostToolUse` hook overwrites the value to `max_tear` (default 3)
   on every edit, *or* inserts the header if missing.
3. To restore a higher tier, a human edits the header back. The diff is the
   attestation: "I reviewed this."
4. `tears` checks every file's directory requirement and every import edge — a
   file may only import from files at its own tier or better.

## Status

Early. v1 is Python-only and scan-only (no `init` / `promote` / `report`
subcommands). Not yet on PyPI. Claude Code hook not implemented yet.
See [`plan.md`](./plan.md) for the v1 scope and
roadmap, [`spec.md`](./spec.md) for the broader vision, and
[`test-spec.md`](./test-spec.md) for the test design.

## Try it locally

```bash
git clone https://github.com/<user>/tears
cd tears
uv sync
uv run tears path/to/your/repo
```

Add a `.tears.yml` at the repo root:

```yaml
directory_requirements:
  src/auth: 0
  src/api: 1
imports:
  source_roots: ["src"]
missing_header: warn   # or "error"
```

## Development

```bash
make test       # pytest
make lint       # ruff + pyright (strict)
make fmt        # ruff format + autofix
make check      # lint + test
```

## License

MIT. See [`LICENSE`](./LICENSE).
