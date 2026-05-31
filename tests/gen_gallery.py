"""Emit `tests/baseline_images/<set>/index.html` showing every committed
baseline SVG side-by-side. Useful for visually reviewing what a baseline
update changes.

    python tests/gen_gallery.py chart
    python tests/gen_gallery.py all      # write galleries for every set

The SVGs are written at honest pixel sizes so multi-panel layouts can
grow with their content. For the gallery view only, each SVG is scaled
down to a uniform thumbnail width via CSS — the underlying baseline
file is untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE_ROOT = HERE / "baseline_images"


def write_gallery(set_name: str) -> None:
    baseline_dir = BASELINE_ROOT / set_name
    if not baseline_dir.is_dir():
        print(f"no baseline dir for {set_name!r} — skipping")
        return
    svg_files = sorted(p for p in baseline_dir.iterdir() if p.suffix == ".svg")
    sections = []
    for svg_path in svg_files:
        sections.append(
            f"<section><h3>{svg_path.stem}</h3>{svg_path.read_text()}</section>"
        )
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
    print(f"wrote {out.relative_to(HERE.parent)} ({len(svg_files)} svgs)")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python tests/gen_gallery.py <set> | all")
        return 1
    target = sys.argv[1]
    if target == "all":
        for d in sorted(BASELINE_ROOT.iterdir()):
            if d.is_dir():
                write_gallery(d.name)
    else:
        write_gallery(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
