# @tear: 3
"""`.tears.yml` parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

CONFIG_FILENAME = ".tears.yml"
MISSING_HEADER_VALUES = ("warn", "error")


class ConfigError(ValueError):
    """Raised when `.tears.yml` is malformed or fails schema validation."""


@dataclass(frozen=True)
class TearsConfig:
    """Validated, resolved tears configuration.

    `directory_requirements` keys are normalized (trailing slashes stripped).
    `import_rules` is the raw, possibly-partial mapping from the YAML; use
    `resolved_import_rules()` to get the full per-tier allow-set with defaults filled in.
    """

    max_tear: int = 3
    directory_requirements: dict[str, int] = field(default_factory=lambda: {})
    exclude: list[str] = field(default_factory=lambda: [])
    source_roots: list[str] = field(default_factory=lambda: ["."])
    import_rules: dict[int, list[int]] | None = None
    missing_header: str = "warn"

    def __post_init__(self) -> None:
        if self.max_tear < 1:
            raise ConfigError(f"max_tear must be at least 1, got {self.max_tear}")
        if self.missing_header not in MISSING_HEADER_VALUES:
            raise ConfigError(
                f"missing_header must be one of {MISSING_HEADER_VALUES}, "
                f"got {self.missing_header!r}"
            )
        for path, tier in self.directory_requirements.items():
            if not 0 <= tier <= self.max_tear:
                raise ConfigError(
                    f"directory_requirements[{path!r}] = {tier}: "
                    f"tear level {tier} exceeds max_tear {self.max_tear}"
                )
        if self.import_rules is not None:
            for importer, allowed in self.import_rules.items():
                if not 0 <= importer <= self.max_tear:
                    raise ConfigError(
                        f"import_rules key {importer}: "
                        f"tear level {importer} exceeds max_tear {self.max_tear}"
                    )
                for target in allowed:
                    if not 0 <= target <= self.max_tear:
                        raise ConfigError(
                            f"import_rules[{importer}] contains {target}: "
                            f"tear level {target} exceeds max_tear {self.max_tear}"
                        )
                if importer not in allowed:
                    raise ConfigError(f"tier {importer} must be able to import from itself")

    def resolved_import_rules(self) -> dict[int, frozenset[int]]:
        """Full matrix with defaults filled in for any unspecified tier."""
        resolved: dict[int, frozenset[int]] = {}
        for tier in range(self.max_tear + 1):
            if self.import_rules is not None and tier in self.import_rules:
                resolved[tier] = frozenset(self.import_rules[tier])
            else:
                resolved[tier] = frozenset(range(tier + 1))
        return resolved


def load_config(repo_root: Path) -> TearsConfig:
    """Load `.tears.yml` from `repo_root`. Missing file => defaults.

    Malformed YAML or a schema failure raises `ConfigError` with a clear message
    naming the file and the problem.
    """
    config_path = repo_root / CONFIG_FILENAME
    if not config_path.exists():
        return TearsConfig()

    try:
        raw: Any = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"{config_path}: malformed YAML: {exc}") from exc

    if raw is None:
        return TearsConfig()
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path}: top level must be a mapping, got {type(raw).__name__}")

    return _from_mapping(cast(dict[str, Any], raw), source=str(config_path))


def _from_mapping(raw: dict[str, Any], *, source: str) -> TearsConfig:
    kwargs: dict[str, Any] = {}

    if "max_tear" in raw:
        kwargs["max_tear"] = _require_int(raw["max_tear"], "max_tear", source)

    if "directory_requirements" in raw:
        dr_raw = _require_mapping(raw["directory_requirements"], "directory_requirements", source)
        normalized: dict[str, int] = {}
        for key, value in dr_raw.items():
            if not isinstance(key, str) or not isinstance(value, int) or isinstance(value, bool):
                raise ConfigError(
                    f"{source}: directory_requirements entries must be str -> int, "
                    f"got {key!r} -> {value!r}"
                )
            normalized[key.rstrip("/")] = value
        kwargs["directory_requirements"] = normalized

    if "exclude" in raw:
        exclude_raw = _require_list(raw["exclude"], "exclude", source)
        exclude: list[str] = []
        for item in exclude_raw:
            if not isinstance(item, str):
                raise ConfigError(f"{source}: exclude entries must be strings, got {item!r}")
            exclude.append(item)
        kwargs["exclude"] = exclude

    if "imports" in raw:
        imports_raw = _require_mapping(raw["imports"], "imports", source)
        if "source_roots" in imports_raw:
            sr_raw = imports_raw["source_roots"]
            if not isinstance(sr_raw, list):
                raise ConfigError(
                    f"{source}: imports.source_roots must be a list, got {type(sr_raw).__name__}"
                )
            source_roots: list[str] = []
            for item in cast(list[Any], sr_raw):
                if not isinstance(item, str):
                    raise ConfigError(
                        f"{source}: imports.source_roots entries must be strings, got {item!r}"
                    )
                source_roots.append(item)
            kwargs["source_roots"] = source_roots

    if "import_rules" in raw and raw["import_rules"] is not None:
        ir_raw = _require_mapping(raw["import_rules"], "import_rules", source)
        rules: dict[int, list[int]] = {}
        for key, value in ir_raw.items():
            if not isinstance(key, int) or isinstance(key, bool):
                raise ConfigError(f"{source}: import_rules keys must be ints, got {key!r}")
            if not isinstance(value, list):
                raise ConfigError(
                    f"{source}: import_rules[{key}] must be a list, got {type(value).__name__}"
                )
            allowed: list[int] = []
            for entry in cast(list[Any], value):
                if not isinstance(entry, int) or isinstance(entry, bool):
                    raise ConfigError(
                        f"{source}: import_rules[{key}] entries must be ints, got {entry!r}"
                    )
                allowed.append(entry)
            rules[key] = allowed
        kwargs["import_rules"] = rules

    if "missing_header" in raw:
        kwargs["missing_header"] = _require_str(raw["missing_header"], "missing_header", source)

    try:
        return TearsConfig(**kwargs)
    except ConfigError as exc:
        raise ConfigError(f"{source}: {exc}") from None


def _require_int(value: Any, key: str, source: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{source}: {key} must be int, got {type(value).__name__}")
    return value


def _require_str(value: Any, key: str, source: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{source}: {key} must be str, got {type(value).__name__}")
    return value


def _require_mapping(value: Any, key: str, source: str) -> dict[Any, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: {key} must be a mapping, got {type(value).__name__}")
    return cast(dict[Any, Any], value)


def _require_list(value: Any, key: str, source: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(f"{source}: {key} must be a list, got {type(value).__name__}")
    return cast(list[Any], value)
