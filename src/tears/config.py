# @tear: 3
"""`.tears.toml` parsing and validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from tears.languages import SUPPORTED_LANGUAGES, supported_languages_text

CONFIG_FILENAME = ".tears.toml"
MISSING_HEADER_VALUES = ("warn", "error")
_GLOB_CHARS = frozenset("*?[")


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
    artificial_tears: dict[str, int] = field(default_factory=lambda: {})
    exclude: list[str] = field(default_factory=lambda: [])
    scan_exclude: list[str] = field(default_factory=lambda: [])
    mutate_exclude: list[str] = field(default_factory=lambda: [])
    respect_gitignore: bool = True
    scan_respect_gitignore: bool | None = None
    mutate_respect_gitignore: bool | None = None
    source_roots: list[str] = field(default_factory=lambda: ["."])
    languages: list[str] = field(default_factory=lambda: ["python"])
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
        for path, tier in self.artificial_tears.items():
            if not 0 <= tier <= self.max_tear:
                raise ConfigError(
                    f"artificial_tears[{path!r}] = {tier}: "
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
        for language in self.languages:
            if language not in SUPPORTED_LANGUAGES:
                raise ConfigError(
                    f"unsupported language {language!r}; supported languages: "
                    f"{supported_languages_text()}"
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

    def excludes_for_scan(self) -> list[str]:
        """Exclude patterns that apply while scanning."""
        return [*self.exclude, *self.scan_exclude]

    def excludes_for_mutation(self) -> list[str]:
        """Exclude patterns that apply while mutating headers through hooks/CLI."""
        return [*self.exclude, *self.mutate_exclude]

    def respect_gitignore_for_scan(self) -> bool:
        """Whether scanner filtering should skip gitignored paths."""
        if self.scan_respect_gitignore is not None:
            return self.scan_respect_gitignore
        return self.respect_gitignore

    def respect_gitignore_for_mutation(self) -> bool:
        """Whether hook/CLI header marking should skip gitignored paths."""
        if self.mutate_respect_gitignore is not None:
            return self.mutate_respect_gitignore
        return self.respect_gitignore

    def artificial_tear_for(self, rel_path: str) -> int | None:
        """Return the longest-prefix artificial import tear for `rel_path`."""
        file_segs = _path_segments(rel_path)
        longest_len = -1
        matched: int | None = None
        for dir_key, tier in self.artificial_tears.items():
            dir_segs = _path_segments(dir_key)
            if len(dir_segs) > len(file_segs):
                continue
            if file_segs[: len(dir_segs)] != dir_segs:
                continue
            if len(dir_segs) > longest_len:
                longest_len = len(dir_segs)
                matched = tier
        return matched

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
        kwargs["directory_requirements"] = _parse_path_int_mapping(
            raw["directory_requirements"], "directory_requirements", source
        )

    if "artificial_tears" in raw:
        kwargs["artificial_tears"] = _parse_path_int_mapping(
            raw["artificial_tears"],
            "artificial_tears",
            source,
            allow_globs=False,
        )

    if "exclude" in raw:
        kwargs["exclude"] = _parse_string_list(raw["exclude"], "exclude", source)

    if "languages" in raw:
        kwargs["languages"] = _parse_language_list(raw["languages"], "languages", source)

    if "respect_gitignore" in raw:
        kwargs["respect_gitignore"] = _require_bool(
            raw["respect_gitignore"], "respect_gitignore", source
        )

    if "scan" in raw:
        scan_raw = _require_mapping(raw["scan"], "scan", source)
        if "exclude" in scan_raw:
            kwargs["scan_exclude"] = _parse_string_list(scan_raw["exclude"], "scan.exclude", source)
        if "respect_gitignore" in scan_raw:
            kwargs["scan_respect_gitignore"] = _require_bool(
                scan_raw["respect_gitignore"], "scan.respect_gitignore", source
            )

    if "mutate" in raw:
        mutate_raw = _require_mapping(raw["mutate"], "mutate", source)
        if "exclude" in mutate_raw:
            kwargs["mutate_exclude"] = _parse_string_list(
                mutate_raw["exclude"], "mutate.exclude", source
            )
        if "respect_gitignore" in mutate_raw:
            kwargs["mutate_respect_gitignore"] = _require_bool(
                mutate_raw["respect_gitignore"], "mutate.respect_gitignore", source
            )

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
        kwargs["default_tears"] = _parse_path_int_mapping(
            raw["default_tears"], "default_tears", source
        )

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


def _require_bool(value: Any, key: str, source: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{source}: {key} must be bool, got {type(value).__name__}")
    return value


def _require_mapping(value: Any, key: str, source: str) -> dict[Any, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: {key} must be a mapping, got {type(value).__name__}")
    return cast(dict[Any, Any], value)


def _require_list(value: Any, key: str, source: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(f"{source}: {key} must be a list, got {type(value).__name__}")
    return cast(list[Any], value)


def _parse_string_list(value: Any, key: str, source: str) -> list[str]:
    raw = _require_list(value, key, source)
    parsed: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ConfigError(f"{source}: {key} entries must be strings, got {item!r}")
        parsed.append(item)
    return parsed


def _parse_language_list(value: Any, key: str, source: str) -> list[str]:
    parsed = [language.lower() for language in _parse_string_list(value, key, source)]
    unsupported = sorted(set(parsed) - SUPPORTED_LANGUAGES)
    if unsupported:
        raise ConfigError(
            f"{source}: unsupported language {unsupported[0]!r}; "
            f"supported languages: {supported_languages_text()}"
        )
    return parsed


def _parse_path_int_mapping(
    value: Any,
    key: str,
    source: str,
    *,
    allow_globs: bool = True,
) -> dict[str, int]:
    raw = _require_mapping(value, key, source)
    parsed: dict[str, int] = {}
    for item_key, item_value in raw.items():
        if (
            not isinstance(item_key, str)
            or not isinstance(item_value, int)
            or isinstance(item_value, bool)
        ):
            raise ConfigError(
                f"{source}: {key} entries must be str -> int, got {item_key!r} -> {item_value!r}"
            )
        if not allow_globs and any(char in item_key for char in _GLOB_CHARS):
            raise ConfigError(
                f"{source}: {key} keys are directory paths, not glob patterns, got {item_key!r}"
            )
        parsed[item_key.rstrip("/")] = item_value
    return parsed
