<!-- @tear: 3 -->

# Tears README Demo Asset

This directory is a self-contained uv project for regenerating the launch/demo
image. The fake repos live in `fixtures/`; the renderer copies them into
`.work/`, commits a baseline, applies and stages the unsafe policy edit, runs
their pytest suites, runs the real local `tears-cli` hook and scanner for the
protected case, and renders real `git diff --cached`, pytest, and `tears`
output into `out/tears-readme-demo.svg`.

```sh
uv run --project assets/readme-demo python assets/readme-demo/render.py
```

If `rsvg-convert` is installed, the same command also writes
`out/tears-readme-demo.png`.
