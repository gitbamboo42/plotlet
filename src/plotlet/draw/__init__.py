"""Drawing primitives for use inside a custom artist's `draw` callback.

These functions emit SVG fragments at *pixel* coordinates. They're the public
counterpart to the SVG-emit helpers used internally by the built-in artists —
call them from inside your own `draw=` function (the one you hand to
`ArtistSpec`).

Example:

    from plotlet import draw

    def my_draw(a, ctx):
        out = []
        for x, y, label in zip(a["xs"], a["ys"], a["labels"]):
            px = ctx.x_scale(x); py = ctx.y_scale(y)
            out.append(draw.marker("o", px, py, 4, ctx.color, 1))
            out.append(draw.text_path(label, px, py - 8, 10, anchor="middle"))
        return "".join(out)

The primitives map 1:1 to common SVG shapes (`segment`, `rect`, `circle`,
`path`) plus a couple of compounds — `polyline` / `polygon` for point lists,
`errorbar_v` / `errorbar_h` for a bar with two caps. All take pixel
coordinates and emit SVG fragments; combine them with `"".join(...)` in
your draw callback.

The four shape helpers (`rect`, `circle`, `path`, `polygon`) accept optional
`fill_alpha` / `stroke_alpha` overrides for the case where you want a
translucent body with an opaque outline (or vice versa); leave them `None`
and `alpha=` applies to the whole element via a single lean `opacity` attr.

For chart-recording counterparts (data coordinates, not pixels), use the
methods on `Chart` directly — `c.text(x, y, s)`, `c.scatter(xs, ys)`, etc.

The `font`, `colors`, `colormaps` submodules expose the underlying drawing
subsystem (font measurement, color resolution, colormap LUTs) for callers
that need finer-grained control.
"""
from .._spec import _D, _DASH
from .font import _glyph, _measure_text, _UPEM, _GS
from .linestyles import _resolve_linestyle

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform


def text_path(s: str, x: float, y: float, size: float,
              anchor: str = "start", color: str = "#000") -> str:
    """Render `s` as a single SVG <path> with its baseline at pixel (x, y).

    `anchor` matches SVG's text-anchor: 'start' | 'middle' | 'end'. Use this
    inside a custom artist's `draw` callback to emit text-as-paths so output
    stays font-independent across machines.
    """
    if not s:
        return ""
    width = _measure_text(s, size)
    if anchor == "middle":
        x0 = x - width / 2
    elif anchor == "end":
        x0 = x - width
    else:
        x0 = x
    pen = SVGPathPen(_GS)
    scale = size / _UPEM
    cx = x0
    for ch in s:
        g = _glyph(ch)
        # SVG y points down, font y points up — flip with negative scale.
        tpen = TransformPen(pen, Transform().translate(cx, y).scale(scale, -scale))
        g.draw(tpen)
        cx += g.width * scale
    return f'<path d="{pen.getCommands()}" fill="{color}"/>'


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
    pixel `(x, y)`. Returns an empty string for unknown marker codes.

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
    return ""


def _dash_attr(dash) -> str:
    if not dash:
        return ""
    d = _DASH.get(_resolve_linestyle(dash), dash)
    return f' stroke-dasharray="{d}"' if d else ""


def segment(x1: float, y1: float, x2: float, y2: float, *,
            color: str = "#000", width: float = 1, dash=None, alpha=1) -> str:
    """Emit a single SVG `<line>` segment from pixel (x1, y1) to (x2, y2).

    `dash` accepts a matplotlib code (`"--"`, `":"`, `"-."`) or a raw SVG
    dasharray string (`"6,3"`); `None` (default) is solid.
    """
    return (f'<line x1="{x1:.2f}" x2="{x2:.2f}" y1="{y1:.2f}" y2="{y2:.2f}" '
            f'stroke="{color}" stroke-width="{width}"{op(alpha)}{_dash_attr(dash)}/>')


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
    sa = (f' stroke="{stroke}" stroke-width="{stroke_width}"{_dash_attr(dash)}'
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
    sa = f' stroke="{stroke}" stroke-width="{stroke_width}"{_dash_attr(dash)}' if stroke else ""
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


__all__ = ["text_path", "marker", "op", "segment", "rect", "circle",
           "path", "polyline", "polygon", "errorbar_v", "errorbar_h"]
