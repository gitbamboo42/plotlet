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
import math

from .._spec import _D, _DASH
from .font import measure_text, _glyph_path_d, _decoration_y_offset
from .linestyles import resolve_linestyle


def text_path(s: str, x: float, y: float, size: float,
              anchor: str = "start", color: str = "#000",
              fontstyle: str = "normal",
              decoration: str = "none",
              rotate: float = 0) -> str:
    """Render `s` as a single SVG <path> with its baseline at pixel (x, y).

    `anchor` matches SVG's text-anchor: 'start' | 'middle' | 'end'. Use this
    inside a custom artist's `draw` callback to emit text-as-paths so output
    stays font-independent across machines.

    `fontstyle="italic"` synthesizes an oblique slant via a -12° skew during
    glyph composition — matches what matplotlib does when only an upright
    font is available (DejaVu Sans ships no real italic).

    `decoration="underline" | "overline" | "line-through"` appends a stroke
    line at the conventional offset for that decoration.

    `rotate=` (degrees, positive = CCW) rotates the glyph (and any
    decoration line) around the anchor point (x, y). Convention matches
    `xticks(rotation=...)` and the rest of the lib — SVG's positive-CW
    is negated at emission so callers think in matplotlib's visual CCW.
    """
    d = _glyph_path_d(s, x, y, size, anchor=anchor, fontstyle=fontstyle)
    if not d:
        return ""
    out = f'<path d="{d}" fill="{color}"/>'
    if decoration != "none":
        width = measure_text(s, size)
        if anchor == "middle":
            x0 = x - width / 2
        elif anchor == "end":
            x0 = x - width
        else:
            x0 = x
        dy = _decoration_y_offset(decoration, size)
        line_w = max(0.6, size * 0.06)
        out += (f'<line x1="{x0:.2f}" y1="{y + dy:.2f}" '
                f'x2="{x0 + width:.2f}" y2="{y + dy:.2f}" '
                f'stroke="{color}" stroke-width="{line_w:.2f}"/>')
    if rotate:
        out = f'<g transform="rotate({-rotate:.2f} {x:.2f} {y:.2f})">{out}</g>'
    return out


def op(alpha) -> str:
    """SVG opacity attribute, omitted when fully opaque to keep output lean."""
    return "" if alpha == 1 else f' opacity="{alpha}"'


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
    fop = f' fill-opacity="{fa}"' if has_fill and fa != 1 else ""
    sop = f' stroke-opacity="{sa}"' if has_stroke and sa != 1 else ""
    return fop + sop


def marker(kind: str, x: float, y: float, size: float, color: str, alpha,
           edgecolor: str | None = None, edgewidth: float | None = None) -> str:
    """Emit a single marker glyph (one of `"o" "s" "^" "v" "x" "+"`) at
    pixel `(x, y)`. Raises `ValueError` for unknown marker codes.

    `edgecolor=` adds an outline to filled markers (`o`/`s`/`^`/`v`).
    `edgewidth=` overrides the stroke width for ALL markers (including the
    `x`/`+` outlines, which use `color` as their stroke); falls back to
    `_D["marker_stroke_width"]`."""
    msw = edgewidth if edgewidth is not None else _D["marker_stroke_width"]
    _op = op(alpha)
    edge = f' stroke="{edgecolor}" stroke-width="{msw}"' if edgecolor else ""
    if kind == "o":
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size}" fill="{color}"{edge}{_op}/>'
    if kind == "s":
        return (f'<rect x="{x - size:.2f}" y="{y - size:.2f}" width="{2 * size}" '
                f'height="{2 * size}" fill="{color}"{edge}{_op}/>')
    if kind == "^":
        return (f'<path d="M{x:.2f},{y - size:.2f}L{x + size:.2f},{y + size:.2f}'
                f'L{x - size:.2f},{y + size:.2f}Z" fill="{color}"{edge}{_op}/>')
    if kind == "v":
        return (f'<path d="M{x:.2f},{y + size:.2f}L{x + size:.2f},{y - size:.2f}'
                f'L{x - size:.2f},{y - size:.2f}Z" fill="{color}"{edge}{_op}/>')
    if kind == "x":
        return (f'<path d="M{x - size:.2f},{y - size:.2f}L{x + size:.2f},{y + size:.2f}'
                f'M{x - size:.2f},{y + size:.2f}L{x + size:.2f},{y - size:.2f}" '
                f'stroke="{color}" stroke-width="{msw}"{_op}/>')
    if kind == "+":
        return (f'<path d="M{x - size:.2f},{y:.2f}L{x + size:.2f},{y:.2f}'
                f'M{x:.2f},{y - size:.2f}L{x:.2f},{y + size:.2f}" '
                f'stroke="{color}" stroke-width="{msw}"{_op}/>')
    raise ValueError(f"unknown marker kind {kind!r}; expected one of 'o' 's' '^' 'v' 'x' '+'.")


def dash_attr(dash) -> str:
    if not dash:
        return ""
    d = _DASH.get(resolve_linestyle(dash), dash)
    return f' stroke-dasharray="{d}"' if d else ""


def segment(x1: float, y1: float, x2: float, y2: float, *,
            color: str = "#000", width: float = 1, dash=None, alpha=1) -> str:
    """Emit a single SVG `<line>` segment from pixel (x1, y1) to (x2, y2).

    `dash` accepts a matplotlib code (`"--"`, `":"`, `"-."`) or a raw SVG
    dasharray string (`"6,3"`); `None` (default) is solid.
    """
    return (f'<line x1="{x1:.2f}" x2="{x2:.2f}" y1="{y1:.2f}" y2="{y2:.2f}" '
            f'stroke="{color}" stroke-width="{width}"{op(alpha)}{dash_attr(dash)}/>')


def rect(x: float, y: float, w: float, h: float, *,
         fill: str = None, stroke: str = None,
         stroke_width: float = 1, alpha=1,
         fill_alpha=None, stroke_alpha=None,
         dash=None, shape_rendering: str | None = None) -> str:
    """Emit a single SVG `<rect>` at pixel (x, y) with size (w, h).

    `fill=None` (default) draws an outline only — pass `stroke=` to add a
    border. `fill_alpha` / `stroke_alpha` override `alpha` per channel when
    you need a translucent body with an opaque outline (or vice versa); when
    both are `None`, `alpha` is applied as a single whole-element `opacity`.
    `dash` accepts a registered linestyle (`"--"`, `":"`, `"-."`) or a raw
    SVG dasharray (`"6,3"`). `shape_rendering="crispEdges"` pixel-aligns
    borders, useful for contiguous-band heatmap-style rects.
    """
    fa = f' fill="{fill}"' if fill else ' fill="none"'
    sa = (f' stroke="{stroke}" stroke-width="{stroke_width}"{dash_attr(dash)}'
          if stroke else "")
    oa = _shape_opacity(alpha, fill_alpha, stroke_alpha,
                        has_fill=bool(fill), has_stroke=bool(stroke))
    sr = f' shape-rendering="{shape_rendering}"' if shape_rendering else ""
    return (f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"'
            f'{fa}{sa}{oa}{sr}/>')


def circle(cx: float, cy: float, r: float, *,
           fill: str = None, stroke: str = None,
           stroke_width: float = 1, alpha=1,
           fill_alpha=None, stroke_alpha=None) -> str:
    """Emit a single SVG `<circle>` at pixel (cx, cy) with radius r.

    Pass `fill=` for a filled disc, `stroke=` for an outline, or both.
    `fill=None` (default) emits `fill="none"` so an outline-only call works.
    `fill_alpha` / `stroke_alpha` override `alpha` per channel.
    """
    fa = f' fill="{fill}"' if fill else ' fill="none"'
    sa = f' stroke="{stroke}" stroke-width="{stroke_width}"' if stroke else ""
    oa = _shape_opacity(alpha, fill_alpha, stroke_alpha,
                        has_fill=bool(fill), has_stroke=bool(stroke))
    return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"{fa}{sa}{oa}/>'


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
    sa = f' stroke="{stroke}" stroke-width="{stroke_width}"{dash_attr(dash)}' if stroke else ""
    oa = _shape_opacity(alpha, fill_alpha, stroke_alpha,
                        has_fill=bool(fill), has_stroke=bool(stroke))
    return f'<path d="{d}"{fa}{sa}{oa}/>'


def polyline(points, *,
             color: str = "#000", width: float = 1, dash=None, alpha=1) -> str:
    """Stroke a polyline through `points` (list of `(x, y)` pixel tuples).

    Returns `""` for fewer than two points. No fill — for a closed filled
    shape, use `polygon`.
    """
    if not points or len(points) < 2:
        return ""
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return path(d, stroke=color, stroke_width=width, dash=dash, alpha=alpha)


def polygon(points, *,
            fill: str = None, stroke: str = None,
            stroke_width: float = 1, alpha=1,
            fill_alpha=None, stroke_alpha=None) -> str:
    """Closed polygon through `points` (list of `(x, y)` pixel tuples).

    Always emits a trailing `Z`, so the shape is closed even if the last
    point doesn't repeat the first. Pass `fill=` for a filled shape,
    `stroke=` for an outline, or both. `fill_alpha` / `stroke_alpha`
    override `alpha` per channel.
    """
    if not points or len(points) < 3:
        return ""
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points) + "Z"
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
    d = (f"M {x0:.2f},{y0:.2f} "
         f"A {rx:.2f},{ry:.2f} {angle:.2f} 0 {sweep} {x1:.2f},{y1:.2f}")
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
    d = (f"M {cx:.2f},{cy:.2f} L {x0:.2f},{y0:.2f} "
         f"A {r:.2f},{r:.2f} 0 {large_arc} 1 {x1:.2f},{y1:.2f} Z")
    return path(d, fill=fill, stroke=stroke, stroke_width=stroke_width,
                alpha=alpha, fill_alpha=fill_alpha, stroke_alpha=stroke_alpha)
