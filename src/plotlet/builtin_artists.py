"""Built-in artist specs — registered at import time.

Each artist is now a single `ArtistSpec` that knows how to record itself,
contribute to autoscaling, and draw. This replaces the scattered hardcoded
branches in the old `_render`.
"""
from __future__ import annotations

import math

from .registry import ArtistSpec, RenderContext, add_artist
from .artists import (
    _to_pylist, _to_2d_pylist, _histogram,
    _artist_plot, _artist_scatter, _artist_bar, _artist_hist, _artist_fill_between,
    _artist_axhline, _artist_axvline, _artist_axhspan, _artist_axvspan,
    _artist_imshow,
    _marker_at,
)
from ._spec import _D


# --- domain helpers ---------------------------------------------------------

def _xs_of(a):  return a["xs"]
def _ys_of(a):  return a["ys"]
def _vals_of(a): return a["vals"]
def _y1y2_of(a): return list(a["y1"]) + list(a["y2"])
def _bin_xs(a): return [b["x0"] for b in a["_bins"]] + [b["x1"] for b in a["_bins"]]
def _bin_ys(a): return [b["count"] for b in a["_bins"]] + [0]


# --- plot (line) ------------------------------------------------------------

add_artist(ArtistSpec(
    name="plot",
    record=lambda args, kw: {"type": "plot", "xs": _to_pylist(args[0]),
                              "ys": _to_pylist(args[1]), "opts": kw},
    xdomain=_xs_of,
    ydomain=_ys_of,
    draw=lambda a, ctx: _artist_plot(a, ctx.x_scale, ctx.y_scale, ctx.color),
))


# --- scatter ----------------------------------------------------------------

add_artist(ArtistSpec(
    name="scatter",
    record=lambda args, kw: {"type": "scatter", "xs": _to_pylist(args[0]),
                              "ys": _to_pylist(args[1]), "opts": kw},
    xdomain=_xs_of,
    ydomain=_ys_of,
    draw=lambda a, ctx: _artist_scatter(a, ctx.x_scale, ctx.y_scale, ctx.color),
))


# --- bar (categorical x) ----------------------------------------------------
# Bars are special: they drive the categorical x-axis, which is handled
# separately in _render. We still register a spec so the dispatch is uniform.

add_artist(ArtistSpec(
    name="bar",
    record=lambda args, kw: {"type": "bar", "cats": _to_pylist(args[0]),
                              "vals": _to_pylist(args[1]), "opts": kw},
    xdomain=lambda a: None,  # categorical, handled by has_bar branch
    ydomain=_vals_of,
    draw=lambda a, ctx: _artist_bar(a, ctx.x_scale, ctx.y_scale, ctx.color),
))


# --- hist -------------------------------------------------------------------

add_artist(ArtistSpec(
    name="hist",
    record=lambda args, kw: {"type": "hist", "data": _to_pylist(args[0]), "opts": kw},
    xdomain=_bin_xs,
    ydomain=_bin_ys,
    draw=lambda a, ctx: _artist_hist(a, ctx.x_scale, ctx.y_scale, ctx.ih, ctx.color),
))


# --- fill_between -----------------------------------------------------------

add_artist(ArtistSpec(
    name="fill_between",
    record=lambda args, kw: {"type": "fill_between",
                              "xs": _to_pylist(args[0]),
                              "y1": _to_pylist(args[1]),
                              "y2": _to_pylist(args[2]),
                              "opts": kw},
    xdomain=_xs_of,
    ydomain=_y1y2_of,
    draw=lambda a, ctx: _artist_fill_between(a, ctx.x_scale, ctx.y_scale, ctx.color),
))


# --- reference lines and spans ----------------------------------------------
# These don't participate in autoscaling — they decorate the frame.

add_artist(ArtistSpec(
    name="axhline",
    record=lambda args, kw: {"type": "axhline", "y": args[0], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axhline(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["refline_color"],
))

add_artist(ArtistSpec(
    name="axvline",
    record=lambda args, kw: {"type": "axvline", "x": args[0], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axvline(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["refline_color"],
))

add_artist(ArtistSpec(
    name="axhspan",
    record=lambda args, kw: {"type": "axhspan", "ymin": args[0], "ymax": args[1], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axhspan(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="background",
    uses_color_cycle=False,
    default_color=_D["refspan_color"],
))

add_artist(ArtistSpec(
    name="axvspan",
    record=lambda args, kw: {"type": "axvspan", "xmin": args[0], "xmax": args[1], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axvspan(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="background",
    uses_color_cycle=False,
    default_color=_D["refspan_color"],
))


# --- imshow -----------------------------------------------------------------
# imshow needs a preprocessing step (2-D-ify, autocompute vmin/vmax) before
# domain can be computed. We do that in record() rather than _render.

def _imshow_record(args, kw):
    d = _to_2d_pylist(args[0])
    nrows = len(d)
    ncols = len(d[0]) if d else 0
    vmin = kw.get("vmin"); vmax = kw.get("vmax")
    if vmin is None or vmax is None:
        flat = [v for row in d for v in row if v == v]
        if flat:
            if vmin is None: vmin = min(flat)
            if vmax is None: vmax = max(flat)
        else:
            vmin, vmax = 0.0, 1.0
    return {"type": "imshow", "_data": d, "_nrows": nrows, "_ncols": ncols,
            "_vmin": vmin, "_vmax": vmax, "data": d, "opts": kw}


def _imshow_xdomain(a):
    ext = a["opts"].get("extent")
    if ext is None:
        return [0, a["_ncols"]]
    return [ext[0], ext[1]]


def _imshow_ydomain(a):
    ext = a["opts"].get("extent")
    if ext is None:
        return [0, a["_nrows"]]
    return [ext[2], ext[3]]


add_artist(ArtistSpec(
    name="imshow",
    record=_imshow_record,
    xdomain=_imshow_xdomain,
    ydomain=_imshow_ydomain,
    draw=lambda a, ctx: _artist_imshow(a, ctx.x_scale, ctx.y_scale, None),
    uses_color_cycle=False,
))
