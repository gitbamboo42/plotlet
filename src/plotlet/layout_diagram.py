"""`pt.layout_diagram` — a debug visualizer for plotlet's layout
decisions. Pure SVG introspection consumer of the `data-plotlet-*`
schema (see docs/AI_ATTRS.md).

This module lives separately from core / layout because it's a *consumer*
of plotlet's output, not part of the rendering pipeline: every layout
decision is recovered from the public schema, no private internals are
imported. That makes `layout_diagram` doubly useful — it's a debug tool
*and* a worked example of the schema's stable surface for users
building their own consumers.

`pt.layout_diagram(c)` returns a `Chart` leaf with `_leaf_kind="diagram"`
that participates in plotlet's composition algebra: `c | pt.layout_diagram(c)`,
`pt.grid([[c, pt.layout_diagram(c)], ...])`, and any other Chart-shaped
combination work the same way they would with a normal data leaf.
"""
from __future__ import annotations

import html as _html
import xml.etree.ElementTree as ET

from .chart import Chart


_SVG_NS = "{http://www.w3.org/2000/svg}"

_PALETTE = ["#1f77b4", "#ff7f0e", "#d62728", "#2ca02c", "#9467bd", "#8c564b"]

_HATCH_DEF = (
    '<defs><pattern id="plotlet-gap-hatch" patternUnits="userSpaceOnUse"'
    ' width="6" height="6" patternTransform="rotate(45)">'
    '<rect width="6" height="6" fill="#666" fill-opacity="0.06"/>'
    '<line x1="0" y1="0" x2="0" y2="6" stroke="#666"'
    ' stroke-opacity="0.45" stroke-width="1"/></pattern></defs>'
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def layout_diagram(chart: Chart) -> Chart:
    """Visualize plotlet's layout decisions for `chart` as a Chart leaf
    that composes with the original via `|`, `/`, `pt.grid`, etc. The
    diagram visualizes panel bboxes (dashed), data areas (solid, sized
    to scale so the colored ring between them encodes margin
    proportions), and gaps between adjacent panels (hatched slabs
    labeled with pixel size).

    Built by re-parsing `chart.to_svg()` and reading the panel `<g>`'s
    public `data-plotlet-*` attrs — nothing private is touched.

    Caveat: the diagram is a *snapshot* of `chart`'s layout at call time.
    For body-first leaves (the 0.2.0+ default) and the no-margin diagram
    sibling produced here, composition preserves `chart`'s layout, so
    the snapshot stays accurate. Canvas-first legacy leaves under
    explicit width-constrained parents can rescale during composition;
    in that rare case the diagram may slightly drift from how `chart`
    ends up rendered."""
    src_svg = chart.to_svg()
    W, H = _figure_size(src_svg)
    inner = _render_diagram_inner(src_svg, W, H)

    leaf = Chart(canvas_width=W, canvas_height=H,
                 margin={"left": 0, "right": 0, "top": 0, "bottom": 0})
    leaf._leaf_kind = "diagram"
    leaf._diagram_inner = inner
    return leaf


def _render_standalone_diagram(leaf: Chart) -> str:
    """Wrap a diagram leaf's inner content in a fresh `<svg>`. Called by
    `Chart.to_svg()` when the diagram leaf is rendered on its own (not
    as part of a composition)."""
    W = leaf._fig._canvas_width
    H = leaf._fig._canvas_height
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">{leaf._diagram_inner}</svg>'
    )


# ---------------------------------------------------------------------------
# SVG construction
# ---------------------------------------------------------------------------

def _render_diagram_inner(src_svg: str, W: int, H: int) -> str:
    """Build the diagram body — everything that goes between the outer
    `<svg>` tags. Wrapped in a `<g font-family="sans-serif">` so the
    debug font carries through whether the inner is embedded inside a
    layout's outer plotlet `<svg>` (which sets DejaVu Sans on its root)
    or wrapped in a fresh standalone `<svg>`."""
    root = ET.fromstring(src_svg)
    panels = _parse_panels(root)
    gaps = _find_gaps([p["bbox"] for p in panels])

    parts = [
        '<g font-family="sans-serif">',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fafafa"/>',
        _HATCH_DEF,
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="none" '
        f'stroke="#bbb" stroke-width="0.5" stroke-dasharray="2,2"/>',
    ]
    for axis, gx, gy, gw, gh in gaps:
        parts.append(_render_gap(axis, gx, gy, gw, gh))
    for i, p in enumerate(panels):
        parts.append(_render_panel(p, _PALETTE[i % len(_PALETTE)]))
    parts.append('</g>')
    return "".join(parts)


def _figure_size(svg: str) -> tuple[int, int]:
    root = ET.fromstring(svg)
    return int(root.get("width")), int(root.get("height"))


def _parse_panels(root: ET.Element) -> list[dict]:
    out = []
    for g in root.iter(f"{_SVG_NS}g"):
        if g.get("data-plotlet-kind") != "panel":
            continue
        bbox = g.get("data-plotlet-panel-bbox")
        area = g.get("data-plotlet-data-area")
        if bbox is None or area is None:
            continue
        px, py, pw, ph = (int(v) for v in bbox.split(","))
        ml, mt, iw, ih = (int(v) for v in area.split(","))
        out.append({
            "bbox":   (px, py, pw, ph),
            "area":   (ml, mt, iw, ih),
            "margin": {"left": ml, "top": mt,
                       "right":  pw - ml - iw,
                       "bottom": ph - mt - ih},
            "title":  g.get("data-plotlet-title", ""),
            "xscale": g.get("data-plotlet-xscale", "?"),
            "yscale": g.get("data-plotlet-yscale", "?"),
            "xlim":   g.get("data-plotlet-xlim", "(category)"),
            "ylim":   g.get("data-plotlet-ylim", "(category)"),
        })
    return out


def _find_gaps(bboxes: list[tuple]) -> list[tuple]:
    """Pairwise scan: for every (a, b) where a is to the left of (or above)
    b with overlapping orthogonal extent and no other bbox in between,
    record the gap. Joined share-pair joints (gap=0) are filtered out."""
    gaps = []
    for i, (ax, ay, aw, ah) in enumerate(bboxes):
        for j, (bx, by, bw, bh) in enumerate(bboxes):
            if i == j:
                continue
            y_lo, y_hi = max(ay, by), min(ay + ah, by + bh)
            if ax + aw <= bx and y_lo < y_hi:
                gap = bx - (ax + aw)
                if gap > 0 and not _blocked(i, j, ax + aw, bx, y_lo, y_hi, bboxes):
                    gaps.append(("h", ax + aw, y_lo, gap, y_hi - y_lo))
            x_lo, x_hi = max(ax, bx), min(ax + aw, bx + bw)
            if ay + ah <= by and x_lo < x_hi:
                gap = by - (ay + ah)
                if gap > 0 and not _blocked(i, j, x_lo, x_hi, ay + ah, by, bboxes):
                    gaps.append(("v", x_lo, ay + ah, x_hi - x_lo, gap))
    return gaps


def _blocked(i: int, j: int,
             x_lo: float, x_hi: float, y_lo: float, y_hi: float,
             bboxes: list[tuple]) -> bool:
    return any(
        k != i and k != j
        and cx + cw > x_lo and cx < x_hi
        and cy < y_hi and cy + ch > y_lo
        for k, (cx, cy, cw, ch) in enumerate(bboxes)
    )


def _render_panel(p: dict, col: str) -> str:
    px, py, pw, ph = p["bbox"]
    ml, mt, iw, ih = p["area"]
    m = p["margin"]
    cx, cy = px + ml + iw / 2, py + mt + ih / 2
    parts = [
        f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" '
        f'fill="{col}" fill-opacity="0.12" stroke="{col}" '
        f'stroke-width="1.2" stroke-dasharray="5,3"/>',
        f'<rect x="{px+ml}" y="{py+mt}" width="{iw}" height="{ih}" '
        f'fill="{col}" fill-opacity="0.38" stroke="{col}" '
        f'stroke-width="0.6" stroke-opacity="0.6"/>',
    ]
    if mt >= 12:
        parts.append(_txt(px + pw / 2, py + mt / 2 + 3, m["top"]))
    if m["bottom"] >= 12:
        parts.append(_txt(px + pw / 2, py + ph - m["bottom"] / 2 + 3, m["bottom"]))
    if ml >= 12:
        parts.append(_txt(px + ml / 2, cy, m["left"], rotate=-90))
    if m["right"] >= 12:
        parts.append(_txt(px + pw - m["right"] / 2, cy, m["right"], rotate=-90))
    if iw >= 50 and ih >= 30:
        parts.append(_txt(cx, cy - 4, f"{iw} × {ih}",
                          size=12, fill="#222", weight="bold"))
    if iw >= 70 and ih >= 50:
        parts.append(_txt(cx, cy + 12,
                          f'"{p["title"] or "(no title)"}"', size=9, fill="#555"))
        parts.append(_txt(cx, cy + 25,
                          f'x: {p["xscale"]} {p["xlim"]}', size=8, fill="#666"))
        parts.append(_txt(cx, cy + 36,
                          f'y: {p["yscale"]} {p["ylim"]}', size=8, fill="#666"))
    return "".join(parts)


def _render_gap(axis: str, gx: float, gy: float, gw: float, gh: float) -> str:
    rect = (
        f'<rect x="{gx}" y="{gy}" width="{gw}" height="{gh}" '
        f'fill="url(#plotlet-gap-hatch)" stroke="#666" stroke-opacity="0.5" '
        f'stroke-width="0.5" stroke-dasharray="2,2"/>'
    )
    size = gw if axis == "h" else gh
    cx, cy = gx + gw / 2, gy + gh / 2
    if axis == "h":
        label = _txt(cx, cy, f"gap {int(size)}", size=9, fill="#333", rotate=-90)
    else:
        label = _txt(cx, cy + 3, f"gap {int(size)}", size=9, fill="#333")
    return rect + label


def _txt(x: float, y: float, s, *, anchor: str = "middle", size: int = 10,
         fill: str = "#444", weight: str | None = None,
         rotate: float | None = None) -> str:
    extra = ""
    if weight:
        extra += f' font-weight="{weight}"'
    if rotate is not None:
        extra += f' transform="rotate({rotate} {x} {y})"'
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-size="{size}" fill="{fill}"{extra}>'
            f'{_html.escape(str(s))}</text>')
