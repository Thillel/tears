# @tear: 3
"""Tests for `.tears.yml` parsing and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tears.config import ConfigError, TearsConfig, load_config


def test_defaults() -> None:
    cfg = TearsConfig()
    assert cfg.max_tear == 3
    assert cfg.directory_requirements == {}
    assert cfg.exclude == []
    assert cfg.source_roots == ["."]
    assert cfg.import_rules is None
    assert cfg.missing_header == "warn"


def test_load_missing_config_returns_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path) == TearsConfig()


def test_load_yaml(tmp_path: Path) -> None:
    (tmp_path / ".tears.yml").write_text(
        "max_tear: 5\n"
        "directory_requirements:\n"
        "  src/auth: 0\n"
        "  src/api: 2\n"
        "exclude:\n"
        "  - '**/*.generated.py'\n"
        "imports:\n"
        "  source_roots: ['src']\n"
        "import_rules:\n"
        "  1: [0, 1, 2]\n"
        "missing_header: error\n"
    )
    cfg = load_config(tmp_path)
    assert cfg.max_tear == 5
    assert cfg.directory_requirements == {"src/auth": 0, "src/api": 2}
    assert cfg.exclude == ["**/*.generated.py"]
    assert cfg.source_roots == ["src"]
    assert cfg.import_rules == {1: [0, 1, 2]}
    assert cfg.missing_header == "error"


def test_trailing_slashes_in_directory_keys_normalized(tmp_path: Path) -> None:
    (tmp_path / ".tears.yml").write_text("directory_requirements:\n  src/auth/: 0\n")
    cfg = load_config(tmp_path)
    assert cfg.directory_requirements == {"src/auth": 0}


def test_max_tear_must_be_at_least_1() -> None:
    with pytest.raises(ConfigError, match="max_tear must be at least 1"):
        TearsConfig(max_tear=0)


def test_directory_requirement_exceeds_max_tear() -> None:
    with pytest.raises(ConfigError, match="exceeds max_tear 3"):
        TearsConfig(max_tear=3, directory_requirements={"src/auth": 5})


def test_import_rules_exceed_max_tear() -> None:
    with pytest.raises(ConfigError, match="exceeds max_tear 3"):
        TearsConfig(
            max_tear=3,
            import_rules={0: [0], 1: [0, 1], 2: [0, 1, 2], 3: [0, 1, 2, 3, 4]},
        )


def test_import_rules_must_include_self() -> None:
    with pytest.raises(ConfigError, match="tier 0 must be able to import from itself"):
        TearsConfig(import_rules={0: [1], 1: [0, 1], 2: [0, 1, 2], 3: [0, 1, 2, 3]})


def test_resolved_import_rules_default() -> None:
    cfg = TearsConfig()
    resolved = cfg.resolved_import_rules()
    assert resolved[0] == frozenset({0})
    assert resolved[1] == frozenset({0, 1})
    assert resolved[2] == frozenset({0, 1, 2})
    assert resolved[3] == frozenset({0, 1, 2, 3})


def test_resolved_import_rules_partial_override() -> None:
    cfg = TearsConfig(import_rules={1: [0, 1, 2]})
    resolved = cfg.resolved_import_rules()
    assert resolved[0] == frozenset({0})
    assert resolved[1] == frozenset({0, 1, 2})
    assert resolved[2] == frozenset({0, 1, 2})
    assert resolved[3] == frozenset({0, 1, 2, 3})


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    (tmp_path / ".tears.yml").write_text("max_tear: : :\n  nope\n")
    with pytest.raises(ConfigError, match="malformed YAML"):
        load_config(tmp_path)


def test_top_level_not_mapping(tmp_path: Path) -> None:
    (tmp_path / ".tears.yml").write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="top level must be a mapping"):
        load_config(tmp_path)


def test_bad_missing_header_value() -> None:
    with pytest.raises(ConfigError, match="missing_header must be"):
        TearsConfig(missing_header="explode")
