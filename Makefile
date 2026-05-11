# @tear: 1
.PHONY: lint test fmt check

lint:
	uv run ruff check src tests
	uv run pyright src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

test:
	uv run pytest

check: lint test
