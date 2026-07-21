"""User-supplied geometry primitives — rect, polygon, polyline.

`rect` is scale-aware and broadcasts hlines/vlines-style. `polygon` takes
a single closed contour from parallel `xs` / `ys` vertices. `polyline` is
the open-path counterpart to `polygon` — same `(xs, ys)` shape, stroke-only,
never closes. Use it for diagonal reference segments and decorative
multi-point paths in data coords (the gap between `hlines`/`vlines` and
the data-shaped `c.add_line(data=...)`).
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import broadcast, pack_opts, to_list
from .._spec import _D
from ..draw import rect as draw_rect, polygon as draw_polygon, polyline as draw_polyline
from ..draw import resolve_color
from ._shared import _xy_minmax, _bar_legend_entries


def _shape_opts(fill, color, linewidth, alpha, label, legend):
    """Build rect/polygon opts, bar-family style: a literal `fill=`
    color goes to `_fill_literal` (consumed by the color-cycle stamp and
    the draw below); `fill="none"` switches the fill off entirely."""
    opts = pack_opts(color=color, linewidth=linewidth, alpha=alpha,
                     label=label, legend=legend)
    if fill == "none":
        opts["_unfilled"] = True
    elif fill is not None:
        opts["_fill_literal"] = fill
    return opts


def _fill_stroke_params(a, ctx_color):
    """Shared fill/edge resolution for rect and polygon, following the
    bar-family convention. Returns a kwargs dict ready to splat into
    `draw.rect` / `draw.polygon`.
    `fill=` is the fill color (default: the artist color); `fill="none"`
    switches the fill off; `color=` strokes the outline (default None =
    no stroke); `linewidth=` controls outline width (default spec
    linewidth)."""
    opts = a["opts"]
    unfilled = opts.get("_unfilled", False)
    stroke = resolve_color(opts.get("color"))
    lw = opts.get("linewidth", _D["linewidth"])
    alpha = opts.get("alpha", _D["bar_alpha"])
    if unfilled and stroke is None:
        # No fill and no explicit stroke: draw the outline in the artist
        # color so an outline-only shape is still visible.
        stroke = ctx_color
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill = None if unfilled else (
        fill_literal if fill_literal is not None else ctx_color)
    return {"fill": fill,
            "stroke": stroke,
            "stroke_width": lw,
            # `fill="none"` means a transparent shape with an opaque outline —
            # never apply the fill-alpha to the stroke.
            "alpha": 1 if unfilled else alpha}


def _artist_rect(a, xs_, ys_, col, warp=None):
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
        out.append(draw_rect(x_l, y_t, pw, ph, project=warp, **params))
    return "".join(out)


def _artist_polygon(a, xs_, ys_, col, warp=None):
    """Closed polygon from `(xs, ys)` vertices. Always emits a closed
    path (trailing `Z`) so callers don't need to repeat the first point."""
    pts = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["ys"])]
    pts = [(px, py) for px, py in pts if math.isfinite(px) and math.isfinite(py)]
    return draw_polygon(pts, project=warp, **_fill_stroke_params(a, col))


# --- rect ---

def _rect_data_attrs(a):
    n = len(a["xs"])
    out = {"n": n}
    if n:
        x_ends = list(a["xs"]) + [x + w for x, w in zip(a["xs"], a["ws"])]
        y_ends = list(a["ys"]) + [y + h for y, h in zip(a["ys"], a["hs"])]
        out.update(_xy_minmax(x_ends, y_ends))
    return out


def _rect_record(x, y, w, h, fill=None, color=None, linewidth=None,
                 alpha=None, label=None, legend=None):
    xs, ys, ws, hs = broadcast(x, y, w, h)
    return {"type": "rect", "xs": xs, "ys": ys, "ws": ws, "hs": hs,
            "opts": _shape_opts(fill, color, linewidth, alpha, label, legend)}


def _rect_xdomain(a):
    return list(a["xs"]) + [x + w for x, w in zip(a["xs"], a["ws"])]


def _rect_ydomain(a):
    return list(a["ys"]) + [y + h for y, h in zip(a["ys"], a["hs"])]


add_artist(ArtistSpec(
    name="rect",
    record=_rect_record,
    xdomain=_rect_xdomain,
    ydomain=_rect_ydomain,
    draw=lambda a, ctx: _artist_rect(a, ctx.x_scale, ctx.y_scale, ctx.color, ctx.warp),
    legend_entries=_bar_legend_entries,
    data_attrs=_rect_data_attrs,
))


# --- polygon ---

def _polygon_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    return out


def _polygon_record(xs, ys, fill=None, color=None, linewidth=None,
                    alpha=None, label=None, legend=None):
    return {"type": "polygon",
            "xs": to_list(xs),
            "ys": to_list(ys),
            "opts": _shape_opts(fill, color, linewidth, alpha, label, legend)}


add_artist(ArtistSpec(
    name="polygon",
    record=_polygon_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_polygon(a, ctx.x_scale, ctx.y_scale, ctx.color, ctx.warp),
    legend_entries=_bar_legend_entries,
    data_attrs=_polygon_data_attrs,
))


# --- polyline ---

def _artist_polyline(a, xs_, ys_, col, warp=None):
    opts = a["opts"]
    pts = [(xs_(x), ys_(y)) for x, y in zip(a["xs"], a["ys"])]
    pts = [(px, py) for px, py in pts if math.isfinite(px) and math.isfinite(py)]
    color = opts.get("color", col)
    width = opts.get("linewidth", _D["linewidth"])
    dash = opts.get("linestyle")
    alpha = opts.get("alpha", 1)
    return draw_polyline(pts, color=resolve_color(color), width=width,
                          dash=dash, alpha=alpha, project=warp)


def _polyline_record(xs, ys, color=None, linewidth=None, linestyle=None,
                     alpha=None, label=None, legend=None):
    return {"type": "polyline",
            "xs": to_list(xs),
            "ys": to_list(ys),
            "opts": pack_opts(color=color, linewidth=linewidth,
                              linestyle=linestyle, alpha=alpha,
                              label=label, legend=legend)}


add_artist(ArtistSpec(
    name="polyline",
    record=_polyline_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_polyline(a, ctx.x_scale, ctx.y_scale, ctx.color, ctx.warp),
    data_attrs=_polygon_data_attrs,
))
