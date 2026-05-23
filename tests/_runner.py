"""Shared CLI runner for `tests/test_*.py` baseline-image suites.

Each `test_<set>.py` defines plot functions and a `PLOTS` dict, then calls
`_runner.run("<set>", PLOTS)`. Baselines live at
`tests/baseline_images/<set>/<name>.svg`.

Flags (read from `sys.argv`):
    --update    regenerate baseline files (review the diff before committing)
    --gallery   write `baseline_images/<set>/index.html` for visual review
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE_ROOT = HERE / "baseline_images"

# `data-plotlet-version` changes every release by definition — it's the SVG
# equivalent of a build timestamp. Strip it before comparing so a version
# bump alone doesn't invalidate every committed baseline. All other
# `data-plotlet-*` attrs describe the plot itself and stay in the compare.
_VOLATILE_ATTR_RE = re.compile(r' data-plotlet-version="[^"]*"')

def _normalize(svg: str) -> str:
    return _VOLATILE_ATTR_RE.sub("", svg)


def _write_gallery(set_name: str, plots: dict, baseline_dir: Path) -> None:
    sections = []
    for name in sorted(plots):
        svg_path = baseline_dir / f"{name}.svg"
        svg = svg_path.read_text() if svg_path.exists() else "<em>missing</em>"
        sections.append(f"<section><h3>{name}</h3>{svg}</section>")
    # The SVGs are written at honest pixel sizes so multi-panel layouts can
    # grow with their content (component-first composition). For the gallery
    # view only, scale each SVG down to a uniform thumbnail width while
    # preserving aspect ratio — the underlying baseline file is untouched.
    html = (
        "<!doctype html><meta charset=utf-8>"
        f"<title>plotlet baselines — {set_name}</title>"
        "<style>body{font-family:sans-serif;margin:24px;}"
        "section{display:inline-block;margin:8px 16px 24px 0;vertical-align:top;}"
        "section svg{max-width:520px;width:auto;height:auto;}"
        "h3{margin:0 0 4px 0;font-size:13px;color:#444}</style>"
        f"<h1>plotlet — baseline gallery ({set_name})</h1>"
        + "".join(sections)
    )
    out = baseline_dir / "index.html"
    out.write_text(html)
    print(f"wrote {out.relative_to(HERE.parent)}")


def run(set_name: str, plots: dict) -> int:
    update  = "--update"  in sys.argv
    gallery = "--gallery" in sys.argv

    baseline_dir = BASELINE_ROOT / set_name
    baseline_dir.mkdir(parents=True, exist_ok=True)
    failed = 0

    for name, fn in plots.items():
        target = baseline_dir / f"{name}.svg"
        label  = f"{set_name}/{name}.svg"
        actual = fn().to_svg()

        if update:
            # Skip rewrites that would only flip the volatile attrs —
            # avoids a "diff every baseline" cascade on a bare version
            # bump. New files still get written.
            if target.exists() and _normalize(target.read_text()) == _normalize(actual):
                print(f"SKIP   {label} (unchanged under normalize)")
                continue
            target.write_text(actual)
            print(f"WROTE  {label} ({len(actual)} chars)")
            continue

        if not target.exists():
            print(f"MISS   {label} — run with --update to create")
            failed += 1
            continue

        expected = target.read_text()
        if _normalize(actual) == _normalize(expected):
            print(f"OK     {label}")
        else:
            failed += 1
            actual_path = target.with_suffix(".actual.svg")
            actual_path.write_text(actual)
            print(f"FAIL   {label}  (wrote {actual_path.name})")
            diff = list(difflib.unified_diff(
                _normalize(expected).splitlines(), _normalize(actual).splitlines(),
                fromfile="baseline", tofile="actual", lineterm="", n=1))
            for line in diff[:12]:
                print("    " + line)
            if len(diff) > 12:
                print(f"    ... and {len(diff) - 12} more diff lines")

    if gallery:
        _write_gallery(set_name, plots, baseline_dir)

    if failed:
        print(f"\n{failed} of {len(plots)} {set_name} baseline tests FAILED")
        return 1
    print(f"\n{len(plots)} of {len(plots)} {set_name} baseline tests passed")
    return 0
