"""Build cookbook/index.html — a single-page visual gallery of every recipe.

For each `cookbook/<name>/<name>.py`:
  - read SUMMARY from the source (no import, no execution)
  - run the recipe if `<name>.svg` is missing or stale
  - embed the SVG inline in a card on the gallery page

Run:  python cookbook/_gallery.py
"""
from __future__ import annotations

import ast
import html
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _summary(py_path: Path) -> str:
    """Read SUMMARY = '...' from the file without executing it."""
    tree = ast.parse(py_path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SUMMARY":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    return ""


def _ensure_svg(svg_path: Path, py_path: Path) -> bool:
    """Run the recipe if needed. Returns True if SVG is present."""
    if svg_path.exists() and svg_path.stat().st_mtime >= py_path.stat().st_mtime:
        return True
    print(f"  running {py_path.name}")
    r = subprocess.run([sys.executable, str(py_path)], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ! {py_path.name} failed:\n{r.stderr.strip()}")
        return False
    return svg_path.exists()


def _inline_svg(svg_path: Path) -> str:
    """Return SVG markup with width/height stripped so it scales to its
    container (viewBox preserved)."""
    s = svg_path.read_text()
    # Strip explicit width/height on the root <svg> so CSS controls sizing.
    s = re.sub(r'<svg([^>]*?)\swidth="[^"]+"', r'<svg\1', s, count=1)
    s = re.sub(r'<svg([^>]*?)\sheight="[^"]+"', r'<svg\1', s, count=1)
    return s


CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 24px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  color: #222;
  background: #fafafa;
}
h1 { margin: 0 0 8px; font-size: 28px; font-weight: 600; }
p.lead { margin: 0 0 28px; color: #666; max-width: 760px; line-height: 1.5; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 20px;
}
.card {
  background: white;
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  overflow: hidden;
  display: flex; flex-direction: column;
}
.card h2 {
  margin: 0; padding: 12px 16px 4px;
  font-size: 15px; font-weight: 600; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.card p {
  margin: 0; padding: 0 16px 12px;
  font-size: 13px; color: #555; line-height: 1.45;
  flex-grow: 1;
}
.card .svgwrap {
  background: #fff; padding: 8px; border-top: 1px solid #f0f0f0;
}
.card svg { width: 100%; height: auto; max-height: 280px; display: block; }
.card a {
  display: block; padding: 8px 16px; font-size: 12px;
  color: #555; text-decoration: none;
  border-top: 1px solid #f0f0f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.card a:hover { background: #f7f7f7; color: #000; }
.section { margin: 32px 0 12px; font-size: 12px; font-weight: 600;
           text-transform: uppercase; letter-spacing: 0.06em; color: #888; }
"""


# Only multi-component showcase recipes live here. Basic single-file demos
# live in ../examples/ and have their own gallery script.
SECTIONS = [
    ("Projects", ["dendrogram_heatmap", "omics_heatmap", "genomic_tracks"]),
]


def main():
    cards_by_section: dict[str, list[str]] = {}
    listed = set()
    for section, names in SECTIONS:
        cards = []
        for name in names:
            py = HERE / name / f"{name}.py"
            svg = py.with_suffix(".svg")
            if not py.exists():
                print(f"  missing {py}")
                continue
            if not _ensure_svg(svg, py):
                continue
            summary = _summary(py)
            svg_inline = _inline_svg(svg)
            cards.append(
                f'<div class="card">'
                f'<h2>c.{html.escape(name)}</h2>'
                f'<p>{html.escape(summary)}</p>'
                f'<div class="svgwrap">{svg_inline}</div>'
                f'<a href="{name}/{name}.py">view source →</a>'
                f'</div>'
            )
            listed.add(name)
        if cards:
            cards_by_section[section] = cards
    # Pick up any recipes that aren't in the section index.
    extras = []
    for d in sorted(HERE.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name in listed:
            continue
        py = d / f"{d.name}.py"
        if not py.exists():
            continue
        svg = py.with_suffix(".svg")
        if not _ensure_svg(svg, py):
            continue
        extras.append(
            f'<div class="card"><h2>c.{html.escape(d.name)}</h2>'
            f'<p>{html.escape(_summary(py))}</p>'
            f'<div class="svgwrap">{_inline_svg(svg)}</div>'
            f'<a href="{d.name}/{d.name}.py">view source →</a></div>'
        )
    if extras:
        cards_by_section["Other"] = extras

    body = []
    for section, cards in cards_by_section.items():
        body.append(f'<div class="section">{html.escape(section)}</div>')
        body.append('<div class="grid">' + "".join(cards) + '</div>')

    out_path = HERE / "index.html"
    out_path.write_text(
        f'<!doctype html><meta charset="utf-8"><title>plotlet cookbook</title>'
        f'<style>{CSS}</style>'
        f'<h1>plotlet cookbook</h1>'
        f'<p class="lead">Multi-component, domain-specific showcases — annotated '
        f'heatmaps, genome browser tracks, and similar worked examples that '
        f'compose custom artists with plotlet&rsquo;s layout algebra. '
        f'For single-file demos of standard plot types, see the '
        f'<a href="../examples/index.html">examples</a>.</p>'
        + "".join(body)
    )
    print(f"\nwrote {out_path}")
    print(f"  {len(listed) + len(extras)} recipes")


if __name__ == "__main__":
    main()
