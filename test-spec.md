<!-- @tear: 3 -->

# tears — Test Suite Specification

## Design Principles

- Tests read like documentation. A new contributor should understand what tears does by reading the test file alone.
- Parametrized tables for every rule-based behavior. The test logic is written once; the cases are a readable table of inputs and expected outputs.
- Realistic but minimal fixtures. Each test builds tiny file trees that mirror real monorepo structures.
- Test names describe behavior, not implementation: `test_tear3_cannot_import_from_tear1`, not `test_check_import_validation_logic`.
- Strict typing throughout. All test helpers and fixtures return typed objects.

---

## Project Structure

```
tests/
├── conftest.py                    # Shared fixtures: tmp repos, file builders, config builders
├── unit/
│   ├── test_header_parsing.py     # @tear header extraction from files
│   ├── test_import_extraction.py  # Import statement recognition across languages
│   ├── test_import_resolution.py  # Mapping import paths to files on disk
│   ├── test_tear_comparison.py    # Core import rule: can this tear import from that tear?
│   ├── test_directory_rules.py    # Directory requirement matching and enforcement
│   ├── test_config.py             # .tears.yml parsing, defaults, validation, custom tier counts
│   └── test_hook.py               # Claude Code hook: header replacement and insertion
├── integration/
│   ├── test_check.py              # Full `tears check` against realistic file trees
│   ├── test_scan.py               # Full `tears scan` against realistic file trees
│   ├── test_init.py               # `tears init` bootstrapping behavior
│   ├── test_promote.py            # `tears promote` header modification
│   └── test_report.py             # `tears report` output formatting
└── fixtures/
    └── repos/                     # Pre-built mini repo trees for integration tests
        ├── clean_monorepo/        # All files pass, no violations
        ├── import_violations/     # Various import rule violations
        ├── directory_violations/  # Files that don't meet directory requirements
        ├── mixed_languages/       # Python + TypeScript + Go in one repo
        └── custom_tiers/          # Repos configured with non-default tier counts
```

---

## Shared Fixtures (`conftest.py`)

```python
"""Shared fixtures for tears tests.

The core fixture is `repo` — a builder that creates temporary file trees
with @tear headers, letting tests declare realistic mini-repos in a few lines.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from dataclasses import dataclass, field
from tears.config import TearsConfig


@dataclass
class RepoFile:
    """A file in a test repository."""
    path: str
    content: str
    tear: int | None = None  # None means no @tear header


@dataclass
class RepoBuilder:
    """Builds temporary file trees for testing.
    
    Usage:
        repo = builder.add("src/auth/tokens.py", tear=0, content="import src.db.models")
                      .add("src/db/models.py", tear=0, content="class User: pass")
                      .build()
    """
    root: Path
    files: list[RepoFile] = field(default_factory=list)
    config: dict | None = None

    def add(
        self,
        path: str,
        *,
        tear: int | None = None,
        content: str = "",
        lang: str | None = None,
    ) -> RepoBuilder:
        """Add a file to the repo. Comment syntax is inferred from extension."""
        header = _make_header(path, tear, lang) if tear is not None else ""
        full_content = f"{header}\n{content}" if header else content
        self.files.append(RepoFile(path=path, content=full_content, tear=tear))
        return self

    def with_config(self, **kwargs) -> RepoBuilder:
        """Set .tears.yml configuration."""
        self.config = kwargs
        return self

    def build(self) -> Path:
        """Write all files to disk and return the repo root path."""
        for f in self.files:
            full_path = self.root / f.path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(f.content)
        if self.config is not None:
            _write_config(self.root, self.config)
        return self.root


@pytest.fixture
def builder(tmp_path: Path) -> RepoBuilder:
    """Provides a RepoBuilder rooted in a temporary directory."""
    return RepoBuilder(root=tmp_path)


@pytest.fixture
def default_config() -> TearsConfig:
    """The default tears configuration (4 tiers, 0-3)."""
    return TearsConfig()


def _make_header(path: str, tear: int, lang: str | None = None) -> str:
    """Generate the appropriate @tear header for a file's comment syntax."""
    ext = lang or Path(path).suffix
    comment_styles = {
        ".py": "#",
        ".js": "//",
        ".ts": "//",
        ".tsx": "//",
        ".jsx": "//",
        ".go": "//",
        ".rs": "//",
        ".java": "//",
        ".rb": "#",
        ".sql": "--",
    }
    prefix = comment_styles.get(ext, "#")
    return f"{prefix} @tear: {tear}"


def _write_config(root: Path, config: dict) -> None:
    """Write a .tears.yml config file."""
    import yaml
    (root / ".tears.yml").write_text(yaml.dump(config))
```

---

## Unit Tests

### `test_header_parsing.py`

```python
"""Tests for @tear header extraction.

The header parser reads the first 5 lines of a file and extracts the tear level.
It must handle every comment syntax, missing headers, malformed values, and edge cases.
"""

import pytest
from tears.parser import parse_tear_level


# --- Basic extraction across comment syntaxes ---

@pytest.mark.parametrize("content, expected", [
    # Python / Ruby / Shell
    ("# @tear: 0\nimport os",                           0),
    ("# @tear: 1\ndef main(): pass",                    1),
    ("# @tear: 2\n# some other comment",                2),
    ("# @tear: 3\n",                                    3),

    # JavaScript / TypeScript / Go / Rust / Java
    ("// @tear: 0\nimport { x } from './y'",            0),
    ("// @tear: 1\nconst x = 1;",                       1),

    # SQL
    ("-- @tear: 0\nSELECT 1;",                          0),

    # HTML
    ("<!-- @tear: 1 -->\n<html>",                        1),

    # CSS
    ("/* @tear: 2 */\nbody { }",                         2),
], ids=[
    "python-tear-0",
    "python-tear-1",
    "python-tear-2",
    "python-tear-3",
    "js-tear-0",
    "js-tear-1",
    "sql-tear-0",
    "html-tear-1",
    "css-tear-2",
])
def test_parses_tear_from_comment_syntax(content: str, expected: int):
    assert parse_tear_level(content) == expected


# --- Header position within first 5 lines ---

@pytest.mark.parametrize("content, expected", [
    # Line 1 (most common)
    ("# @tear: 0\ncode here",                            0),

    # Line 2 (after shebang)
    ("#!/usr/bin/env python3\n# @tear: 1\nimport os",    1),

    # Line 3 (after shebang + encoding)
    ("#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n# @tear: 2\n", 2),

    # Line 5 (last valid position)
    ("# license\n# license\n# license\n# license\n# @tear: 0\n", 0),

    # Line 6 (too late — should NOT be found)
    ("# a\n# b\n# c\n# d\n# e\n# @tear: 0\n",          None),
], ids=[
    "line-1",
    "line-2-after-shebang",
    "line-3-after-shebang-and-encoding",
    "line-5-last-valid",
    "line-6-too-late",
])
def test_header_position_within_first_5_lines(content: str, expected: int | None):
    assert parse_tear_level(content) == expected


# --- Missing and malformed headers ---

@pytest.mark.parametrize("content, expected", [
    # No header at all
    ("import os\ndef main(): pass",                      None),

    # Empty file
    ("",                                                  None),

    # Looks like a header but wrong format
    ("# tear: 0",                                         None),  # missing @
    ("# @tear 0",                                         None),  # missing colon
    ("# @tear: five",                                     None),  # non-numeric
    ("# @tear: -1",                                       None),  # negative
    ("# @tear: 4",                                        None),  # out of range (default 0-3)
    ("# @tear: 1.5",                                      None),  # float

    # Valid header buried in a string (should NOT match)
    ('x = "# @tear: 0"\n',                                None),
], ids=[
    "no-header",
    "empty-file",
    "missing-at-sign",
    "missing-colon",
    "non-numeric",
    "negative",
    "out-of-range-default",
    "float",
    "inside-string-literal",
])
def test_missing_and_malformed_headers(content: str, expected: int | None):
    assert parse_tear_level(content) == expected


# --- Multiple headers (takes worst) ---

def test_multiple_headers_takes_worst():
    content = "# @tear: 0\n# @tear: 2\ncode"
    result = parse_tear_level(content)
    assert result == 2  # worst (highest number) wins


# --- Configurable tier count ---

@pytest.mark.parametrize("max_tear, content, expected", [
    # Default: 4 tiers (0-3)
    (3, "# @tear: 3",   3),
    (3, "# @tear: 4",   None),  # out of range

    # Extended: 6 tiers (0-5)
    (5, "# @tear: 5",   5),
    (5, "# @tear: 4",   4),
    (5, "# @tear: 6",   None),  # out of range

    # Minimal: 2 tiers (0-1)
    (1, "# @tear: 1",   1),
    (1, "# @tear: 2",   None),  # out of range
], ids=[
    "default-max-valid",
    "default-max-over",
    "extended-6-max-valid",
    "extended-6-mid-valid",
    "extended-6-over",
    "minimal-2-max-valid",
    "minimal-2-over",
])
def test_configurable_tier_count(max_tear: int, content: str, expected: int | None):
    assert parse_tear_level(content, max_tear=max_tear) == expected


# --- Whitespace tolerance ---

@pytest.mark.parametrize("content, expected", [
    ("# @tear:0",       0),  # no space after colon
    ("# @tear:  1",     1),  # extra spaces
    ("# @tear:\t2",     2),  # tab
    ("#  @tear: 0",     0),  # extra space after comment marker
    ("  # @tear: 0",    0),  # leading whitespace on line
], ids=[
    "no-space",
    "extra-spaces",
    "tab",
    "extra-after-comment",
    "leading-whitespace",
])
def test_whitespace_tolerance(content: str, expected: int):
    assert parse_tear_level(content) == expected
```

### `test_import_extraction.py`

```python
"""Tests for import statement extraction across languages.

The import extractor finds all import statements in a file and returns
the raw import paths. It does NOT resolve them to files — that's the
resolver's job. It just finds the strings.
"""

import pytest
from tears.imports import extract_imports


# --- Python imports ---

@pytest.mark.parametrize("content, expected", [
    # Standard imports
    ("import os",                                         []),  # stdlib, no dot path
    ("import foo.bar",                                    ["foo.bar"]),
    ("import foo.bar.baz",                                ["foo.bar.baz"]),

    # From imports
    ("from foo.bar import baz",                           ["foo.bar"]),
    ("from foo.bar import baz, qux",                      ["foo.bar"]),
    ("from foo import bar",                               ["foo"]),

    # Relative imports
    ("from . import sibling",                             [".sibling"]),
    ("from .. import parent",                             ["..parent"]),
    ("from ..parent import thing",                        ["..parent"]),
    ("from ...deep import nested",                        ["...deep"]),

    # Multiple imports
    ("import foo.bar\nimport foo.baz",                    ["foo.bar", "foo.baz"]),
    ("from foo import bar\nfrom baz import qux",          ["foo", "baz"]),

    # Imports mixed with code
    ("# @tear: 1\nimport foo.bar\n\ndef main(): pass",   ["foo.bar"]),

    # No imports
    ("def main(): pass",                                  []),
    ("",                                                  []),
], ids=[
    "stdlib-ignored",
    "dotted-import",
    "deeply-nested-import",
    "from-import",
    "from-import-multiple-names",
    "from-import-single-level",
    "relative-current",
    "relative-parent",
    "relative-parent-named",
    "relative-grandparent",
    "multiple-imports",
    "multiple-from-imports",
    "imports-with-code",
    "no-imports",
    "empty-file",
])
def test_python_imports(content: str, expected: list[str]):
    assert extract_imports(content, lang="python") == expected


# --- JavaScript/TypeScript imports ---

@pytest.mark.parametrize("content, expected", [
    # ES module imports
    ("import { x } from './auth/tokens'",                 ["./auth/tokens"]),
    ("import x from '../core/db'",                        ["../core/db"]),
    ("import * as utils from './utils'",                  ["./utils"]),
    ("import './side-effect'",                             ["./side-effect"]),
    ('import { x } from "./auth/tokens"',                 ["./auth/tokens"]),

    # CommonJS require
    ("const x = require('./auth/tokens')",                ["./auth/tokens"]),
    ("const { x } = require('../core/db')",               ["../core/db"]),

    # Aliased paths
    ("import { x } from '@/auth/tokens'",                 ["@/auth/tokens"]),
    ("import { x } from '@auth/tokens'",                  ["@auth/tokens"]),

    # Node module imports (no relative path — should be skipped)
    ("import express from 'express'",                     []),
    ("import { useState } from 'react'",                  []),
    ("const fs = require('fs')",                          []),

    # Dynamic imports (not supported — skipped)
    ("const x = await import('./dynamic')",               []),

    # Mixed
    (
        "import { auth } from './auth/tokens'\n"
        "import { db } from '../core/db'\n"
        "import express from 'express'\n",
        ["./auth/tokens", "../core/db"]
    ),

    # TypeScript type imports
    ("import type { User } from './models'",              ["./models"]),
], ids=[
    "named-import",
    "default-import",
    "namespace-import",
    "side-effect-import",
    "double-quotes",
    "require",
    "destructured-require",
    "alias-at-slash",
    "alias-at-name",
    "node-module-default",
    "node-module-named",
    "node-module-require",
    "dynamic-import-skipped",
    "mixed-imports",
    "type-import",
])
def test_javascript_imports(content: str, expected: list[str]):
    assert extract_imports(content, lang="javascript") == expected


# --- Go imports ---

@pytest.mark.parametrize("content, expected", [
    # Single import
    ('import "myproject/auth/tokens"',                    ["myproject/auth/tokens"]),

    # Grouped imports
    (
        'import (\n'
        '    "fmt"\n'
        '    "myproject/auth/tokens"\n'
        '    "myproject/core/db"\n'
        ')',
        ["myproject/auth/tokens", "myproject/core/db"]
    ),

    # Standard library (no dot in path — skipped by resolver, but extractor returns them)
    ('import "fmt"',                                      []),
    ('import "net/http"',                                 []),

    # Aliased import
    ('import auth "myproject/auth/tokens"',               ["myproject/auth/tokens"]),
], ids=[
    "single",
    "grouped",
    "stdlib-fmt",
    "stdlib-net-http",
    "aliased",
])
def test_go_imports(content: str, expected: list[str]):
    assert extract_imports(content, lang="go") == expected
```

### `test_import_resolution.py`

```python
"""Tests for resolving import paths to actual files in the repo.

The resolver takes an import path (from the extractor) and the importing file's
location, and returns the absolute path to the target file — or None if it can't
be resolved (third-party, missing file, etc.).
"""

import pytest
from pathlib import Path
from tears.resolver import resolve_import


# --- Python resolution ---

class TestPythonResolution:
    """Python import resolution: dotted paths mapped to files via source_roots."""

    def test_simple_dotted_path(self, builder):
        root = (builder
            .add("src/auth/tokens.py", tear=0)
            .add("src/utils/helpers.py", tear=1, content="from auth.tokens import verify")
            .with_config(imports={"source_roots": ["src"]})
            .build())

        result = resolve_import(
            import_path="auth.tokens",
            from_file=root / "src/utils/helpers.py",
            root=root,
            source_roots=["src"],
            lang="python",
        )
        assert result == root / "src/auth/tokens.py"

    def test_relative_import_sibling(self, builder):
        root = (builder
            .add("src/utils/helpers.py", tear=1)
            .add("src/utils/constants.py", tear=1)
            .build())

        result = resolve_import(
            import_path=".constants",
            from_file=root / "src/utils/helpers.py",
            root=root,
            source_roots=["src"],
            lang="python",
        )
        assert result == root / "src/utils/constants.py"

    def test_relative_import_parent(self, builder):
        root = (builder
            .add("src/auth/tokens.py", tear=0)
            .add("src/utils/deep/helper.py", tear=1)
            .build())

        result = resolve_import(
            import_path="..auth.tokens",
            from_file=root / "src/utils/deep/helper.py",
            root=root,
            source_roots=["src"],
            lang="python",
        )
        assert result == root / "src/auth/tokens.py"

    def test_unresolvable_returns_none(self, builder):
        root = builder.add("src/utils/helpers.py", tear=1).build()

        result = resolve_import(
            import_path="nonexistent.module",
            from_file=root / "src/utils/helpers.py",
            root=root,
            source_roots=["src"],
            lang="python",
        )
        assert result is None

    def test_init_file_resolution(self, builder):
        root = (builder
            .add("src/auth/__init__.py", tear=0, content="from .tokens import verify")
            .add("src/auth/tokens.py", tear=0)
            .build())

        result = resolve_import(
            import_path="auth",
            from_file=root / "src/main.py",
            root=root,
            source_roots=["src"],
            lang="python",
        )
        assert result == root / "src/auth/__init__.py"


# --- JavaScript/TypeScript resolution ---

class TestJavaScriptResolution:
    """JS/TS import resolution: relative paths and aliases."""

    def test_relative_path(self, builder):
        root = (builder
            .add("src/auth/tokens.ts", tear=0)
            .add("src/utils/helpers.ts", tear=1)
            .build())

        result = resolve_import(
            import_path="../auth/tokens",
            from_file=root / "src/utils/helpers.ts",
            root=root,
            source_roots=["src"],
            lang="javascript",
        )
        assert result == root / "src/auth/tokens.ts"

    def test_alias_resolution(self, builder):
        root = (builder
            .add("src/auth/tokens.ts", tear=0)
            .add("src/utils/helpers.ts", tear=1)
            .with_config(imports={"aliases": {"@/": "src/"}})
            .build())

        result = resolve_import(
            import_path="@/auth/tokens",
            from_file=root / "src/utils/helpers.ts",
            root=root,
            source_roots=["src"],
            lang="javascript",
            aliases={"@/": "src/"},
        )
        assert result == root / "src/auth/tokens.ts"

    def test_index_file_resolution(self, builder):
        root = (builder
            .add("src/auth/index.ts", tear=0)
            .add("src/utils/helpers.ts", tear=1)
            .build())

        result = resolve_import(
            import_path="../auth",
            from_file=root / "src/utils/helpers.ts",
            root=root,
            source_roots=["src"],
            lang="javascript",
        )
        assert result == root / "src/auth/index.ts"

    @pytest.mark.parametrize("ext", [".ts", ".tsx", ".js", ".jsx"])
    def test_extension_inference(self, builder, ext: str):
        root = (builder
            .add(f"src/auth/tokens{ext}", tear=0)
            .add("src/utils/helpers.ts", tear=1)
            .build())

        result = resolve_import(
            import_path="../auth/tokens",
            from_file=root / "src/utils/helpers.ts",
            root=root,
            source_roots=["src"],
            lang="javascript",
        )
        assert result == root / f"src/auth/tokens{ext}"
```

### `test_tear_comparison.py`

```python
"""Tests for the core import rule: can file A import from file B?

The rule is simple: a file can import from files at its own tear level or better
(lower number). This is the heart of tears.
"""

import pytest
from tears.rules import can_import


# --- The full matrix (default 4 tiers: 0-3) ---

@pytest.mark.parametrize("importer_tear, target_tear, allowed", [
    # Tear 0 can only import from tear 0
    (0, 0, True),
    (0, 1, False),
    (0, 2, False),
    (0, 3, False),

    # Tear 1 can import from 0, 1
    (1, 0, True),
    (1, 1, True),
    (1, 2, False),
    (1, 3, False),

    # Tear 2 can import from 0, 1, 2
    (2, 0, True),
    (2, 1, True),
    (2, 2, True),
    (2, 3, False),

    # Tear 3 can import from anything
    (3, 0, True),
    (3, 1, True),
    (3, 2, True),
    (3, 3, True),
], ids=[
    "tear0-from-tear0-YES",
    "tear0-from-tear1-NO",
    "tear0-from-tear2-NO",
    "tear0-from-tear3-NO",

    "tear1-from-tear0-YES",
    "tear1-from-tear1-YES",
    "tear1-from-tear2-NO",
    "tear1-from-tear3-NO",

    "tear2-from-tear0-YES",
    "tear2-from-tear1-YES",
    "tear2-from-tear2-YES",
    "tear2-from-tear3-NO",

    "tear3-from-tear0-YES",
    "tear3-from-tear1-YES",
    "tear3-from-tear2-YES",
    "tear3-from-tear3-YES",
])
def test_import_rule_default_tiers(importer_tear: int, target_tear: int, allowed: bool):
    assert can_import(importer_tear, target_tear) == allowed


# --- The rule in plain English ---

def test_rule_is_importer_less_than_or_equal_to_target():
    """The rule is: importer_tear >= target_tear (lower number = more trusted)."""
    # Trusted code (tear 0) can't depend on untrusted code (tear 3)
    assert can_import(0, 3) is False
    # Untrusted code (tear 3) CAN depend on trusted code (tear 0)
    assert can_import(3, 0) is True


# --- Custom tier counts ---

@pytest.mark.parametrize("max_tear, importer, target, allowed", [
    # 6 tiers (0-5): tear 4 importing from tear 5
    (5, 4, 5, False),
    (5, 5, 4, True),
    (5, 5, 5, True),
    (5, 0, 5, False),
    (5, 5, 0, True),

    # 2 tiers (0-1): binary trusted/untrusted
    (1, 0, 0, True),
    (1, 0, 1, False),
    (1, 1, 0, True),
    (1, 1, 1, True),
], ids=[
    "6tier-t4-from-t5-NO",
    "6tier-t5-from-t4-YES",
    "6tier-t5-from-t5-YES",
    "6tier-t0-from-t5-NO",
    "6tier-t5-from-t0-YES",
    "2tier-t0-from-t0-YES",
    "2tier-t0-from-t1-NO",
    "2tier-t1-from-t0-YES",
    "2tier-t1-from-t1-YES",
])
def test_import_rule_custom_tier_counts(max_tear: int, importer: int, target: int, allowed: bool):
    assert can_import(importer, target, max_tear=max_tear) == allowed


# --- Custom import rules (overriding the default matrix) ---

RELAXED = {0: [0], 1: [0, 1, 2], 2: [0, 1, 2], 3: [0, 1, 2, 3]}
ISLANDS = {0: [0, 1], 1: [0, 1], 2: [2, 3], 3: [2, 3]}
STRICT  = {0: [0], 1: [1], 2: [2], 3: [3]}
OPEN    = {0: [0, 1, 2, 3], 1: [0, 1, 2, 3], 2: [0, 1, 2, 3], 3: [0, 1, 2, 3]}

@pytest.mark.parametrize("importer, target, rules, allowed", [
    # Relaxed: tier 1 can now reach tier 2
    (1, 2, RELAXED, True),
    (0, 2, RELAXED, False),
    (0, 1, RELAXED, False),

    # Islands: 0-1 interop, 2-3 interop, no crossing
    (0, 1, ISLANDS, True),
    (1, 0, ISLANDS, True),
    (2, 3, ISLANDS, True),
    (3, 2, ISLANDS, True),
    (0, 2, ISLANDS, False),
    (2, 0, ISLANDS, False),
    (1, 3, ISLANDS, False),
    (3, 1, ISLANDS, False),

    # Strict: each tier only imports from itself
    (0, 0, STRICT, True),
    (0, 1, STRICT, False),
    (1, 0, STRICT, False),
    (1, 1, STRICT, True),
    (3, 0, STRICT, False),

    # Open: everything can import everything
    (0, 3, OPEN, True),
    (3, 0, OPEN, True),
    (0, 0, OPEN, True),
], ids=[
    "relaxed-t1-from-t2-YES",
    "relaxed-t0-from-t2-NO",
    "relaxed-t0-from-t1-NO",

    "islands-t0-from-t1-YES",
    "islands-t1-from-t0-YES",
    "islands-t2-from-t3-YES",
    "islands-t3-from-t2-YES",
    "islands-t0-from-t2-NO",
    "islands-t2-from-t0-NO",
    "islands-t1-from-t3-NO",
    "islands-t3-from-t1-NO",

    "strict-t0-from-t0-YES",
    "strict-t0-from-t1-NO",
    "strict-t1-from-t0-NO",
    "strict-t1-from-t1-YES",
    "strict-t3-from-t0-NO",

    "open-t0-from-t3-YES",
    "open-t3-from-t0-YES",
    "open-t0-from-t0-YES",
])
def test_custom_import_rules(importer: int, target: int, rules: dict, allowed: bool):
    assert can_import(importer, target, import_rules=rules) == allowed


def test_none_rules_falls_back_to_default():
    """When import_rules=None, the default 'equal or better' rule applies."""
    assert can_import(1, 2, import_rules=None) is False
    assert can_import(2, 1, import_rules=None) is True


def test_rules_must_include_self():
    """A tier must always be allowed to import from itself."""
    bad_rules = {0: [1], 1: [0, 1], 2: [0, 1, 2], 3: [0, 1, 2, 3]}
    with pytest.raises(ValueError, match="tier 0 must be able to import from itself"):
        can_import(0, 0, import_rules=bad_rules)
```

### `test_directory_rules.py`

```python
"""Tests for directory requirement enforcement.

Directories can declare a maximum tear level (minimum trust). A file
living in that directory must have a tear level at or better than the
directory's requirement.
"""

import pytest
from tears.rules import check_directory_requirement


# --- Basic matching ---

@pytest.mark.parametrize("file_path, file_tear, requirements, passes", [
    # File meets requirement exactly
    ("src/auth/tokens.py", 0, {"src/auth": 0}, True),

    # File exceeds requirement (better than needed)
    ("src/auth/tokens.py", 0, {"src/auth": 1}, True),

    # File fails requirement
    ("src/auth/tokens.py", 2, {"src/auth": 0}, False),
    ("src/auth/tokens.py", 3, {"src/auth": 0}, False),

    # File in unrestricted directory (no requirement)
    ("scripts/deploy.sh", 3, {"src/auth": 0}, True),

    # Empty requirements (everything passes)
    ("src/auth/tokens.py", 3, {}, True),
], ids=[
    "exact-match",
    "exceeds-requirement",
    "fails-by-2",
    "fails-unreviewed-in-critical",
    "unrestricted-directory",
    "no-requirements",
])
def test_directory_requirement_check(
    file_path: str,
    file_tear: int,
    requirements: dict[str, int],
    passes: bool,
):
    assert check_directory_requirement(file_path, file_tear, requirements) == passes


# --- Most-specific prefix wins ---

@pytest.mark.parametrize("file_path, file_tear, passes", [
    # src/auth requires 0, src requires 1
    # src/auth/tokens.py should use src/auth (tear 0)
    ("src/auth/tokens.py", 0, True),
    ("src/auth/tokens.py", 1, False),   # fails: src/auth requires 0

    # src/utils/helpers.py should use src (tear 1)
    ("src/utils/helpers.py", 1, True),
    ("src/utils/helpers.py", 2, False),  # fails: src requires 1

    # Deeply nested: src/auth/internal/secret.py uses src/auth (0)
    ("src/auth/internal/secret.py", 0, True),
    ("src/auth/internal/secret.py", 1, False),
])
def test_most_specific_prefix_wins(file_path: str, file_tear: int, passes: bool):
    requirements = {
        "src": 1,
        "src/auth": 0,
    }
    assert check_directory_requirement(file_path, file_tear, requirements) == passes


# --- Edge cases ---

def test_root_level_file_with_no_matching_directory():
    """A file at the repo root with no matching directory requirement passes."""
    assert check_directory_requirement(
        "main.py", 3, {"src": 1, "src/auth": 0}
    ) is True

def test_trailing_slashes_normalized():
    """Directory paths should work with or without trailing slashes."""
    assert check_directory_requirement(
        "src/auth/tokens.py", 0, {"src/auth/": 0}
    ) is True
```

### `test_config.py`

```python
"""Tests for .tears.yml configuration parsing and validation.

Configuration defines directory requirements, exclusions, included extensions,
import settings, and the tier count. All fields are optional with sensible defaults.
"""

import pytest
from tears.config import TearsConfig, load_config


# --- Defaults ---

def test_default_config():
    config = TearsConfig()
    assert config.max_tear == 3
    assert config.directory_requirements == {}
    assert config.import_rules is None  # None = use default "equal or better" rule
    assert config.exclude == []
    assert config.strict_promotion is False
    assert config.test_policy == "exclude"
    assert config.missing_header == "warn"


# --- Custom tier count ---

@pytest.mark.parametrize("max_tear", [1, 3, 5, 9])
def test_custom_max_tear(max_tear: int):
    config = TearsConfig(max_tear=max_tear)
    assert config.max_tear == max_tear


def test_max_tear_must_be_at_least_1():
    with pytest.raises(ValueError, match="max_tear must be at least 1"):
        TearsConfig(max_tear=0)


def test_directory_requirements_validated_against_max_tear():
    """Directory requirements can't reference tiers beyond max_tear."""
    with pytest.raises(ValueError, match="tear level 5 exceeds max_tear 3"):
        TearsConfig(
            max_tear=3,
            directory_requirements={"src/auth": 5}
        )


# --- Import rules config ---

def test_import_rules_validated_against_max_tear():
    """Import rules can't reference tiers beyond max_tear."""
    with pytest.raises(ValueError, match="tear level 4 exceeds max_tear 3"):
        TearsConfig(
            max_tear=3,
            import_rules={0: [0], 1: [0, 1], 2: [0, 1, 2], 3: [0, 1, 2, 3, 4]}
        )


def test_import_rules_must_include_self():
    """Every tier must be allowed to import from itself."""
    with pytest.raises(ValueError, match="tier 0 must be able to import from itself"):
        TearsConfig(
            import_rules={0: [1], 1: [0, 1], 2: [0, 1, 2], 3: [0, 1, 2, 3]}
        )


def test_import_rules_partial_override_fills_defaults():
    """If only some tiers are specified, unspecified tiers use the default rule."""
    config = TearsConfig(import_rules={1: [0, 1, 2]})  # only override tier 1
    resolved = config.resolved_import_rules()
    assert resolved[0] == [0]          # default
    assert resolved[1] == [0, 1, 2]    # overridden
    assert resolved[2] == [0, 1, 2]    # default
    assert resolved[3] == [0, 1, 2, 3] # default


# --- YAML loading ---

def test_load_from_yaml(tmp_path):
    config_content = """
max_tear: 5
directory_requirements:
  src/auth: 0
  src/db: 0
  src/api: 2
import_rules:
  1: [0, 1, 2]
exclude:
  - "*.md"
  - "migrations/**"
strict_promotion: true
missing_header: error
"""
    (tmp_path / ".tears.yml").write_text(config_content)
    config = load_config(tmp_path)

    assert config.max_tear == 5
    assert config.directory_requirements == {"src/auth": 0, "src/db": 0, "src/api": 2}
    assert config.import_rules == {1: [0, 1, 2]}
    assert "*.md" in config.exclude
    assert config.strict_promotion is True
    assert config.missing_header == "error"


def test_load_missing_config_returns_defaults(tmp_path):
    """If no .tears.yml exists, return default config."""
    config = load_config(tmp_path)
    assert config == TearsConfig()


# --- File exclusion matching ---

@pytest.mark.parametrize("path, exclude, is_excluded", [
    ("src/auth/tokens.py",    ["*.md"],                  False),
    ("README.md",             ["*.md"],                  True),
    ("src/auth/tokens.pb.go", ["**/*.pb.go"],            True),
    ("migrations/001.sql",    ["migrations/**"],         True),
    ("src/migrations/x.py",   ["migrations/**"],         False),  # not top-level migrations
    ("package.json",          ["package.json"],          True),
    ("src/package.json",      ["package.json"],          False),  # only root
], ids=[
    "py-not-excluded-by-md",
    "md-excluded",
    "proto-go-excluded",
    "migration-excluded",
    "nested-migration-not-excluded",
    "root-package-json",
    "nested-package-json-not-excluded",
])
def test_file_exclusion(path: str, exclude: list[str], is_excluded: bool):
    config = TearsConfig(exclude=exclude)
    assert config.is_excluded(path) == is_excluded
```

### `test_hook.py`

```python
"""Tests for the Claude Code post-edit hook.

The hook is a shell script, but we test the underlying logic in Python:
given a file's content and extension, produce the modified content with
@tear set to the maximum (least trusted) value.
"""

import pytest
from tears.hook import apply_hook


# --- Replaces existing header ---

@pytest.mark.parametrize("before, after", [
    # Python: replaces any tier to max
    ("# @tear: 0\nimport os",           "# @tear: 3\nimport os"),
    ("# @tear: 1\nimport os",           "# @tear: 3\nimport os"),
    ("# @tear: 2\nimport os",           "# @tear: 3\nimport os"),
    ("# @tear: 3\nimport os",           "# @tear: 3\nimport os"),  # already max, no-op

    # JavaScript
    ("// @tear: 0\nconst x = 1;",       "// @tear: 3\nconst x = 1;"),

    # SQL
    ("-- @tear: 1\nSELECT 1;",          "-- @tear: 3\nSELECT 1;"),

    # HTML
    ("<!-- @tear: 0 -->\n<html>",        "<!-- @tear: 3 -->\n<html>"),

    # CSS
    ("/* @tear: 1 */\nbody {}",          "/* @tear: 3 */\nbody {}"),
], ids=[
    "python-0-to-3",
    "python-1-to-3",
    "python-2-to-3",
    "python-already-3",
    "javascript",
    "sql",
    "html",
    "css",
])
def test_replaces_existing_header(before: str, after: str):
    assert apply_hook(before) == after


# --- Inserts header when missing ---

@pytest.mark.parametrize("ext, before, expected_first_line", [
    (".py",   "import os\ndef main(): pass",    "# @tear: 3"),
    (".js",   "const x = 1;",                   "// @tear: 3"),
    (".ts",   "const x: number = 1;",           "// @tear: 3"),
    (".go",   'package main\nimport "fmt"',      "// @tear: 3"),
    (".rb",   "puts 'hello'",                    "# @tear: 3"),
    (".sql",  "SELECT 1;",                       "-- @tear: 3"),
], ids=["python", "javascript", "typescript", "go", "ruby", "sql"])
def test_inserts_header_when_missing(ext: str, before: str, expected_first_line: str):
    result = apply_hook(before, ext=ext)
    assert result.split("\n")[0] == expected_first_line
    # Original content preserved after header
    assert before in result


# --- Preserves shebang ---

def test_inserts_after_shebang():
    before = "#!/usr/bin/env python3\nimport os"
    result = apply_hook(before, ext=".py")
    lines = result.split("\n")
    assert lines[0] == "#!/usr/bin/env python3"
    assert lines[1] == "# @tear: 3"
    assert lines[2] == "import os"


# --- Custom max tier ---

def test_hook_uses_custom_max_tear():
    before = "# @tear: 0\nimport os"
    result = apply_hook(before, max_tear=5)
    assert result == "# @tear: 5\nimport os"


# --- Idempotency ---

def test_hook_is_idempotent():
    """Running the hook twice produces the same result as running it once."""
    original = "# @tear: 0\nimport os"
    once = apply_hook(original)
    twice = apply_hook(once)
    assert once == twice
```

---

## Integration Tests

### `test_check.py`

```python
"""Integration tests for `tears check`.

Each test builds a realistic mini-repo and runs the full check pipeline,
verifying that the right violations are found (or that the repo is clean).
"""

import pytest
from tears.cli import check
from tears.config import TearsConfig


class TestCleanRepo:
    """Repos with no violations should pass cleanly."""

    def test_simple_clean_repo(self, builder):
        root = (builder
            .add("src/auth/tokens.py",  tear=0, content="import hashlib")
            .add("src/auth/session.py", tear=0, content="from auth.tokens import verify")
            .add("src/api/routes.py",   tear=1, content="from auth.tokens import verify")
            .add("scripts/deploy.sh",   tear=3, content="echo hello")
            .with_config(
                directory_requirements={"src/auth": 0, "src/api": 1},
                imports={"source_roots": ["src"]},
            )
            .build())

        result = check(root, files=["src/auth/tokens.py", "src/auth/session.py", "src/api/routes.py"])
        assert result.failures == []
        assert result.exit_code == 0

    def test_empty_repo(self, builder):
        root = builder.build()
        result = check(root, files=[])
        assert result.exit_code == 0


class TestImportViolations:
    """Repos where files import from insufficiently-trusted files."""

    def test_tear0_importing_tear3(self, builder):
        """The classic violation: secure code depending on unreviewed AI output."""
        root = (builder
            .add("src/auth/tokens.py", tear=0, content="from utils.helpers import sanitize")
            .add("src/utils/helpers.py", tear=3)
            .with_config(imports={"source_roots": ["src"]})
            .build())

        result = check(root, files=["src/auth/tokens.py"])
        assert len(result.failures) == 1
        assert "tear 0 cannot import from tear 3" in result.failures[0].message

    def test_tear1_importing_tear2(self, builder):
        root = (builder
            .add("src/api/routes.py", tear=1, content="from utils.format import pretty")
            .add("src/utils/format.py", tear=2)
            .with_config(imports={"source_roots": ["src"]})
            .build())

        result = check(root, files=["src/api/routes.py"])
        assert len(result.failures) == 1

    def test_tear3_importing_tear0_is_fine(self, builder):
        """Untrusted code importing trusted code is always allowed."""
        root = (builder
            .add("scripts/check_auth.py", tear=3, content="from auth.tokens import verify")
            .add("src/auth/tokens.py", tear=0)
            .with_config(imports={"source_roots": ["src"]})
            .build())

        result = check(root, files=["scripts/check_auth.py"])
        assert result.failures == []

    def test_multiple_violations_in_one_file(self, builder):
        root = (builder
            .add("src/auth/tokens.py", tear=0,
                 content="from utils.a import x\nfrom utils.b import y")
            .add("src/utils/a.py", tear=2)
            .add("src/utils/b.py", tear=3)
            .with_config(imports={"source_roots": ["src"]})
            .build())

        result = check(root, files=["src/auth/tokens.py"])
        assert len(result.failures) == 2

    def test_unresolvable_import_is_skipped(self, builder):
        """Imports that can't be resolved to repo files are silently skipped."""
        root = (builder
            .add("src/api/routes.py", tear=1,
                 content="from nonexistent.module import thing")
            .with_config(imports={"source_roots": ["src"]})
            .build())

        result = check(root, files=["src/api/routes.py"])
        assert result.failures == []


class TestDirectoryViolations:
    """Files that don't meet their directory's minimum tear requirement."""

    def test_tear3_in_tear0_directory(self, builder):
        root = (builder
            .add("src/auth/tokens.py", tear=3)
            .with_config(directory_requirements={"src/auth": 0})
            .build())

        result = check(root, files=["src/auth/tokens.py"])
        assert len(result.failures) == 1
        assert "directory requires tear 0" in result.failures[0].message

    def test_tear1_in_tear0_directory(self, builder):
        """Even one level off is a violation."""
        root = (builder
            .add("src/auth/tokens.py", tear=1)
            .with_config(directory_requirements={"src/auth": 0})
            .build())

        result = check(root, files=["src/auth/tokens.py"])
        assert len(result.failures) == 1


class TestMissingHeaders:
    """Files without @tear headers."""

    def test_missing_header_warn_mode(self, builder):
        root = (builder
            .add("src/utils/helpers.py", content="def helper(): pass")  # no tear
            .with_config(missing_header="warn")
            .build())

        result = check(root, files=["src/utils/helpers.py"])
        assert len(result.warnings) == 1
        assert result.exit_code == 0  # warnings don't fail

    def test_missing_header_error_mode(self, builder):
        root = (builder
            .add("src/utils/helpers.py", content="def helper(): pass")  # no tear
            .with_config(missing_header="error")
            .build())

        result = check(root, files=["src/utils/helpers.py"])
        assert len(result.failures) == 1
        assert result.exit_code == 1


class TestCustomTierCount:
    """Repos configured with non-default tier counts."""

    def test_six_tier_system(self, builder):
        """A team using 6 tiers (0-5) for finer granularity."""
        root = (builder
            .add("src/auth/tokens.py", tear=0, content="from utils.helpers import x")
            .add("src/utils/helpers.py", tear=4)  # would be valid in 4-tier, invalid in 6-tier for tear 0
            .with_config(
                max_tear=5,
                imports={"source_roots": ["src"]},
            )
            .build())

        result = check(root, files=["src/auth/tokens.py"])
        assert len(result.failures) == 1  # tear 0 can't import from tear 4

    def test_binary_tier_system(self, builder):
        """A minimal team using just 2 tiers: 0 (trusted) and 1 (untrusted)."""
        root = (builder
            .add("src/auth/tokens.py", tear=0, content="from utils.helpers import x")
            .add("src/utils/helpers.py", tear=1)
            .with_config(
                max_tear=1,
                imports={"source_roots": ["src"]},
            )
            .build())

        result = check(root, files=["src/auth/tokens.py"])
        assert len(result.failures) == 1  # tear 0 can't import from tear 1


class TestExcludedFiles:
    """Excluded files should be completely skipped."""

    def test_excluded_file_not_checked(self, builder):
        root = (builder
            .add("src/auth/tokens.pb.go", content="// generated code, no header")
            .with_config(
                exclude=["**/*.pb.go"],
                directory_requirements={"src/auth": 0},
            )
            .build())

        result = check(root, files=["src/auth/tokens.pb.go"])
        assert result.failures == []
        assert result.warnings == []

    def test_excluded_import_target_not_enforced(self, builder):
        """If an import target is excluded, the import check is skipped."""
        root = (builder
            .add("src/api/routes.py", tear=0, content="from auth.generated import schema")
            .add("src/auth/generated.py", content="# generated, no header")
            .with_config(
                exclude=["**/generated.py"],
                imports={"source_roots": ["src"]},
            )
            .build())

        result = check(root, files=["src/api/routes.py"])
        assert result.failures == []


class TestStrictPromotion:
    """When strict_promotion is true, tier improvements must be in
    commits that don't change anything else in the file."""

    # Note: this requires diff analysis, tested with git fixtures
    pass  # TODO: implement with git-based fixtures
```

### `test_init.py`

```python
"""Integration tests for `tears init`."""

import pytest
from pathlib import Path
from tears.cli import init


def test_init_adds_headers_to_all_files(builder):
    root = (builder
        .add("src/auth/tokens.py", content="import hashlib")
        .add("src/api/routes.py", content="from flask import Flask")
        .add("scripts/deploy.sh", content="echo hello")
        .build())

    init(root, default_tear=1)

    for path in ["src/auth/tokens.py", "src/api/routes.py"]:
        content = (root / path).read_text()
        assert "@tear: 1" in content.split("\n")[0]


def test_init_creates_config_file(builder):
    root = builder.build()
    init(root)
    assert (root / ".tears.yml").exists()


def test_init_creates_claude_hook(builder):
    root = builder.build()
    init(root)
    hook_path = root / ".claude" / "hooks" / "post-edit.sh"
    assert hook_path.exists()
    assert hook_path.stat().st_mode & 0o111  # executable


def test_init_does_not_overwrite_existing_headers(builder):
    root = (builder
        .add("src/auth/tokens.py", tear=0, content="import hashlib")
        .build())

    init(root, default_tear=1)

    content = (root / "src/auth/tokens.py").read_text()
    assert "@tear: 0" in content  # preserved, not overwritten to 1


def test_init_with_custom_default_tear(builder):
    root = (builder
        .add("src/utils/helpers.py", content="def helper(): pass")
        .build())

    init(root, default_tear=2)

    content = (root / "src/utils/helpers.py").read_text()
    assert "@tear: 2" in content.split("\n")[0]


def test_init_skips_binary_files(builder):
    root = builder.build()
    # Create a binary file
    (root / "assets").mkdir()
    (root / "assets" / "logo.png").write_bytes(b'\x89PNG\r\n')

    init(root, default_tear=1)

    content = (root / "assets" / "logo.png").read_bytes()
    assert b"@tear" not in content
```

---

## Test Utilities

### Assertion Helpers

```python
"""Custom assertions for readable test output."""

from tears.cli import CheckResult


def assert_passes(result: CheckResult) -> None:
    """Assert that a check result has no failures."""
    assert result.exit_code == 0, (
        f"Expected clean check but got {len(result.failures)} failure(s):\n"
        + "\n".join(f"  - {f}" for f in result.failures)
    )


def assert_fails_with(result: CheckResult, *fragments: str) -> None:
    """Assert that a check result failed and messages contain all fragments."""
    assert result.exit_code == 1, "Expected check to fail but it passed"
    messages = " ".join(f.message for f in result.failures)
    for fragment in fragments:
        assert fragment in messages, (
            f"Expected '{fragment}' in failure messages but got:\n"
            + "\n".join(f"  - {f.message}" for f in result.failures)
        )
```
