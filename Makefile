# @tear: 1
.PHONY: lint test fmt check update-snapshots

lint:
	uv run ruff check src tests
	uv run pyright src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

test:
	uv run pytest

# Regenerate `expected.txt` for every fixture under tests/scan/fixtures/.
# Run after adding a fixture or changing scan/checker output. Review the
# resulting diffs carefully — this is the only way the test suite knows
# what the right answer is.
update-snapshots:
	TEARS_UPDATE_SNAPSHOTS=1 uv run pytest tests/scan

check: lint test
