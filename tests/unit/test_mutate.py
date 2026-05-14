# @tear: 3
"""Tests for tears.mutate — set_tear (pure string transform) and process_file."""

from __future__ import annotations

from pathlib import Path

import pytest

from tears.mutate import process_file, set_tear

# --- Replace existing header ---


@pytest.mark.parametrize(
    "before, after",
    [
        ("# @tear: 0\nimport os\n", "# @tear: 3\nimport os\n"),
        ("# @tear: 1\nimport os\n", "# @tear: 3\nimport os\n"),
        ("# @tear: 2\nimport os\n", "# @tear: 3\nimport os\n"),
        ("# @tear: 3\nimport os\n", "# @tear: 3\nimport os\n"),  # idempotent
    ],
    ids=["from-0", "from-1", "from-2", "already-3"],
)
def test_replaces_existing_header(before: str, after: str) -> None:
    assert set_tear(before) == after


def test_preserves_indentation_of_existing_header() -> None:
    assert (
        set_tear("  # @tear: 1\nclass Inside:\n    pass\n")
        == "  # @tear: 3\nclass Inside:\n    pass\n"
    )


def test_replaces_malformed_header_too() -> None:
    assert set_tear("# @tear: 99\nx = 1\n") == "# @tear: 3\nx = 1\n"


# --- Multiple-header collapse ---


def test_multiple_headers_all_replaced() -> None:
    assert set_tear("# @tear: 0\n# @tear: 1\nimport os\n") == "# @tear: 3\n# @tear: 3\nimport os\n"


# --- Insert when missing ---


def test_inserts_header_when_missing() -> None:
    assert set_tear("import os\n") == "# @tear: 3\nimport os\n"


def test_inserts_into_empty_file() -> None:
    assert set_tear("") == "# @tear: 3\n"


def test_inserts_without_trailing_newline_preserves_lack_of_one() -> None:
    assert set_tear("import os") == "# @tear: 3\nimport os"


# --- Preserve shebang / encoding declaration ---


def test_inserts_after_shebang() -> None:
    assert (
        set_tear("#!/usr/bin/env python3\nimport os\n")
        == "#!/usr/bin/env python3\n# @tear: 3\nimport os\n"
    )


def test_inserts_after_encoding_declaration() -> None:
    assert (
        set_tear("# -*- coding: utf-8 -*-\nimport os\n")
        == "# -*- coding: utf-8 -*-\n# @tear: 3\nimport os\n"
    )


def test_inserts_after_shebang_and_encoding() -> None:
    assert (
        set_tear("#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nimport os\n")
        == "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n# @tear: 3\nimport os\n"
    )


def test_alternative_encoding_syntax_with_equals() -> None:
    assert set_tear("# coding=utf-8\nimport os\n") == "# coding=utf-8\n# @tear: 3\nimport os\n"


# --- Custom tear level ---


def test_custom_tear_replaces() -> None:
    assert set_tear("# @tear: 0\nx = 1\n", tear=5) == "# @tear: 5\nx = 1\n"


def test_custom_tear_inserts() -> None:
    assert set_tear("x = 1\n", tear=1) == "# @tear: 1\nx = 1\n"


# --- Idempotency ---


def test_idempotent_on_already_set_file() -> None:
    original = "# @tear: 3\nimport os\n"
    assert set_tear(set_tear(original)) == original


def test_idempotent_on_newly_inserted_header() -> None:
    original = "def f(): pass\n"
    once = set_tear(original)
    assert set_tear(once) == once


# --- Line endings ---


def test_preserves_crlf_line_endings() -> None:
    assert set_tear("# @tear: 0\r\nimport os\r\n") == "# @tear: 3\r\nimport os\r\n"


# --- Replacement works across any comment style ---


@pytest.mark.parametrize(
    "before, after",
    [
        ("// @tear: 1\nconst x = 1;\n", "// @tear: 3\nconst x = 1;\n"),
        ("-- @tear: 1\nSELECT 1;\n", "-- @tear: 3\nSELECT 1;\n"),
        ("; @tear: 1\n[section]\n", "; @tear: 3\n[section]\n"),
        ("<!-- @tear: 1 -->\n# heading\n", "<!-- @tear: 3 -->\n# heading\n"),
        ("/* @tear: 1 */\nbody {}\n", "/* @tear: 3 */\nbody {}\n"),
        ("# @tear: 1\nfoo: bar\n", "# @tear: 3\nfoo: bar\n"),
    ],
    ids=["js", "sql", "ini", "html", "css", "hash-non-py"],
)
def test_replaces_in_any_comment_style(before: str, after: str) -> None:
    assert set_tear(before, extension=".unknown") == after


def test_unsupported_type_without_header_is_noop() -> None:
    content = "raw bytes-ish content\n"
    assert set_tear(content, extension=".unknown-ext") == content


def test_known_extension_match_is_case_insensitive() -> None:
    assert set_tear("import os\n", extension=".PY") == "# @tear: 3\nimport os\n"


# --- Insertion for non-Python file types ---


@pytest.mark.parametrize(
    "extension, before, after",
    [
        (".js", "const x = 1;\n", "// @tear: 3\nconst x = 1;\n"),
        (".ts", "export const x = 1;\n", "// @tear: 3\nexport const x = 1;\n"),
        (".go", "package main\n", "// @tear: 3\npackage main\n"),
        (".rs", "fn main() {}\n", "// @tear: 3\nfn main() {}\n"),
        (".sh", "echo hi\n", "# @tear: 3\necho hi\n"),
        (".rb", "puts 'hi'\n", "# @tear: 3\nputs 'hi'\n"),
        (".toml", '[tool]\nname = "x"\n', '# @tear: 3\n[tool]\nname = "x"\n'),
        (".yaml", "key: value\n", "# @tear: 3\nkey: value\n"),
        (".sql", "SELECT 1;\n", "-- @tear: 3\nSELECT 1;\n"),
        (".lua", "print('hi')\n", "-- @tear: 3\nprint('hi')\n"),
        (".ini", "[section]\n", "; @tear: 3\n[section]\n"),
        (".html", "<html></html>\n", "<!-- @tear: 3 -->\n<html></html>\n"),
        (".md", "# Heading\n", "<!-- @tear: 3 -->\n# Heading\n"),
        (".xml", "<root/>\n", "<!-- @tear: 3 -->\n<root/>\n"),
        (".css", "body {}\n", "/* @tear: 3 */\nbody {}\n"),
        (".scss", "$x: 1;\n", "/* @tear: 3 */\n$x: 1;\n"),
    ],
    ids=[
        "js",
        "ts",
        "go",
        "rs",
        "sh",
        "rb",
        "toml",
        "yaml",
        "sql",
        "lua",
        "ini",
        "html",
        "md",
        "xml",
        "css",
        "scss",
    ],
)
def test_inserts_header_in_known_extensions(extension: str, before: str, after: str) -> None:
    assert set_tear(before, extension=extension) == after


@pytest.mark.parametrize(
    "filename, before, after",
    [
        ("Makefile", ".PHONY: test\n", "# @tear: 3\n.PHONY: test\n"),
        ("Dockerfile", "FROM python:3.11\n", "# @tear: 3\nFROM python:3.11\n"),
        (".gitignore", "*.pyc\n", "# @tear: 3\n*.pyc\n"),
        (".env", "DEBUG=1\n", "# @tear: 3\nDEBUG=1\n"),
    ],
    ids=["makefile", "dockerfile", "gitignore", "dotenv"],
)
def test_inserts_header_for_extensionless_files(filename: str, before: str, after: str) -> None:
    assert set_tear(before, extension="", filename=filename) == after


# --- process_file ---


def test_process_file_modifies_a_py_file(tmp_path: Path) -> None:
    target = tmp_path / "src" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")
    assert process_file(target, tear=3, exclude=[], repo_root=tmp_path) is True
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_process_file_sets_non_python_file(tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    target.write_text("# @tear: 1\n.PHONY: test\ntest:\n\tpytest\n")
    assert process_file(target, tear=3, exclude=[], repo_root=tmp_path) is True
    assert target.read_text() == "# @tear: 3\n.PHONY: test\ntest:\n\tpytest\n"


def test_process_file_sets_markdown(tmp_path: Path) -> None:
    target = tmp_path / "audit.md"
    target.write_text("<!-- @tear: 1 -->\n# Audit\n")
    assert process_file(target, tear=3, exclude=[], repo_root=tmp_path) is True
    assert target.read_text() == "<!-- @tear: 3 -->\n# Audit\n"


def test_process_file_noop_on_unknown_type_without_header(tmp_path: Path) -> None:
    target = tmp_path / "data.unknown-ext"
    target.write_text("raw content\n")
    assert process_file(target, tear=3, exclude=[], repo_root=tmp_path) is False
    assert target.read_text() == "raw content\n"


def test_process_file_inserts_into_extensionless_file(tmp_path: Path) -> None:
    target = tmp_path / "Makefile"
    target.write_text(".PHONY: test\n")
    assert process_file(target, tear=3, exclude=[], repo_root=tmp_path) is True
    assert target.read_text() == "# @tear: 3\n.PHONY: test\n"


def test_process_file_skips_excluded(tmp_path: Path) -> None:
    target = tmp_path / "generated" / "schema.py"
    target.parent.mkdir()
    target.write_text("import os\n")
    assert process_file(target, tear=3, exclude=["generated/**"], repo_root=tmp_path) is False
    assert target.read_text() == "import os\n"


def test_process_file_noop_when_already_at_target(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("# @tear: 3\nimport os\n")
    assert process_file(target, tear=3, exclude=[], repo_root=tmp_path) is False
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_process_file_noop_on_missing_path(tmp_path: Path) -> None:
    assert process_file(tmp_path / "ghost.py", tear=3, exclude=[], repo_root=tmp_path) is False
