# @tear: 2
"""Tests for the Claude Code post-edit hook.

The hook is `tears.hook.apply_hook` — a pure string transformation. The CLI
glue (`tears.hook.main`) is exercised separately at the bottom for the argv
and stdin paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tears.hook import apply_hook, main, process_file

# --- Replace existing header ---


@pytest.mark.parametrize(
    "before, after",
    [
        ("# @tear: 0\nimport os\n", "# @tear: 3\nimport os\n"),
        ("# @tear: 1\nimport os\n", "# @tear: 3\nimport os\n"),
        ("# @tear: 2\nimport os\n", "# @tear: 3\nimport os\n"),
        # Idempotent: already at max
        ("# @tear: 3\nimport os\n", "# @tear: 3\nimport os\n"),
    ],
    ids=["from-0", "from-1", "from-2", "already-3"],
)
def test_replaces_existing_header(before: str, after: str) -> None:
    assert apply_hook(before) == after


def test_preserves_indentation_of_existing_header() -> None:
    before = "  # @tear: 1\nclass Inside:\n    pass\n"
    after = "  # @tear: 3\nclass Inside:\n    pass\n"
    assert apply_hook(before) == after


def test_replaces_malformed_header_too() -> None:
    """An out-of-range @tear: 99 should be rewritten to max_tear, not ignored."""
    assert apply_hook("# @tear: 99\nx = 1\n") == "# @tear: 3\nx = 1\n"


# --- Multiple-header collapse ---


def test_multiple_headers_all_replaced() -> None:
    """If a file somehow has multiple @tear lines, ALL get rewritten."""
    before = "# @tear: 0\n# @tear: 1\nimport os\n"
    after = "# @tear: 3\n# @tear: 3\nimport os\n"
    assert apply_hook(before) == after


# --- Insert when missing ---


def test_inserts_header_when_missing() -> None:
    assert apply_hook("import os\n") == "# @tear: 3\nimport os\n"


def test_inserts_into_empty_file() -> None:
    assert apply_hook("") == "# @tear: 3\n"


def test_inserts_without_trailing_newline_preserves_lack_of_one() -> None:
    """Source files without a final newline stay without one (except the header line)."""
    result = apply_hook("import os")
    assert result == "# @tear: 3\nimport os"


# --- Preserve shebang / encoding declaration ---


def test_inserts_after_shebang() -> None:
    before = "#!/usr/bin/env python3\nimport os\n"
    after = "#!/usr/bin/env python3\n# @tear: 3\nimport os\n"
    assert apply_hook(before) == after


def test_inserts_after_encoding_declaration() -> None:
    """PEP 263 — encoding declaration must stay on line 1 or 2."""
    before = "# -*- coding: utf-8 -*-\nimport os\n"
    after = "# -*- coding: utf-8 -*-\n# @tear: 3\nimport os\n"
    assert apply_hook(before) == after


def test_inserts_after_shebang_and_encoding() -> None:
    before = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nimport os\n"
    after = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n# @tear: 3\nimport os\n"
    assert apply_hook(before) == after


def test_alternative_encoding_syntax_with_equals() -> None:
    """`coding=utf-8` is also valid per PEP 263."""
    before = "# coding=utf-8\nimport os\n"
    after = "# coding=utf-8\n# @tear: 3\nimport os\n"
    assert apply_hook(before) == after


# --- Custom max_tear ---


def test_custom_max_tear() -> None:
    assert apply_hook("# @tear: 0\nx = 1\n", max_tear=5) == "# @tear: 5\nx = 1\n"


def test_custom_max_tear_inserted_when_missing() -> None:
    assert apply_hook("x = 1\n", max_tear=1) == "# @tear: 1\nx = 1\n"


# --- Idempotency ---


def test_idempotent_on_already_demoted_file() -> None:
    original = "# @tear: 3\nimport os\n"
    once = apply_hook(original)
    twice = apply_hook(once)
    assert once == twice == original


def test_idempotent_on_newly_inserted_header() -> None:
    """Running the hook on a file Claude just edited, then again, is a no-op the
    second time."""
    original = "def f(): pass\n"
    once = apply_hook(original)
    twice = apply_hook(once)
    assert once == twice


# --- Line endings ---


def test_preserves_crlf_line_endings_on_existing_header() -> None:
    before = "# @tear: 0\r\nimport os\r\n"
    after = "# @tear: 3\r\nimport os\r\n"
    assert apply_hook(before) == after


# --- Replacement works across any comment style ---


@pytest.mark.parametrize(
    "before, after",
    [
        # Line comments
        ("// @tear: 1\nconst x = 1;\n", "// @tear: 3\nconst x = 1;\n"),
        ("-- @tear: 1\nSELECT 1;\n", "-- @tear: 3\nSELECT 1;\n"),
        ("; @tear: 1\n[section]\n", "; @tear: 3\n[section]\n"),
        # Block comments (trailing tokens preserved)
        ("<!-- @tear: 1 -->\n# heading\n", "<!-- @tear: 3 -->\n# heading\n"),
        ("/* @tear: 1 */\nbody {}\n", "/* @tear: 3 */\nbody {}\n"),
        # Python-style `#` comment in a non-Python file (YAML, TOML, Makefile)
        ("# @tear: 1\nfoo: bar\n", "# @tear: 3\nfoo: bar\n"),
    ],
    ids=["js", "sql", "ini", "html", "css", "hash-non-py"],
)
def test_replaces_in_any_comment_style(before: str, after: str) -> None:
    """Replacement is universal — extension only matters for insertion."""
    assert apply_hook(before, extension=".unknown") == after


def test_unsupported_type_without_header_is_noop() -> None:
    """A file of unknown type with no header → unchanged."""
    content = "raw bytes-ish content\n"
    assert apply_hook(content, extension=".unknown-ext") == content


def test_known_extension_match_is_case_insensitive() -> None:
    """`.PY` should still get header insertion."""
    assert apply_hook("import os\n", extension=".PY") == "# @tear: 3\nimport os\n"


# --- Insertion for non-Python file types ---


@pytest.mark.parametrize(
    "extension, before, after",
    [
        # Line-comment families
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
        # Block-comment families
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
def test_inserts_header_in_known_extensions(
    extension: str, before: str, after: str
) -> None:
    assert apply_hook(before, extension=extension) == after


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
def test_inserts_header_for_extensionless_files(
    filename: str, before: str, after: str
) -> None:
    # Pass empty extension to simulate Path("Makefile").suffix
    assert apply_hook(before, extension="", filename=filename) == after


# --- process_file (filesystem boundary) ---


def test_process_file_modifies_a_py_file(tmp_path: Path) -> None:
    target = tmp_path / "src" / "x.py"
    target.parent.mkdir()
    target.write_text("import os\n")
    changed = process_file(target, max_tear=3, exclude=[], repo_root=tmp_path)
    assert changed is True
    assert target.read_text() == "# @tear: 3\nimport os\n"


def test_process_file_demotes_existing_header_in_non_python(tmp_path: Path) -> None:
    """A Makefile / .toml / .yml with `# @tear: 1` gets demoted on touch."""
    target = tmp_path / "Makefile"
    target.write_text("# @tear: 1\n.PHONY: test\ntest:\n\tpytest\n")
    changed = process_file(target, max_tear=3, exclude=[], repo_root=tmp_path)
    assert changed is True
    assert target.read_text() == "# @tear: 3\n.PHONY: test\ntest:\n\tpytest\n"


def test_process_file_demotes_md_with_html_comment_header(tmp_path: Path) -> None:
    """Markdown with `<!-- @tear: 1 -->` → demoted in place."""
    target = tmp_path / "audit.md"
    target.write_text("<!-- @tear: 1 -->\n# Audit\n")
    changed = process_file(target, max_tear=3, exclude=[], repo_root=tmp_path)
    assert changed is True
    assert target.read_text() == "<!-- @tear: 3 -->\n# Audit\n"


def test_process_file_no_op_on_unsupported_type_without_header(tmp_path: Path) -> None:
    """A file of unknown type with no header → unchanged."""
    target = tmp_path / "data.unknown-ext"
    target.write_text("raw content\n")
    changed = process_file(target, max_tear=3, exclude=[], repo_root=tmp_path)
    assert changed is False
    assert target.read_text() == "raw content\n"


def test_process_file_inserts_into_markdown(tmp_path: Path) -> None:
    """README.md with no header → gets `<!-- @tear: 3 -->` inserted."""
    target = tmp_path / "README.md"
    target.write_text("# hello\n")
    changed = process_file(target, max_tear=3, exclude=[], repo_root=tmp_path)
    assert changed is True
    assert target.read_text() == "<!-- @tear: 3 -->\n# hello\n"


def test_process_file_inserts_into_extensionless_file(tmp_path: Path) -> None:
    """Makefile without a header → gets `# @tear: 3` inserted (filename-keyed)."""
    target = tmp_path / "Makefile"
    target.write_text(".PHONY: test\n")
    changed = process_file(target, max_tear=3, exclude=[], repo_root=tmp_path)
    assert changed is True
    assert target.read_text() == "# @tear: 3\n.PHONY: test\n"


def test_process_file_skips_excluded(tmp_path: Path) -> None:
    target = tmp_path / "generated" / "schema.py"
    target.parent.mkdir()
    target.write_text("import os\n")
    changed = process_file(
        target, max_tear=3, exclude=["generated/**"], repo_root=tmp_path
    )
    assert changed is False
    assert target.read_text() == "import os\n"


def test_process_file_returns_false_when_already_demoted(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("# @tear: 3\nimport os\n")
    changed = process_file(target, max_tear=3, exclude=[], repo_root=tmp_path)
    assert changed is False


def test_process_file_missing_path_is_a_noop(tmp_path: Path) -> None:
    changed = process_file(
        tmp_path / "ghost.py", max_tear=3, exclude=[], repo_root=tmp_path
    )
    assert changed is False


# --- CLI: argv path ---


def test_main_with_argv_paths(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_text("import os\n")
    assert main([str(target)]) == 0
    assert "# @tear: 3" in target.read_text()


# --- CLI: stdin JSON path (Claude Code PostToolUse contract) ---


def test_main_with_stdin_claude_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "x.py"
    target.write_text("import os\n")

    # Make stdin produce the JSON payload Claude Code sends.
    import io

    payload = json.dumps({"tool_input": {"file_path": str(target)}})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    assert main([]) == 0
    assert "# @tear: 3" in target.read_text()


def test_main_with_empty_stdin_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main([]) == 0


def test_main_with_malformed_stdin_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    assert main([]) == 0


def test_main_with_broken_config_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken .tears.yml shouldn't break Claude Code — fall back to defaults."""
    (tmp_path / ".tears.yml").write_text("max_tear: : :\n  nope\n")
    target = tmp_path / "x.py"
    target.write_text("import os\n")
    monkeypatch.chdir(tmp_path)
    assert main([str(target)]) == 0
    assert "# @tear: 3" in target.read_text()
