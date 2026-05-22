"""User-supplied geometry primitives — rect and polygon.

`rect` is scale-aware and broadcasts hlines/vlines-style. `polygon` takes
a single closed contour from parallel `xs` / `ys` vertices.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import broadcast, to_list
from .._spec import _D
from ..draw import rect as draw_rect, polygon as draw_polygon
from ..draw.colors import _resolve_color
from ._shared import _xy_minmax, _bar_legend_entries


def _fill_stroke_params(a, ctx_color):
    """Shared edge/fill resolution for rect and polygon. Returns a kwargs
    dict ready to splat into `draw.rect` / `draw.polygon`.
    `fill=False` switches the fill off entirely; `edgecolor=` overrides the
    artist color for the outline; `linewidth=` controls outline width
    (default spec linewidth)."""
    opts = a["opts"]
    do_fill = opts.get("fill", True)
    edge = opts.get("edgecolor")
    lw = opts.get("linewidth", _D["linewidth"])
    alpha = opts.get("alpha", _D["bar_alpha"])
    if edge is not None:
        stroke = _resolve_color(edge)
    elif not do_fill:
        # No fill and no explicit edge: draw the outline in the artist color
        # so the shape is visible at all (matplotlib's `fill=False` idiom).
        stroke = ctx_color
    else:
        stroke = None
    return {"fill": ctx_color if do_fill else None,
            "stroke": stroke,
            "stroke_width": lw,
            # `fill=False` means a transparent shape with an opaque outline —
            # never apply the fill-alpha to the stroke.
            "alpha": alpha if do_fill else 1}


def _artist_rect(a, xs_, ys_, col):
    """Scale-aware axis-aligned rectangles. `xs`, `ys`, `ws`, `hs` are
    pre-broadcast to a common length in `record`. Each rect spans
    `(x, y) -> (x + w, y + h)` in data coords; pixel-space sign is fixed
    up so flipped y-axes (imshow origin='upper') still render correctly."""
    params = _fill_stroke_params(a, col)
    out = []
    for x, y, w, h in zip(a["xs"], a["ys"], a["ws"], a["hs"]):
        px0 = xs_(x); px1 = xs_(x + w)
        py0 = ys_(y); py1 = ys_(y + h)
        if not all(math.isfinite(v) for v in (px0, px1, py0, py1)):
            continue
        x_l = min(px0, px1); y_t = min(py0, py1)
        pw = abs(px1 - px0); ph = abs(py1 - py0)
        if pw <= 0 or ph <= 0:
            continue
        out.append(draw_rect(x_l, y_t, pw, ph, **params))
    return "".join(out)


def _artist_polygon(a, xs_, ys_, col):
    """Closed polygon from `(xs, ys)` vertices. Always emits a closed path
    (trailing `Z`) — matches matplotlib's `plt.fill()` which auto-closes."""
    pts = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["ys"])]
    pts = [(px, py) for px, py in pts if math.isfinite(px) and math.isfinite(py)]
    return draw_polygon(pts, **_fill_stroke_params(a, col))


# --- rect ---

def _rect_data_attrs(a):
    n = len(a["xs"])
    out = {"n": n}
    if n:
        x_ends = list(a["xs"]) + [x + w for x, w in zip(a["xs"], a["ws"])]
        y_ends = list(a["ys"]) + [y + h for y, h in zip(a["ys"], a["hs"])]
        out.update(_xy_minmax(x_ends, y_ends))
    return out


def _rect_record(args, kw):
    xs, ys, ws, hs = broadcast(args[0], args[1], args[2], args[3])
    return {"type": "rect", "xs": xs, "ys": ys, "ws": ws, "hs": hs, "opts": kw}


def _rect_xdomain(a):
    return list(a["xs"]) + [x + w for x, w in zip(a["xs"], a["ws"])]


def _rect_ydomain(a):
    return list(a["ys"]) + [y + h for y, h in zip(a["ys"], a["hs"])]


add_artist(ArtistSpec(
    name="rect",
    record=_rect_record,
    xdomain=_rect_xdomain,
    ydomain=_rect_ydomain,
    draw=lambda a, ctx: _artist_rect(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_bar_legend_entries,
    data_attrs=_rect_data_attrs,
))


# --- polygon ---

def _polygon_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    return out


add_artist(ArtistSpec(
    name="polygon",
    record=lambda args, kw: {"type": "polygon",
                              "xs": to_list(args[0]),
                              "ys": to_list(args[1]),
                              "opts": kw},
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_polygon(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_bar_legend_entries,
    data_attrs=_polygon_data_attrs,
))
