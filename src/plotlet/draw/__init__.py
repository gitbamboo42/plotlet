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

For chart-recording counterparts (data coordinates, not pixels), use the
methods on `Chart` directly — `c.text(x, y, s)`, `c.scatter(xs, ys)`, etc.

The `font`, `colors`, `colormaps` submodules expose the underlying drawing
subsystem (font measurement, color resolution, colormap LUTs) for callers
that need finer-grained control.
"""
from .._spec import _D, _DASH
from .font import _glyph, _measure_text, _UPEM, _GS

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


def marker(marker: str, x: float, y: float, size: float, col: str, alpha) -> str:
    """Emit a single marker glyph (one of `"o" "s" "^" "v" "x" "+"`) at
    pixel `(x, y)`. Returns an empty string for unknown marker codes.
    """
    msw = _D["marker_stroke_width"]
    _op = op(alpha)
    if marker == "o":
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size}" fill="{col}"{_op}/>'
    if marker == "s":
        return (f'<rect x="{x - size:.2f}" y="{y - size:.2f}" width="{2 * size}" '
                f'height="{2 * size}" fill="{col}"{_op}/>')
    if marker == "^":
        return (f'<path d="M{x:.2f},{y - size:.2f}L{x + size:.2f},{y + size:.2f}'
                f'L{x - size:.2f},{y + size:.2f}Z" fill="{col}"{_op}/>')
    if marker == "v":
        return (f'<path d="M{x:.2f},{y + size:.2f}L{x + size:.2f},{y - size:.2f}'
                f'L{x - size:.2f},{y - size:.2f}Z" fill="{col}"{_op}/>')
    if marker == "x":
        return (f'<path d="M{x - size:.2f},{y - size:.2f}L{x + size:.2f},{y + size:.2f}'
                f'M{x - size:.2f},{y + size:.2f}L{x + size:.2f},{y - size:.2f}" '
                f'stroke="{col}" stroke-width="{msw}"{_op}/>')
    if marker == "+":
        return (f'<path d="M{x - size:.2f},{y:.2f}L{x + size:.2f},{y:.2f}'
                f'M{x:.2f},{y - size:.2f}L{x:.2f},{y + size:.2f}" '
                f'stroke="{col}" stroke-width="{msw}"{_op}/>')
    return ""


def segment(x1: float, y1: float, x2: float, y2: float, *,
            color: str = "#000", width: float = 1, dash=None, alpha=1) -> str:
    """Emit a single SVG `<line>` segment from pixel (x1, y1) to (x2, y2).

    `dash` accepts a matplotlib code (`"--"`, `":"`, `"-."`) or a raw SVG
    dasharray string (`"6,3"`); `None` (default) is solid.
    """
    da = ""
    if dash:
        d = _DASH.get(dash, dash)
        if d:
            da = f' stroke-dasharray="{d}"'
    return (f'<line x1="{x1:.2f}" x2="{x2:.2f}" y1="{y1:.2f}" y2="{y2:.2f}" '
            f'stroke="{color}" stroke-width="{width}"{da}{op(alpha)}/>')


def rect(x: float, y: float, w: float, h: float, *,
         fill: str = "none", stroke: str = None,
         stroke_width: float = 1, alpha=1) -> str:
    """Emit a single SVG `<rect>` at pixel (x, y) with size (w, h).

    `fill="none"` draws an outline only; pass `stroke=` to add a border.
    """
    sa = f' stroke="{stroke}" stroke-width="{stroke_width}"' if stroke else ""
    return (f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{fill}"{sa}{op(alpha)}/>')


__all__ = ["text_path", "marker", "op", "segment", "rect"]
