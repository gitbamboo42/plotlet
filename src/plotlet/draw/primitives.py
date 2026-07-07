"""SVG primitive emitters — the core draw verbs.

These functions emit SVG fragments at *pixel* coordinates. Import them
via `plotlet.draw` (the package `__init__` re-exports everything here).
Combine fragments with `"".join(...)` and return the result from your
`draw=` callback.

`rect`, `circle`, `path`, and `polygon` accept optional `fill_alpha` /
`stroke_alpha` for per-channel opacity (translucent fill, opaque outline
or vice versa); leave them `None` and `alpha=` applies to the whole element.

For chart-recording counterparts in data coordinates, use `Chart` methods
directly — `c.scatter(xs, ys)`, `c.text(x, y, s)`, etc.
"""
from __future__ import annotations

import math

from .._spec import _D, _DASH

# Pre-computed unit-radius vertices of a 5-point star (outer radius = 1,
# inner radius = 0.382 ≈ 1/φ², the classic plotting look). Listed
# alternating outer/inner starting from the top tip and walking CW.
_STAR5_VERTICES = [
    (math.cos(-math.pi / 2 + i * math.pi / 5) * (1.0 if i % 2 == 0 else 0.382),
     math.sin(-math.pi / 2 + i * math.pi / 5) * (1.0 if i % 2 == 0 else 0.382))
    for i in range(10)
]

# Pre-computed unit-radius vertices of a vertex-up hexagon (top vertex
# pointing up, walking CW). Used by the `"h"` marker glyph.
_HEX_VERTICES = [
    (math.cos(-math.pi / 2 + i * math.pi / 3),
     math.sin(-math.pi / 2 + i * math.pi / 3))
    for i in range(6)
]
from .font import (measure_text, _glyph_path_d, _decoration_y_offset,
                   cap_height, descender, line_height)
from .linestyles import resolve_linestyle
from .._regions import record as _record_region
from .format import coord, degree, opacity, stroke_w



# Per-edge subdivision count when a coord-native artist passes `project=`.
# Each Cartesian edge gets split into this many sub-segments before each
# sample is projected; the resulting polyline approximates the warped curve.
# 20 keeps a 100-px chord smooth on a typical ring without blowing up the
# emitted polyline. Future: per-coord override (CircularCoordinate could
# request more samples on long arcs).
_COORD_NATIVE_SUBDIV = 20


def _subdivide_project(points, project, n: int = _COORD_NATIVE_SUBDIV):
    """Sample n+1 points along each edge of `points` and project each
    through `project(x_px, y_px) -> (px, py)`. Endpoints are projected
    exactly; intermediate samples are linear interpolations in Cartesian
    space (so a straight Cartesian edge becomes a curve under non-affine
    coords). Returns the projected point list, suitable for polyline /
    polygon emission."""
    if not points:
        return []
    out = [project(*points[0])]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        for i in range(1, n + 1):
            f = i / n
            out.append(project(x0 + f * (x1 - x0), y0 + f * (y1 - y0)))
    return out


def text_path(s: str, x: float, y: float, size: float,
              anchor: str = "start", color: str = "#000",
              fontstyle: str = "normal",
              decoration: str = "none",
              rotate: float = 0,
              tag: str | None = None) -> str:
    """Render `s` as a single SVG <path> with its baseline at pixel (x, y).

    `anchor` matches SVG's text-anchor: 'start' | 'middle' | 'end'. Use this
    inside a custom artist's `draw` callback to emit text-as-paths so output
    stays font-independent across machines.

    Multi-line text: `\\n` starts a new line one `line_height(size)` below
    the previous one; (x, y) stays the FIRST line's baseline and each line
    is anchored independently (so `anchor="middle"` centers every line).

    `fontstyle="italic"` synthesizes an oblique slant via a -12° skew
    during glyph composition (the bundled DejaVu Sans ships no real
    italic face).

    `decoration="underline" | "overline" | "line-through"` appends a stroke
    line at the conventional offset for that decoration.

    `rotate=` (degrees, positive = CCW) rotates the glyph (and any
    decoration line) around the anchor point (x, y). Convention matches
    `xticks(rotation=...)` and the rest of the lib; SVG's native
    positive-CW is negated at emission so callers think in screen CCW.
    """
    d = _glyph_path_d(s, x, y, size, anchor=anchor, fontstyle=fontstyle)
    if not d:
        return ""
    # Anchor mapping from a line's width to its left edge — shared by the
    # bbox rect (block-widest line) and the per-line decoration strokes,
    # so the two can't drift apart.
    def _anchor_left(width: float) -> float:
        if anchor == "middle":
            return x - width / 2
        if anchor == "end":
            return x - width
        return x

    lines = s.split("\n")
    if tag is not None:
        # Region capture. First-line baseline at y maps to cap_height
        # above; the block extends descender below the LAST line's
        # baseline. Width is the widest line's. When `rotate` is set,
        # the SVG transform rotates the glyph around (x, y), so the
        # recorded bbox is the axis-aligned hull of the four rotated
        # corners — and the precise rotated rectangle's 4 corners go in
        # meta as `polygon` so overlap detection can use SAT
        # (axis-aligned hulls of 45°-rotated rectangles overlap even
        # when the rectangles themselves don't, so AABB alone is a
        # false-positive trap).
        w = measure_text(s, size)
        rx = _anchor_left(w)
        ry = y - cap_height(size)
        rh = (cap_height(size) + descender(size)
              + (len(lines) - 1) * line_height(size))
        if rotate:
            # SVG transform uses `-rotate` (CCW in user space); same sign
            # here so the corner math matches the visible rendering.
            theta = math.radians(-rotate)
            cos_t, sin_t = math.cos(theta), math.sin(theta)
            corners = [(rx, ry), (rx + w, ry), (rx + w, ry + rh), (rx, ry + rh)]
            rotated_pts = []
            for cx, cy in corners:
                dx_, dy_ = cx - x, cy - y
                rotated_pts.append((x + dx_ * cos_t - dy_ * sin_t,
                                    y + dx_ * sin_t + dy_ * cos_t))
            xs = [p[0] for p in rotated_pts]
            ys = [p[1] for p in rotated_pts]
            rx_r, ry_r = min(xs), min(ys)
            _record_region("text",
                            (rx_r, ry_r, max(xs) - rx_r, max(ys) - ry_r),
                            name=tag, text=s, size=size, anchor=anchor,
                            rotate=rotate, polygon=rotated_pts)
        else:
            _record_region("text", (rx, ry, w, rh), name=tag,
                            text=s, size=size, anchor=anchor, rotate=0)
    out = f'<path d="{d}" fill="{color}"/>'
    if decoration != "none":
        dy = _decoration_y_offset(decoration, size)
        line_w = max(0.6, size * 0.06)
        for i, line in enumerate(lines):
            if not line:
                continue
            lw = measure_text(line, size)
            lx = _anchor_left(lw)
            ly = y + i * line_height(size) + dy
            out += (f'<line x1="{coord(lx)}" y1="{coord(ly)}" '
                    f'x2="{coord(lx + lw)}" y2="{coord(ly)}" '
                    f'stroke="{color}" stroke-width="{stroke_w(line_w)}"/>')
    if rotate:
        out = f'<g transform="rotate({degree(-rotate)} {coord(x)} {coord(y)})">{out}</g>'
    return out


def op(alpha) -> str:
    """SVG opacity attribute, omitted when fully opaque to keep output lean.

    Quantized to 2 decimals (1%) so float-noise from upstream compute (e.g.
    1 - tiny → 0.9999999999999998) doesn't make SVG byte-different across
    numpy/scipy builds. Anything finer than 1% opacity is invisible."""
    return "" if alpha == 1 else f' opacity="{opacity(alpha)}"'


def _shape_opacity(alpha, fill_alpha, stroke_alpha,
                   has_fill: bool, has_stroke: bool) -> str:
    """Resolve whole-element vs per-channel opacity for shapes that may have
    both a fill and a stroke. When neither per-channel alpha is set, emits
    the lean whole-element `opacity` (omitted at 1). When either is set,
    emits `fill-opacity` / `stroke-opacity` separately — each omitted at 1,
    and skipped entirely when the corresponding channel is absent."""
    if fill_alpha is None and stroke_alpha is None:
        return op(alpha)
    fa = fill_alpha if fill_alpha is not None else alpha
    sa = stroke_alpha if stroke_alpha is not None else alpha
    fop = f' fill-opacity="{opacity(fa)}"' if has_fill and fa != 1 else ""
    sop = f' stroke-opacity="{opacity(sa)}"' if has_stroke and sa != 1 else ""
    return fop + sop


def marker(kind: str, x: float, y: float, size: float, color: str, alpha,
           edgecolor: str | None = None, edgewidth: float | None = None,
           tag: str | None = None,
           project=None) -> str:
    """Emit a single marker glyph (one of
    `"o" "s" "^" "v" "<" ">" "x" "+" "*" "D" "h"`) at pixel `(x, y)`.
    Raises `ValueError` for unknown marker codes.

    `edgecolor=` adds an outline to filled markers (`o`/`s`/`^`/`v`/`<`/`>`/`*`/`D`/`h`).
    `edgewidth=` overrides the stroke width for ALL markers (including the
    `x`/`+` outlines, which use `color` as their stroke); falls back to
    `_D["marker_stroke_width"]`.

    `project=` (Cartesian-pixel -> coord-pixel closure) shifts the marker's
    anchor through a non-affine coord. The glyph itself is NOT warped — a
    marker is a fixed-size symbol, so it keeps its Cartesian shape and just
    lands in the right place under the ring/polar."""
    if project is not None:
        x, y = project(x, y)
    msw = edgewidth if edgewidth is not None else _D["marker_stroke_width"]
    _op = op(alpha)
    edge = f' stroke="{edgecolor}" stroke-width="{stroke_w(msw)}"' if edgecolor else ""
    if tag is not None:
        # All marker glyphs fit in a (2*size)² box centered on (x, y).
        _record_region("marker", (x - size, y - size, 2 * size, 2 * size),
                        name=tag, marker=kind, size=size)
    if kind == "o":
        return f'<circle cx="{coord(x)}" cy="{coord(y)}" r="{coord(size)}" fill="{color}"{edge}{_op}/>'
    if kind == "s":
        return (f'<rect x="{coord(x - size)}" y="{coord(y - size)}" width="{coord(2 * size)}" '
                f'height="{coord(2 * size)}" fill="{color}"{edge}{_op}/>')
    if kind == "^":
        return (f'<path d="M{coord(x)},{coord(y - size)}L{coord(x + size)},{coord(y + size)}'
                f'L{coord(x - size)},{coord(y + size)}Z" fill="{color}"{edge}{_op}/>')
    if kind == "v":
        return (f'<path d="M{coord(x)},{coord(y + size)}L{coord(x + size)},{coord(y - size)}'
                f'L{coord(x - size)},{coord(y - size)}Z" fill="{color}"{edge}{_op}/>')
    if kind == "x":
        return (f'<path d="M{coord(x - size)},{coord(y - size)}L{coord(x + size)},{coord(y + size)}'
                f'M{coord(x - size)},{coord(y + size)}L{coord(x + size)},{coord(y - size)}" '
                f'stroke="{color}" stroke-width="{stroke_w(msw)}"{_op}/>')
    if kind == "+":
        return (f'<path d="M{coord(x - size)},{coord(y)}L{coord(x + size)},{coord(y)}'
                f'M{coord(x)},{coord(y - size)}L{coord(x)},{coord(y + size)}" '
                f'stroke="{color}" stroke-width="{stroke_w(msw)}"{_op}/>')
    if kind == "*":
        d = "M" + " L".join(f"{coord(x + size*dx)},{coord(y + size*dy)}"
                            for dx, dy in _STAR5_VERTICES) + "Z"
        return f'<path d="{d}" fill="{color}"{edge}{_op}/>'
    if kind == "D":
        # Diamond: 4 vertices (top/right/bottom/left), `size` is center-to-vertex.
        return (f'<path d="M{coord(x)},{coord(y - size)}L{coord(x + size)},{coord(y)}'
                f'L{coord(x)},{coord(y + size)}L{coord(x - size)},{coord(y)}Z" '
                f'fill="{color}"{edge}{_op}/>')
    if kind == "<":
        # Triangle-left: tip at left, two corners at right.
        return (f'<path d="M{coord(x - size)},{coord(y)}L{coord(x + size)},{coord(y - size)}'
                f'L{coord(x + size)},{coord(y + size)}Z" fill="{color}"{edge}{_op}/>')
    if kind == ">":
        # Triangle-right: tip at right, two corners at left.
        return (f'<path d="M{coord(x + size)},{coord(y)}L{coord(x - size)},{coord(y - size)}'
                f'L{coord(x - size)},{coord(y + size)}Z" fill="{color}"{edge}{_op}/>')
    if kind == "h":
        # Hexagon, vertex-up orientation.
        d = "M" + " L".join(f"{coord(x + size*dx)},{coord(y + size*dy)}"
                            for dx, dy in _HEX_VERTICES) + "Z"
        return f'<path d="{d}" fill="{color}"{edge}{_op}/>'
    raise ValueError(f"unknown marker kind {kind!r}; expected one of "
                     f"'o' 's' '^' 'v' '<' '>' 'x' '+' '*' 'D' 'h'.")


def dash_attr(dash) -> str:
    if not dash:
        return ""
    d = _DASH.get(resolve_linestyle(dash), dash)
    return f' stroke-dasharray="{d}"' if d else ""


def segment(x1: float, y1: float, x2: float, y2: float, *,
            color: str = "#000", width: float = 1, dash=None, alpha=1,
            tag: str | None = None,
            project=None) -> str:
    """Emit a single SVG `<line>` segment from pixel (x1, y1) to (x2, y2).

    `dash` accepts a short code (`"--"`, `":"`, `"-."`) or a raw SVG
    dasharray string (`"6,3"`); `None` (default) is solid.

    `project=` (Cartesian-pixel -> coord-pixel closure) subdivides the
    segment and emits a polyline through the warped samples instead of a
    straight `<line>`. Region tags reflect the Cartesian footprint
    (segment intent is layout-meaningful even when the visible shape
    curves)."""
    if tag is not None:
        # Region bbox represents the segment's visible footprint, so a
        # horizontal/vertical 1-D line picks up its stroke-width
        # thickness. Otherwise a zero-thickness bbox would be invisible
        # to layout overlays and treated as "no extent" by overlap
        # checks.
        rx, ry = min(x1, x2), min(y1, y2)
        rw, rh = abs(x2 - x1), abs(y2 - y1)
        if rh < width:
            ry -= (width - rh) / 2
            rh = width
        if rw < width:
            rx -= (width - rw) / 2
            rw = width
        _record_region("segment", (rx, ry, rw, rh), name=tag, width=width)
    if project is not None:
        pts = _subdivide_project([(x1, y1), (x2, y2)], project)
        return polyline(pts, color=color, width=width, dash=dash, alpha=alpha)
    return (f'<line x1="{coord(x1)}" x2="{coord(x2)}" y1="{coord(y1)}" y2="{coord(y2)}" '
            f'stroke="{color}" stroke-width="{stroke_w(width)}"{op(alpha)}{dash_attr(dash)}/>')


def rect(x: float, y: float, w: float, h: float, *,
         fill: str = None, stroke: str = None,
         stroke_width: float = 1, alpha=1,
         fill_alpha=None, stroke_alpha=None,
         dash=None, shape_rendering: str | None = None,
         tag: str | None = None,
         project=None) -> str:
    """Emit a single SVG `<rect>` at pixel (x, y) with size (w, h).

    `fill=None` (default) draws an outline only — pass `stroke=` to add a
    border. `fill_alpha` / `stroke_alpha` override `alpha` per channel when
    you need a translucent body with an opaque outline (or vice versa); when
    both are `None`, `alpha` is applied as a single whole-element `opacity`.
    `dash` accepts a registered linestyle (`"--"`, `":"`, `"-."`) or a raw
    SVG dasharray (`"6,3"`). `shape_rendering="crispEdges"` pixel-aligns
    borders, useful for contiguous-band heatmap-style rects.

    `project=` (Cartesian-pixel -> coord-pixel closure) emits a 4-edge
    subdivided polygon instead of a `<rect>`, so heatmap cells / bars
    curve correctly under non-affine coords. `shape_rendering` is dropped
    on that path (pixel alignment is meaningless once the shape curves).
    """
    if project is not None:
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        pts = _subdivide_project(corners + [corners[0]], project)
        return polygon(pts, fill=fill, stroke=stroke,
                       stroke_width=stroke_width, alpha=alpha,
                       fill_alpha=fill_alpha, stroke_alpha=stroke_alpha)
    fa = f' fill="{fill}"' if fill else ' fill="none"'
    sa = (f' stroke="{stroke}" stroke-width="{stroke_w(stroke_width)}"{dash_attr(dash)}'
          if stroke else "")
    oa = _shape_opacity(alpha, fill_alpha, stroke_alpha,
                        has_fill=bool(fill), has_stroke=bool(stroke))
    sr = f' shape-rendering="{shape_rendering}"' if shape_rendering else ""
    if tag is not None:
        _record_region("rect", (x, y, w, h), name=tag,
                        fill=fill, stroke=stroke)
    return (f'<rect x="{coord(x)}" y="{coord(y)}" width="{coord(w)}" height="{coord(h)}"'
            f'{fa}{sa}{oa}{sr}/>')


def circle(cx: float, cy: float, r: float, *,
           fill: str = None, stroke: str = None,
           stroke_width: float = 1, alpha=1,
           fill_alpha=None, stroke_alpha=None,
           tag: str | None = None,
           project=None) -> str:
    """Emit a single SVG `<circle>` at pixel (cx, cy) with radius r.

    Pass `fill=` for a filled disc, `stroke=` for an outline, or both.
    `fill=None` (default) emits `fill="none"` so an outline-only call works.
    `fill_alpha` / `stroke_alpha` override `alpha` per channel.

    `project=` (Cartesian-pixel -> coord-pixel closure) shifts the center
    through a non-affine coord; the radius stays pixel-absolute so the
    disc keeps its physical size under the ring/polar.
    """
    if project is not None:
        cx, cy = project(cx, cy)
    fa = f' fill="{fill}"' if fill else ' fill="none"'
    sa = f' stroke="{stroke}" stroke-width="{stroke_w(stroke_width)}"' if stroke else ""
    oa = _shape_opacity(alpha, fill_alpha, stroke_alpha,
                        has_fill=bool(fill), has_stroke=bool(stroke))
    if tag is not None:
        _record_region("circle", (cx - r, cy - r, 2 * r, 2 * r),
                        name=tag, fill=fill, stroke=stroke)
    return f'<circle cx="{coord(cx)}" cy="{coord(cy)}" r="{coord(r)}"{fa}{sa}{oa}/>'


def path(d: str, *,
         fill: str = None, stroke: str = None,
         stroke_width: float = 1, dash=None, alpha=1,
         fill_alpha=None, stroke_alpha=None) -> str:
    """Emit a `<path>` for an arbitrary SVG path-data string `d`.

    Use this when `polyline` / `polygon` aren't shaped right (curves,
    holes, T-junctions). For common cases prefer those — they handle the
    point-list -> `d` translation for you. `fill_alpha` / `stroke_alpha`
    override `alpha` per channel.
    """
    fa = f' fill="{fill}"' if fill else ' fill="none"'
    sa = f' stroke="{stroke}" stroke-width="{stroke_w(stroke_width)}"{dash_attr(dash)}' if stroke else ""
    oa = _shape_opacity(alpha, fill_alpha, stroke_alpha,
                        has_fill=bool(fill), has_stroke=bool(stroke))
    return f'<path d="{d}"{fa}{sa}{oa}/>'


def polyline(points, *,
             color: str = "#000", width: float = 1, dash=None, alpha=1,
             project=None) -> str:
    """Stroke a polyline through `points` (list of `(x, y)` pixel tuples).

    Returns `""` for fewer than two points. No fill — for a closed filled
    shape, use `polygon`.

    `project=` (Cartesian-pixel -> coord-pixel closure) subdivides each
    edge before projection so straight Cartesian edges become smooth
    curves under non-affine coords.
    """
    if project is not None:
        points = _subdivide_project(list(points), project)
    if not points or len(points) < 2:
        return ""
    d = "M" + " L".join(f"{coord(x)},{coord(y)}" for x, y in points)
    return path(d, stroke=color, stroke_width=width, dash=dash, alpha=alpha)


def polygon(points, *,
            fill: str = None, stroke: str = None,
            stroke_width: float = 1, alpha=1,
            fill_alpha=None, stroke_alpha=None,
            project=None) -> str:
    """Closed polygon through `points` (list of `(x, y)` pixel tuples).

    Always emits a trailing `Z`, so the shape is closed even if the last
    point doesn't repeat the first. Pass `fill=` for a filled shape,
    `stroke=` for an outline, or both. `fill_alpha` / `stroke_alpha`
    override `alpha` per channel.

    `project=` (Cartesian-pixel -> coord-pixel closure) subdivides each
    edge — including the implicit closing edge — before projection. The
    caller can either pass the closing point explicitly (last == first)
    or let `polygon` close via the trailing `Z`; under `project=` the
    explicit form gives a smoother closing seam.
    """
    if project is not None:
        points = _subdivide_project(list(points), project)
    if not points or len(points) < 3:
        return ""
    d = "M" + " L".join(f"{coord(x)},{coord(y)}" for x, y in points) + "Z"
    return path(d, fill=fill, stroke=stroke, stroke_width=stroke_width,
                alpha=alpha, fill_alpha=fill_alpha, stroke_alpha=stroke_alpha)


def arc(x0: float, y0: float, x1: float, y1: float, *,
        height: float, **path_kwargs) -> str:
    """Half-ellipse arc from `(x0, y0)` to `(x1, y1)` in pixel coords.

    `height` is the perpendicular distance from the chord midpoint to
    the arc apex. **Positive height** curves toward smaller SVG y
    (visually "above" a horizontal chord); negative flips to the other
    side. Returns an empty string for a zero-length chord.

    Use this for chord / arc-diagram edges and other "bulge between two
    points" curves. For closed sankey-ribbon shapes, build with `polygon`
    or two `arc` calls instead. All extra kwargs forward to `path`
    (`stroke=`, `stroke_width=`, `fill=`, `alpha=`, etc.).
    """
    dx = x1 - x0
    dy = y1 - y0
    L = math.hypot(dx, dy)
    if L == 0:
        return ""
    rx = L / 2
    ry = abs(height)
    angle = math.degrees(math.atan2(dy, dx))
    # SVG sweep-flag: 0 sweeps CCW in user space (SVG y down), 1 sweeps CW.
    # For positive height = curve toward smaller y on a horizontal chord,
    # we need CCW from (x0,y0) to (x1,y1) → sweep=0.
    sweep = 0 if height > 0 else 1
    d = (f"M {coord(x0)},{coord(y0)} "
         f"A {coord(rx)},{coord(ry)} {degree(angle)} 0 {sweep} {coord(x1)},{coord(y1)}")
    return path(d, **path_kwargs)


def errorbar_v(x: float, y_lo: float, y_hi: float, *,
               capsize: float = 4, color: str = "#000",
               width: float = 1, alpha=1) -> str:
    """Vertical error bar at pixel `x` from `y_lo` to `y_hi`, with caps.

    `capsize` is the cap width in pixels; pass `0` to drop the caps.
    """
    parts = [segment(x, y_lo, x, y_hi, color=color, width=width, alpha=alpha)]
    if capsize:
        half = capsize / 2
        parts.append(segment(x - half, y_lo, x + half, y_lo,
                             color=color, width=width, alpha=alpha))
        parts.append(segment(x - half, y_hi, x + half, y_hi,
                             color=color, width=width, alpha=alpha))
    return "".join(parts)


def errorbar_h(y: float, x_lo: float, x_hi: float, *,
               capsize: float = 4, color: str = "#000",
               width: float = 1, alpha=1) -> str:
    """Horizontal error bar at pixel `y` from `x_lo` to `x_hi`, with caps.

    `capsize` is the cap height in pixels; pass `0` to drop the caps.
    """
    parts = [segment(x_lo, y, x_hi, y, color=color, width=width, alpha=alpha)]
    if capsize:
        half = capsize / 2
        parts.append(segment(x_lo, y - half, x_lo, y + half,
                             color=color, width=width, alpha=alpha))
        parts.append(segment(x_hi, y - half, x_hi, y + half,
                             color=color, width=width, alpha=alpha))
    return "".join(parts)


def split_rect(x: float, y: float, w: float, h: float,
               n: int, i: int, *,
               fill: str = None, stroke: str = None,
               stroke_width: float = 1, alpha=1,
               fill_alpha=None, stroke_alpha=None,
               padding: float = 0,
               start: float = 0.0,
               weights=None,
               symmetric: bool = False) -> str:
    """One sector of a rectangle divided into n perimeter sectors.

    Divides the rectangle by splitting its perimeter into n segments and
    connecting each to the center. Sector 0 starts at the top-left corner
    and proceeds clockwise. Useful for multi-valued cells in oncoprint /
    compound-glyph heatmaps:

        for i, color in enumerate(colors):
            out += draw.split_rect(px, py, cw, ch, len(colors), i,
                                   fill=color, padding=2)

    `padding`   — inward shrink on all four sides; creates visible gaps.
    `start`     — offset as a fraction [0, 1) of the perimeter where sector
                  0 begins. Default 0 = top-left corner.
    `weights`   — list of n positive numbers giving proportional sector sizes.
                  Default None = equal sectors.
    `symmetric` — if True (default), each edge is weighted equally so sector
                  boundaries always fall on corners for n that divides 4
                  (n=2,4,8). If False, boundaries are spaced by actual arc
                  length, which can be unequal for non-square rectangles.
    n=1 returns a plain rect. No hard cap on n.
    """
    if n < 1 or not (0 <= i < n):
        raise ValueError(
            f"split_rect: need n >= 1 and 0 <= i < n, got n={n!r}, i={i!r}"
        )
    if n == 1:
        return rect(x, y, w, h, fill=fill, stroke=stroke,
                    stroke_width=stroke_width, alpha=alpha,
                    fill_alpha=fill_alpha, stroke_alpha=stroke_alpha)
    cx, cy = x + w / 2, y + h / 2
    rx, ry = x + padding, y + padding
    rw, rh = w - 2 * padding, h - 2 * padding
    if rw <= 0 or rh <= 0:
        return ""

    if symmetric:
        # Each edge gets weight 1 regardless of actual length — P = 4.
        P = 4.0
        def _pt(t):
            t = t % P
            if t <= 1.0: return (rx + t * rw,           ry)
            t -= 1.0
            if t <= 1.0: return (rx + rw,               ry + t * rh)
            t -= 1.0
            if t <= 1.0: return (rx + rw * (1.0 - t),   ry + rh)
            t -= 1.0
            return              (rx,                     ry + rh * (1.0 - t))
        base_corners = [1.0, 2.0, 3.0]
    else:
        P = 2.0 * (rw + rh)
        def _pt(t):
            t = t % P
            if t <= rw:       return (rx + t,       ry)
            t -= rw
            if t <= rh:       return (rx + rw,      ry + t)
            t -= rh
            if t <= rw:       return (rx + rw - t,  ry + rh)
            t -= rw
            return                   (rx,            ry + rh - t)
        base_corners = [rw, rw + rh, 2 * rw + rh]

    if weights is not None:
        if len(weights) != n:
            raise ValueError(
                f"split_rect: weights must have length n={n}, got {len(weights)}"
            )
        total = sum(weights)
        if total <= 0:
            return ""
        cum = [0.0]
        for wt in weights:
            cum.append(cum[-1] + wt / total * P)
        t0_base, t1_base = cum[i], cum[i + 1]
    else:
        seg = P / n
        t0_base, t1_base = i * seg, (i + 1) * seg

    start_off = start * P
    t0, t1 = start_off + t0_base, start_off + t1_base

    # P = top-left corner in offset space; corners repeated at +P handle
    # sectors that wrap past t=0.
    corner_ts = base_corners + [P] + [tc + P for tc in base_corners]

    pts = [(cx, cy), _pt(t0)]
    for tc in corner_ts:
        if t0 < tc < t1:
            pts.append(_pt(tc))
    pts.append(_pt(t1))
    return polygon(pts, fill=fill, stroke=stroke, stroke_width=stroke_width,
                   alpha=alpha, fill_alpha=fill_alpha, stroke_alpha=stroke_alpha)


def split_pie(x: float, y: float, w: float, h: float,
              n: int, i: int, *,
              fill: str = None, stroke: str = None,
              stroke_width: float = 1, alpha=1,
              fill_alpha=None, stroke_alpha=None,
              r: float = None,
              padding: float = 0,
              start: float = 0.0,
              weights=None,
              gap: float = 0) -> str:
    """One sector of a perfect circle inscribed in the bounding box.

    Always draws a round circle regardless of the cell's aspect ratio:
    `r` defaults to `min(w, h) / 2 - padding`; pass an explicit `r` to
    fix the radius independent of cell size (sized-dot use case).

    `start`   — fraction [0, 1) of a full turn where sector 0 begins.
                0 (default) = 12 o'clock, proceeding clockwise.
    `weights` — list of n positive numbers for proportional sector angles.
    `gap`     — degrees to cut from each side of a slice edge; creates
                visible separation between adjacent sectors.
    n=1 returns a full circle.
    """
    if n < 1 or not (0 <= i < n):
        raise ValueError(
            f"split_pie: need n >= 1 and 0 <= i < n, got n={n!r}, i={i!r}"
        )
    cx, cy = x + w / 2, y + h / 2
    if r is None:
        r = min(w, h) / 2 - padding
    if r <= 0:
        return ""
    full = 2 * math.pi
    if weights is not None:
        if len(weights) != n:
            raise ValueError(
                f"split_pie: weights must have length n={n}, got {len(weights)}"
            )
        total = sum(weights)
        if total <= 0:
            return ""
        cum = [0.0]
        for wt in weights:
            cum.append(cum[-1] + wt / total * full)
        t0_base, t1_base = cum[i], cum[i + 1]
    else:
        seg = full / n
        t0_base, t1_base = i * seg, (i + 1) * seg
    # start=0 → 12 o'clock = -π/2 in SVG coords (y points down)
    origin = -math.pi / 2 + start * full
    t0 = origin + t0_base
    t1 = origin + t1_base
    if gap > 0:
        gap_rad = gap * math.pi / 180
        t0 += gap_rad / 2
        t1 -= gap_rad / 2
        if t1 <= t0:
            return ""
    # Full 360° arc degenerates in SVG — emit a circle element instead.
    if t1 - t0 >= full - 1e-9:
        return circle(cx, cy, r, fill=fill, stroke=stroke,
                      stroke_width=stroke_width, alpha=alpha,
                      fill_alpha=fill_alpha, stroke_alpha=stroke_alpha)
    large_arc = 1 if (t1 - t0) > math.pi else 0
    x0 = cx + r * math.cos(t0);  y0 = cy + r * math.sin(t0)
    x1 = cx + r * math.cos(t1);  y1 = cy + r * math.sin(t1)
    d = (f"M {coord(cx)},{coord(cy)} L {coord(x0)},{coord(y0)} "
         f"A {coord(r)},{coord(r)} 0 {large_arc} 1 {coord(x1)},{coord(y1)} Z")
    return path(d, fill=fill, stroke=stroke, stroke_width=stroke_width,
                alpha=alpha, fill_alpha=fill_alpha, stroke_alpha=stroke_alpha)
