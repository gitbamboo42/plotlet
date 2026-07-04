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
from .draw import coord, rect


_SVG_NS = "{http://www.w3.org/2000/svg}"

_PALETTE = ["#1f77b4", "#ff7f0e", "#d62728", "#2ca02c", "#9467bd", "#8c564b"]

_HATCH_DEF = (
    '<defs><pattern id="plotlet-gap-hatch" patternUnits="userSpaceOnUse"'
    ' width="6" height="6" patternTransform="rotate(45)">'
    '<rect width="6" height="6" fill="#666" fill-opacity="0.06"/>'
    '<line x1="0" y1="0" x2="0" y2="6" stroke="#666"'
    ' stroke-opacity="0.45" stroke-width="1"/></pattern></defs>'
)

# Per-name stroke colors for the chrome-regions overlay mode. Greys and
# muted hues — outlines should help the eye trace each chrome element
# without competing with the underlying chart's own data colors.
_REGIONS_PALETTE = {
    "panel":         "#d00",
    "spine":         "#999",
    "title":         "#070",
    "xlabel":        "#070",
    "ylabel":        "#070",
    "tick-x":        "#06c",
    "tick-y":        "#06c",
    # Legend sub-tags echo their chrome counterparts: marks
    # (swatch + colorbar) are the data identifier, text (entry labels +
    # colorbar ticks) is text on data, headers are sub-titles.
    "legend-mark":   "#d00",  # swatch / colorbar — same as panel
    "legend-text":   "#06c",  # entry labels + colorbar ticks — same as tick labels
    "legend-header": "#070",  # group title — same as chart title
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def layout_diagram(chart: Chart) -> Chart:
    """Visualize plotlet's layout decisions for `chart` as a Chart leaf
    that composes with the original via `|`, `/`, `pt.grid`, etc.

    Shows: panel bboxes (dashed), data areas (solid, sized to scale so
    the colored ring between them encodes margin proportions), gaps
    between adjacent panels (hatched slabs), standalone-legend leaves
    (dashed border, no data-area fill), and each chrome bbox (panel,
    spines, title, axis labels, ticks, legend sub-elements) overlaid
    as a translucent shape — rotated tick labels render as their
    precise rotated rectangle, not the loose AABB hull.

    Built by re-parsing the chart's inner (no-outer-margin) SVG for
    the abstract layout (panel + data-area + legend-leaf bboxes from
    `data-plotlet-*` attrs) and the regions sink for the chrome
    overlay layer.

    Caveat: the diagram is a *snapshot* of `chart`'s layout at call time.
    Composition preserves the body-first leaf's layout, so the snapshot
    stays accurate."""
    # Use the inner (no-outer-margin) render so the diagram leaf's
    # natural size matches what `chart` will be in a sibling layout —
    # `to_svg()` would include the figure-level outer_margin that only
    # the public root render adds, and that 8-px-each-axis padding
    # would force `chart` to grow when re-composed via `|` or `grid`.
    chart._require_render_root()
    from . import _regions
    root = chart._render_root()
    with _regions.collecting() as sink:
        src_svg = root._to_svg_unchecked()
    regions_data = [{"kind": r.kind, "bbox": r.bbox, "name": r.name,
                     "meta": r.meta} for r in sink.regions]
    W, H = _figure_size(src_svg)
    inner = _render_diagram_inner(src_svg, W, H, regions_data)

    leaf = Chart._new_sized_leaf(
        canvas_width=W, canvas_height=H,
        leaf_kind="diagram",
        margin={"left": 0, "right": 0, "top": 0, "bottom": 0},
    )
    leaf._diagram_inner = inner
    return leaf


# ---------------------------------------------------------------------------
# SVG construction
# ---------------------------------------------------------------------------

def _render_diagram_inner(src_svg: str, W: int, H: int,
                          regions_data: list[dict] | None = None) -> str:
    """Build the diagram body — everything that goes between the outer
    `<svg>` tags. Wrapped in a `<g font-family="sans-serif">` so the
    debug font carries through whether the inner is embedded inside a
    layout's outer plotlet `<svg>` (which sets DejaVu Sans on its root)
    or wrapped in a fresh standalone `<svg>`.

    `regions_data`, when supplied, overlays each chrome bbox as a
    translucent shape (`polygon` for rotated text, `rect` otherwise).
    Bboxes arrive in outer-SVG coords from `chart.regions()`, so
    single- and multi-panel layouts both work without per-panel
    bookkeeping here."""
    root = ET.fromstring(src_svg)
    panels = _parse_panels(root)
    legend_leaves = _parse_legend_leaves(root)
    # Legend leaves participate in gap detection alongside data panels —
    # the space between a data panel and a sibling legend leaf is a real
    # layout gap worth showing in the diagram.
    gaps = _find_gaps([p["bbox"] for p in panels] + list(legend_leaves))

    parts = [
        '<g font-family="sans-serif">',
        rect(0, 0, W, H, fill="#fafafa"),
        _HATCH_DEF,
        rect(0, 0, W, H, stroke="#bbb", stroke_width=0.5, dash="2,2"),
    ]
    for _axis, gx, gy, gw, gh in gaps:
        parts.append(_render_gap(gx, gy, gw, gh))
    show_overlays = bool(regions_data)
    for i, p in enumerate(panels):
        parts.append(_render_panel(p, _PALETTE[i % len(_PALETTE)],
                                   hide_margin_numbers=show_overlays))
    # Legend leaves render as a panel-without-data-region: same dashed
    # colored border as data panels (cycled palette color picks up where
    # the panel loop left off), no inner data-area fill since a legend
    # has no data axis to anchor.
    for j, (lx, ly, lw, lh) in enumerate(legend_leaves):
        col = _PALETTE[(len(panels) + j) % len(_PALETTE)]
        parts.append(rect(lx, ly, lw, lh, stroke=col,
                          stroke_width=1.2, dash="5,3"))

    if show_overlays:
        # Region bboxes are already in outer-SVG coords thanks to the
        # `_regions.translate(...)` wrappers in the rendering pipeline,
        # so single- and multi-panel layouts both work without per-panel
        # bookkeeping here. Translucent fills (not strokes) so overlapping
        # chrome reads as a darker blend rather than a tangle of outlines.
        # When a region ships a `polygon` (rotated text), render the
        # actual rotated rectangle rather than its axis-aligned hull —
        # the hull overcounts area badly for 45° labels.
        for r in regions_data:
            col = _REGIONS_PALETTE.get(r["name"], "#888")
            poly = r["meta"].get("polygon")
            if poly:
                pts = " ".join(f"{coord(px)},{coord(py)}" for px, py in poly)
                parts.append(
                    f'<polygon points="{pts}" '
                    f'fill="{col}" fill-opacity="0.3"/>'
                )
            else:
                x, y, w, h = r["bbox"]
                parts.append(
                    f'<rect x="{coord(x)}" y="{coord(y)}" '
                    f'width="{coord(w)}" height="{coord(h)}" '
                    f'fill="{col}" fill-opacity="0.3"/>'
                )
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


def _parse_legend_leaves(root: ET.Element) -> list[tuple]:
    """Return each standalone legend leaf's bbox `(x, y, w, h)`. The
    layout engine annotates the leaf's wrapper `<g>` with
    `data-plotlet-kind="legend"` + `data-plotlet-legend-bbox`."""
    out = []
    for g in root.iter(f"{_SVG_NS}g"):
        if g.get("data-plotlet-kind") != "legend":
            continue
        bbox = g.get("data-plotlet-legend-bbox")
        if bbox is None:
            continue
        out.append(tuple(int(v) for v in bbox.split(",")))
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


def _render_panel(p: dict, col: str, *, hide_margin_numbers: bool = False) -> str:
    px, py, pw, ph = p["bbox"]
    ml, mt, iw, ih = p["area"]
    m = p["margin"]
    cx, cy = px + ml + iw / 2, py + mt + ih / 2
    parts = [
        rect(px, py, pw, ph, fill=col, stroke=col,
             stroke_width=1.2, dash="5,3", fill_alpha=0.12),
        rect(px + ml, py + mt, iw, ih, fill=col, stroke=col,
             stroke_width=0.6, fill_alpha=0.38, stroke_alpha=0.6),
    ]
    # The four margin-size labels live outside the data region and
    # collide with the chrome-region overlays when those are present;
    # skip them in that case. When no chrome data is available (no
    # regions to overlay), keep them — they're useful context for the
    # abstract layout view.
    if not hide_margin_numbers:
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


def _render_gap(gx: float, gy: float, gw: float, gh: float) -> str:
    return rect(gx, gy, gw, gh,
                fill="url(#plotlet-gap-hatch)",
                stroke="#666", stroke_width=0.5,
                stroke_alpha=0.5, dash="2,2")


def _txt(x: float, y: float, s, *, anchor: str = "middle", size: int = 10,
         fill: str = "#444", weight: str | None = None,
         rotate: float | None = None) -> str:
    extra = ""
    if weight:
        extra += f' font-weight="{weight}"'
    if rotate is not None:
        extra += f' transform="rotate({rotate} {x} {y})"'
    return (f'<text x="{coord(x)}" y="{coord(y)}" text-anchor="{anchor}" '
            f'font-size="{size}" fill="{fill}"{extra}>'
            f'{_html.escape(str(s))}</text>')
