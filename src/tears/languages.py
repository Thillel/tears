# @tear: 2
"""Language metadata shared by scanner configuration and import builders."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

SUPPORTED_LANGUAGES = frozenset(
    {
        "c",
        "cpp",
        "csharp",
        "dart",
        "go",
        "java",
        "javascript",
        "kotlin",
        "php",
        "python",
        "ruby",
        "rust",
        "typescript",
    }
)

LANGUAGES_BY_SUFFIX: Mapping[str, tuple[str, ...]] = {
    ".py": ("python",),
    ".ts": ("typescript",),
    ".tsx": ("typescript",),
    ".js": ("javascript",),
    ".jsx": ("javascript",),
    ".mjs": ("javascript",),
    ".cjs": ("javascript",),
    ".c": ("c",),
    ".h": ("c", "cpp"),
    ".cpp": ("cpp",),
    ".cc": ("cpp",),
    ".cxx": ("cpp",),
    ".hpp": ("cpp",),
    ".hh": ("cpp",),
    ".hxx": ("cpp",),
    ".cs": ("csharp",),
    ".dart": ("dart",),
    ".go": ("go",),
    ".java": ("java",),
    ".kt": ("kotlin",),
    ".php": ("php",),
    ".rb": ("ruby",),
    ".rs": ("rust",),
}

SOURCE_SUFFIXES_BY_LANGUAGE: Mapping[str, tuple[str, ...]] = {
    "python": (".py",),
    "typescript": (".ts", ".tsx", ".js", ".jsx"),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "c": (".h", ".c"),
    "cpp": (".hpp", ".hh", ".hxx", ".h", ".cpp", ".cc", ".cxx"),
    "csharp": (".cs",),
    "dart": (".dart",),
    "go": (".go",),
    "java": (".java",),
    "kotlin": (".kt",),
    "php": (".php",),
    "ruby": (".rb",),
    "rust": (".rs",),
}


def supported_languages_text() -> str:
    return ", ".join(sorted(SUPPORTED_LANGUAGES))


def enabled_language_for_suffix(suffix: str, enabled_languages: Iterable[str]) -> str | None:
    enabled = frozenset(enabled_languages)
    return next(
        (language for language in LANGUAGES_BY_SUFFIX.get(suffix, ()) if language in enabled),
        None,
    )
