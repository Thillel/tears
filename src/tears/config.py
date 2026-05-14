# @tear: 3
"""`.tears.toml` parsing and validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

CONFIG_FILENAME = ".tears.toml"
MISSING_HEADER_VALUES = ("warn", "error")


def _path_segments(path: str) -> tuple[str, ...]:
    return tuple(p for p in path.strip("/").split("/") if p)


class ConfigError(ValueError):
    """Raised when `.tears.toml` is malformed or fails schema validation."""


@dataclass(frozen=True)
class TearsConfig:
    """Validated, resolved tears configuration.

    `directory_requirements` keys are normalized (trailing slashes stripped).
    `import_rules` is the raw, possibly-partial mapping; use
    `resolved_import_rules()` to get the full per-tier allow-set with defaults filled in.
    """

    max_tear: int = 3
    directory_requirements: dict[str, int] = field(default_factory=lambda: {})
    exclude: list[str] = field(default_factory=lambda: [])
    source_roots: list[str] = field(default_factory=lambda: ["."])
    import_rules: dict[int, int] | None = None
    missing_header: str = "warn"
    default_tear: int | None = None
    default_tears: dict[str, int] = field(default_factory=lambda: {})

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
            for importer, max_allowed in self.import_rules.items():
                if not 0 <= importer <= self.max_tear:
                    raise ConfigError(
                        f"import_rules key {importer}: "
                        f"tear level {importer} exceeds max_tear {self.max_tear}"
                    )
                if not 0 <= max_allowed <= self.max_tear:
                    raise ConfigError(
                        f"import_rules[{importer}] = {max_allowed}: "
                        f"max_allowed {max_allowed} exceeds max_tear {self.max_tear}"
                    )
        if self.default_tear is not None and not 0 <= self.default_tear <= self.max_tear:
            raise ConfigError(f"default_tear {self.default_tear} exceeds max_tear {self.max_tear}")
        for path, tear in self.default_tears.items():
            if not 0 <= tear <= self.max_tear:
                raise ConfigError(
                    f"default_tears[{path!r}] = {tear}: "
                    f"tear level {tear} exceeds max_tear {self.max_tear}"
                )

    def resolved_import_rules(self) -> dict[int, frozenset[int]]:
        """Full matrix with defaults filled in for any unspecified tier."""
        resolved: dict[int, frozenset[int]] = {}
        for tier in range(self.max_tear + 1):
            if self.import_rules is not None and tier in self.import_rules:
                resolved[tier] = frozenset(range(self.import_rules[tier] + 1))
            else:
                resolved[tier] = frozenset(range(tier + 1))
        return resolved

    def resolve_missing_tier(self, rel_path: str) -> tuple[int, bool]:
        """Return (effective_tier, was_defaulted) for a file with no @tear header.

        Lookup order: longest-prefix match in default_tears → global default_tear
        → max_tear (not defaulted; caller should emit the missing-header warning).
        """
        file_segs = _path_segments(rel_path)
        longest_len = -1
        matched: int | None = None
        for dir_key, tier in self.default_tears.items():
            dir_segs = _path_segments(dir_key)
            if len(dir_segs) > len(file_segs):
                continue
            if file_segs[: len(dir_segs)] != dir_segs:
                continue
            if len(dir_segs) > longest_len:
                longest_len = len(dir_segs)
                matched = tier
        if matched is not None:
            return matched, True
        if self.default_tear is not None:
            return self.default_tear, True
        return self.max_tear, False


def load_config(repo_root: Path) -> TearsConfig:
    """Load `.tears.toml` from `repo_root`. Missing file => defaults.

    Malformed TOML or a schema failure raises `ConfigError` with a clear message
    naming the file and the problem.
    """
    config_path = repo_root / CONFIG_FILENAME
    if not config_path.exists():
        return TearsConfig()

    try:
        raw = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{CONFIG_FILENAME}: malformed TOML: {exc}") from exc

    return _from_mapping(raw, source=CONFIG_FILENAME)


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

    if "import_rules" in raw:
        ir_raw = _require_mapping(raw["import_rules"], "import_rules", source)
        rules: dict[int, int] = {}
        for key, value in ir_raw.items():
            # TOML keys are always strings; convert to int.
            try:
                key_int = int(cast(str, key))
            except (ValueError, TypeError) as exc:
                raise ConfigError(
                    f"{source}: import_rules keys must be integer-valued strings, got {key!r}"
                ) from exc
            if not isinstance(value, int) or isinstance(value, bool):
                raise ConfigError(
                    f"{source}: import_rules[{key_int}] must be an int, got {type(value).__name__}"
                )
            rules[key_int] = value
        kwargs["import_rules"] = rules

    if "missing_header" in raw:
        kwargs["missing_header"] = _require_str(raw["missing_header"], "missing_header", source)

    if "default_tear" in raw:
        kwargs["default_tear"] = _require_int(raw["default_tear"], "default_tear", source)

    if "default_tears" in raw:
        dt_raw = _require_mapping(raw["default_tears"], "default_tears", source)
        default_tears: dict[str, int] = {}
        for key, value in dt_raw.items():
            if not isinstance(key, str) or not isinstance(value, int) or isinstance(value, bool):
                raise ConfigError(
                    f"{source}: default_tears entries must be str -> int, got {key!r} -> {value!r}"
                )
            default_tears[key.rstrip("/")] = value
        kwargs["default_tears"] = default_tears

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
