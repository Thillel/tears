# @tear: 3
"""Regenerate the Tears launch/demo image from real fixture command output."""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
WORK = ROOT / ".work"
OUT = ROOT / "out"
SVG_OUT = OUT / "tears-readme-demo.svg"
PNG_OUT = OUT / "tears-readme-demo.png"

WIDTH = 1600
HEIGHT = 900


@dataclass(frozen=True)
class CommandOutput:
    display: str
    lines: tuple[str, ...]
    returncode: int


def main() -> int:
    without_dir, with_dir = prepare_demo_repos()

    stage_policy(without_dir)
    left_diff = git_diff_cached(without_dir)
    assert_no_tear_header(left_diff, label="without-Tears diff")

    policy = with_dir / "src/auth/policy.py"
    run_hidden([sys.executable, "-m", "tears.hook", str(policy)], cwd=with_dir)
    stage_policy(with_dir)
    right_diff = git_diff_cached(with_dir)

    left_pytest = run_command(
        "$ pytest -q",
        [sys.executable, "-m", "pytest", "-q"],
        cwd=without_dir,
        expected_returncode=0,
    )
    right_pytest = run_command(
        "$ pytest -q",
        [sys.executable, "-m", "pytest", "-q"],
        cwd=with_dir,
        expected_returncode=0,
    )
    right_tears = run_command(
        "$ tears",
        [sys.executable, "-m", "tears", "."],
        cwd=with_dir,
        expected_returncode=1,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    SVG_OUT.write_text(render_svg(left_diff, right_diff, left_pytest, right_pytest, right_tears))
    png_written = render_png_if_possible()

    print(f"wrote {SVG_OUT.relative_to(ROOT)}")
    if png_written:
        print(f"wrote {PNG_OUT.relative_to(ROOT)}")
    else:
        print("skipped PNG export: rsvg-convert not found")
    return 0


def prepare_demo_repos() -> tuple[Path, Path]:
    if WORK.exists():
        shutil.rmtree(WORK)

    without_dir = WORK / "without-tears"
    with_dir = WORK / "with-tears"

    shutil.copytree(FIXTURES / "without-tears", without_dir)
    shutil.copytree(FIXTURES / "with-tears", with_dir)
    write_baseline_policy(without_dir, fixture_name="baseline-without-tears")
    init_git_repo(without_dir)
    write_final_policy(without_dir, fixture_name="without-tears")

    write_baseline_policy(with_dir, fixture_name="baseline-with-tears")
    init_git_repo(with_dir)
    write_final_policy(with_dir, fixture_name="with-tears")
    return without_dir, with_dir


def write_baseline_policy(repo: Path, *, fixture_name: str) -> None:
    source = FIXTURES / fixture_name / "src/auth/policy.py"
    (repo / "src/auth/policy.py").write_text(source.read_text())


def write_final_policy(repo: Path, *, fixture_name: str) -> None:
    source = FIXTURES / fixture_name / "src/auth/policy.py"
    (repo / "src/auth/policy.py").write_text(source.read_text())


def init_git_repo(repo: Path) -> None:
    run_hidden(["git", "init", "--quiet"], cwd=repo)
    run_hidden(["git", "add", "."], cwd=repo)
    run_hidden(
        [
            "git",
            "-c",
            "user.name=Tears Demo",
            "-c",
            "user.email=demo@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "baseline",
        ],
        cwd=repo,
    )


def stage_policy(repo: Path) -> None:
    run_hidden(["git", "add", "src/auth/policy.py"], cwd=repo)


def git_diff_cached(repo: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--no-ext-diff",
            "--no-color",
            "--unified=5",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--",
            "src/auth/policy.py",
        ],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=command_env(),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed with {result.returncode}\n{result.stdout}")
    return result.stdout.rstrip("\n").splitlines()


def assert_no_tear_header(lines: list[str], *, label: str) -> None:
    visible_tier_lines = [
        line for line in lines if "@tear:" in line and not line.startswith("diff --git")
    ]
    if visible_tier_lines:
        joined = "\n".join(visible_tier_lines)
        raise RuntimeError(f"{label} unexpectedly contains a tear header:\n{joined}")


def run_hidden(args: list[str], *, cwd: Path) -> None:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=command_env(),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{args!r} failed with {result.returncode}\n{result.stdout}")


def run_command(
    display: str,
    args: list[str],
    *,
    cwd: Path,
    expected_returncode: int,
) -> CommandOutput:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=command_env(),
        check=False,
    )
    output = result.stdout.rstrip("\n")
    lines = tuple(output.splitlines()) if output else ()
    if result.returncode != expected_returncode:
        rendered = "\n".join((display, *lines))
        raise RuntimeError(
            f"{display} returned {result.returncode}, expected {expected_returncode}\n{rendered}"
        )
    return CommandOutput(display=display, lines=lines, returncode=result.returncode)


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "COLUMNS": "72",
            "NO_COLOR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
    )
    return env


def render_png_if_possible() -> bool:
    converter = shutil.which("rsvg-convert")
    if converter is None:
        return False
    subprocess.run(
        [
            converter,
            "--width",
            str(WIDTH),
            "--height",
            str(HEIGHT),
            "--format",
            "png",
            "--output",
            str(PNG_OUT),
            str(SVG_OUT),
        ],
        check=True,
    )
    return True


def render_svg(
    left_diff: list[str],
    right_diff: list[str],
    left_pytest: CommandOutput,
    right_pytest: CommandOutput,
    right_tears: CommandOutput,
) -> str:
    parts: list[str] = [
        "<!-- @tear: 3 -->",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        '  <title id="title">Vibe Code Responsibly</title>',
        '  <desc id="desc">A side-by-side comparison showing the same unsafe '
        "AI auth fallback without Tears and with Tears.</desc>",
        style_block(),
        '  <rect width="1600" height="900" fill="url(#bg)"/>',
        '  <path d="M70 143H1530" class="rule-line"/>',
        '  <path d="M800 174V860" class="rule-line"/>',
        '  <text x="800" y="82" text-anchor="middle" class="sans title">'
        "Vibe Code Responsibly</text>",
        '  <text x="70" y="171" class="sans column-title">Without Tears</text>',
        '  <text x="70" y="196" class="sans column-note">All tests passed.</text>',
        '  <text x="820" y="171" class="sans column-title">With Tears</text>',
        '  <text x="820" y="196" class="sans column-note">Merge blocked.</text>',
    ]
    parts.extend(
        render_diff_panel(
            x=70,
            y=220,
            width=710,
            height=428,
            file_label="src/auth/policy.py",
            status_label="plausible diff",
            lines=left_diff,
            emphasize_tears=False,
        )
    )
    parts.extend(
        render_terminal_panel(
            x=70,
            y=676,
            width=710,
            height=184,
            title="CI",
            status_label="all tests passed",
            groups=[left_pytest],
        )
    )
    parts.extend(
        render_diff_panel(
            x=820,
            y=220,
            width=710,
            height=428,
            file_label="src/auth/policy.py",
            status_label="hook changed header",
            lines=right_diff,
            emphasize_tears=True,
        )
    )
    parts.extend(
        render_terminal_panel(
            x=820,
            y=676,
            width=710,
            height=184,
            title="CI",
            status_label="merge blocked",
            groups=[right_pytest, right_tears],
        )
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def style_block() -> str:
    return textwrap.dedent(
        """
          <defs>
            <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stop-color="#0a0f14"/>
              <stop offset="1" stop-color="#121820"/>
            </linearGradient>
            <filter id="shadow" x="-10%" y="-10%" width="120%" height="125%">
              <feDropShadow dx="0" dy="16" stdDeviation="24"
                flood-color="#000000" flood-opacity="0.38"/>
            </filter>
            <style>
              .sans { font-family: Inter, ui-sans-serif, system-ui,
                -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
              .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco,
                Consolas, "Liberation Mono", monospace; }
              .title { fill: #f7f3e8; font-size: 52px; font-weight: 760; letter-spacing: 0; }
              .column-title { fill: #edf2f7; font-size: 27px; font-weight: 700; letter-spacing: 0; }
              .column-note { fill: #93a1af; font-size: 15px; font-weight: 560; letter-spacing: 0; }
              .panel { fill: #0f151d; stroke: #283443; stroke-width: 1.25; }
              .panel-right { stroke: #b78232; stroke-width: 1.6; }
              .panel-bar { fill: #151d27; }
              .bar-text { fill: #d7dee8; font-size: 15px; font-weight: 650; letter-spacing: 0; }
              .bar-muted { fill: #8997a6; font-size: 13px; font-weight: 500; letter-spacing: 0; }
              .dot-red { fill: #ef6767; }
              .dot-yellow { fill: #f0bc5e; }
              .dot-green { fill: #59c68c; }
              .code { font-size: 13.2px; letter-spacing: 0; }
              .code-meta { fill: #7f8b99; }
              .code-context { fill: #c8d3df; }
              .code-add { fill: #80d8a5; }
              .code-remove { fill: #ff8b8b; }
              .line-add { fill: #143423; }
              .line-remove { fill: #3a1b20; }
              .line-warn { fill: #3c2d16; }
              .demotion-ring { fill: none; stroke: #f4b74d; stroke-width: 2; }
              .badge { fill: #24190b; stroke: #d69a32; stroke-width: 1; }
              .badge-text { fill: #ffd88a; font-size: 13px; font-weight: 720; letter-spacing: 0; }
              .terminal { fill: #090d12; stroke: #283443; stroke-width: 1.25; }
              .terminal-red { stroke: #d64c4c; stroke-width: 1.6; }
              .term-error-line { fill: #41181b; }
              .term-ok-line { fill: #112c20; }
              .terminal-text { fill: #dce5ef; font-size: 12px; letter-spacing: 0; }
              .terminal-muted { fill: #9ca9b6; }
              .terminal-error { fill: #ff8b8b; }
              .terminal-good { fill: #80d8a5; }
              .rule-line { stroke: #253141; stroke-width: 1; }
            </style>
          </defs>
        """
    ).strip()


def render_diff_panel(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    file_label: str,
    status_label: str,
    lines: list[str],
    emphasize_tears: bool,
) -> list[str]:
    parts = [
        '  <g filter="url(#shadow)">',
        f'    <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" '
        f'class="panel{" panel-right" if emphasize_tears else ""}"/>',
        f'    <rect x="{x}" y="{y}" width="{width}" height="44" rx="8" class="panel-bar"/>',
        f'    <path d="M{x} {y + 36}H{x + width}" class="rule-line"/>',
        f'    <circle cx="{x + 25}" cy="{y + 22}" r="6" class="dot-red"/>',
        f'    <circle cx="{x + 45}" cy="{y + 22}" r="6" class="dot-yellow"/>',
        f'    <circle cx="{x + 65}" cy="{y + 22}" r="6" class="dot-green"/>',
        f'    <text x="{x + 88}" y="{y + 27}" class="sans bar-text">{escape(file_label)}</text>',
        f'    <text x="{x + width - 102}" y="{y + 27}" text-anchor="end" '
        f'class="sans bar-muted">{escape(status_label)}</text>',
    ]
    text_x = x + 26
    line_y = y + 72
    line_h = 19
    tear_indices: list[int] = []
    for i, line in enumerate(lines):
        yy = line_y + i * line_h
        cls = diff_class(line)
        if line.startswith("+") and not line.startswith("+++"):
            rect_cls = "line-warn" if "@tear:" in line else "line-add"
            parts.append(
                f'    <rect x="{x + 20}" y="{yy - 14}" width="{width - 40}" '
                f'height="18" rx="3" class="{rect_cls}"/>'
            )
        elif line.startswith("-") and not line.startswith("---"):
            rect_cls = "line-warn" if "@tear:" in line else "line-remove"
            parts.append(
                f'    <rect x="{x + 20}" y="{yy - 14}" width="{width - 40}" '
                f'height="18" rx="3" class="{rect_cls}"/>'
            )
        if "@tear:" in line:
            tear_indices.append(i)
        parts.append(
            f'    <text x="{text_x}" y="{yy}" class="mono code {cls}">{escape(line)}</text>'
        )
    if emphasize_tears and tear_indices:
        first = line_y + min(tear_indices) * line_h - 17
        last = line_y + max(tear_indices) * line_h + 7
        parts.append(
            f'    <rect x="{x + 16}" y="{first}" width="{width - 32}" '
            f'height="{last - first}" rx="8" class="demotion-ring"/>'
        )
        parts.append(
            f'    <rect x="{x + width - 253}" y="{first - 13}" width="228" height="30" '
            f'rx="15" class="badge"/>'
        )
        parts.append(
            f'    <text x="{x + width - 139}" y="{first + 7}" text-anchor="middle" '
            f'class="sans badge-text">automatic hook demotion</text>'
        )
    parts.append("  </g>")
    return parts


def render_terminal_panel(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    status_label: str,
    groups: list[CommandOutput],
) -> list[str]:
    has_failure = any(group.returncode != 0 for group in groups)
    panel_class = "terminal terminal-red" if has_failure else "terminal"
    parts = [
        '  <g filter="url(#shadow)">',
        f'    <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" '
        f'class="{panel_class}"/>',
        f'    <rect x="{x}" y="{y}" width="{width}" height="42" rx="8" fill="#171016"/>',
        f'    <path d="M{x} {y + 42}H{x + width}" class="rule-line"/>',
        f'    <circle cx="{x + 25}" cy="{y + 21}" r="6" class="dot-red"/>',
        f'    <circle cx="{x + 45}" cy="{y + 21}" r="6" class="dot-yellow"/>',
        f'    <circle cx="{x + 65}" cy="{y + 21}" r="6" class="dot-green"/>',
        f'    <text x="{x + 88}" y="{y + 26}" class="sans bar-text">{escape(title)}</text>',
        f'    <text x="{x + width - 102}" y="{y + 26}" text-anchor="end" '
        f'class="sans bar-muted">{escape(status_label)}</text>',
    ]
    line_items = terminal_lines(groups)
    body_y = y + 64
    line_h = 14
    for i, (text, cls, background) in enumerate(line_items[:11]):
        yy = body_y + i * line_h
        if background is not None:
            parts.append(
                f'    <rect x="{x + 20}" y="{yy - 11}" width="{width - 40}" '
                f'height="14" rx="3" class="{background}"/>'
            )
        parts.append(
            f'    <text x="{x + 26}" y="{yy}" class="mono terminal-text {cls}">'
            f"{escape(text)}</text>"
        )
    parts.append("  </g>")
    return parts


def terminal_lines(groups: list[CommandOutput]) -> list[tuple[str, str, str | None]]:
    items: list[tuple[str, str, str | None]] = []
    for index, group in enumerate(groups):
        if index:
            items.append(("", "terminal-muted", None))
        items.append((group.display, "terminal-muted", None))
        for line in group.lines:
            cls = terminal_class(line, group.returncode)
            background = terminal_background(line, group.returncode)
            items.append((line, cls, background))
    return items


def terminal_class(line: str, returncode: int) -> str:
    if returncode == 0 and ("passed" in line or "[100%]" in line):
        return "terminal-good"
    if line.startswith("FAIL") or "failure" in line or "directory requires" in line:
        return "terminal-error"
    if line.startswith("OK"):
        return "terminal-good"
    return "terminal-text"


def terminal_background(line: str, returncode: int) -> str | None:
    if returncode == 0 and "passed" in line:
        return "term-ok-line"
    if line.startswith("FAIL") or "directory requires" in line:
        return "term-error-line"
    return None


def diff_class(line: str) -> str:
    if line.startswith("+") and not line.startswith("+++"):
        return "code-add"
    if line.startswith("-") and not line.startswith("---"):
        return "code-remove"
    if line.startswith("diff ") or line.startswith("index ") or line.startswith("@@"):
        return "code-meta"
    if line.startswith("---") or line.startswith("+++"):
        return "code-meta"
    return "code-context"


def escape(value: str) -> str:
    return html.escape(value, quote=False)


if __name__ == "__main__":
    raise SystemExit(main())
