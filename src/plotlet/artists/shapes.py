"""User-supplied geometry primitives — rect and polygon.

`rect` is scale-aware and broadcasts hlines/vlines-style. `polygon` takes
a single closed contour from parallel `xs` / `ys` vertices.
"""
from ..registry import ArtistSpec, add_artist
from ..utils import broadcast, to_list
from .._artist_impl import _artist_rect, _artist_polygon
from ._shared import _xy_minmax, _bar_legend_entries


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
