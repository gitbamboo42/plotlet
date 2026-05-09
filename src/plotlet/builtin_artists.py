"""Built-in artist specs — registered at import time.

Each artist is now a single `ArtistSpec` that knows how to record itself,
contribute to autoscaling, and draw. This replaces the scattered hardcoded
branches in the old `_render`.
"""
from __future__ import annotations

import math

from .registry import ArtistSpec, RenderContext, add_artist
from .artists import (
    _to_pylist, _to_2d_pylist, _histogram, _broadcast_three,
    _artist_plot, _artist_scatter, _artist_bar, _artist_hist, _artist_fill_between,
    _artist_axhline, _artist_axvline, _artist_axhspan, _artist_axvspan,
    _artist_hlines, _artist_vlines,
    _artist_imshow,
    _marker_at, _op,
)
from ._spec import _D, _LEGSPEC


# --- domain helpers ---------------------------------------------------------

def _xs_of(a):  return a["xs"]
def _ys_of(a):  return a["ys"]
def _vals_of(a): return a["vals"]
def _y1y2_of(a): return list(a["y1"]) + list(a["y2"])
def _bin_xs(a): return [b["x0"] for b in a["_bins"]] + [b["x1"] for b in a["_bins"]]
def _bin_ys(a): return [b["count"] for b in a["_bins"]] + [0]


# --- legend swatch helpers --------------------------------------------------
# Each built-in artist registers one of these so the legend dispatch in
# `_render` can stay generic — no type-string matching.

def _line_swatch(a, ctx, x0, y_mid, default_lw):
    sw = _LEGSPEC["swatch_width"]
    ls = a["opts"].get("linestyle")
    da = f' stroke-dasharray="{ctx.dash[ls]}"' if ls and ctx.dash.get(ls) else ""
    return (f'<line x1="{x0}" x2="{x0 + sw}" y1="{y_mid}" y2="{y_mid}" '
            f'stroke="{a["_color"]}" '
            f'stroke-width="{a["opts"].get("linewidth", default_lw)}"{da}/>')


def _plot_legend_swatch(a, ctx, x0, y_mid):
    out = _line_swatch(a, ctx, x0, y_mid, ctx.defaults["linewidth"])
    if a["opts"].get("marker"):
        sw = _LEGSPEC["swatch_width"]
        out += _marker_at(a["opts"]["marker"], x0 + sw / 2, y_mid,
                          a["opts"].get("markersize", ctx.defaults["markersize"]),
                          a["_color"], 1)
    return out


def _refline_legend_swatch(a, ctx, x0, y_mid):
    return _line_swatch(a, ctx, x0, y_mid, ctx.defaults["refline_width"])


def _scatter_legend_swatch(a, ctx, x0, y_mid):
    sw = _LEGSPEC["swatch_width"]
    s_size = math.sqrt(a["opts"].get("s", ctx.defaults["scatter_s"])) / 2
    return _marker_at(a["opts"].get("marker", "o"),
                      x0 + sw / 2, y_mid, s_size, a["_color"],
                      a["opts"].get("alpha", ctx.defaults["scatter_alpha"]))


def _rect_swatch(a, x0, y_mid, default_alpha):
    sw = _LEGSPEC["swatch_width"]
    return (f'<rect x="{x0}" y="{y_mid - 5}" width="{sw}" height="10" '
            f'fill="{a["_color"]}"'
            f'{_op(a["opts"].get("alpha", default_alpha))}/>')


def _bar_legend_swatch(a, ctx, x0, y_mid):
    return _rect_swatch(a, x0, y_mid, 1)


def _refspan_legend_swatch(a, ctx, x0, y_mid):
    return _rect_swatch(a, x0, y_mid, ctx.defaults["refspan_alpha"])


# --- AI-readable structural attrs + payloads (0.3.0) ------------------------
# Each helper computes type-specific attrs from the recorded artist dict.
# The wrapper in core._wrap_artist supplies the common attrs (type, index,
# label, color); these add the per-artist fields. Returned dict keys map
# 1:1 to `data-plotlet-<key>` attribute names.

def _xy_minmax(xs, ys):
    """Min/max for an x/y series, ignoring NaN. Returns dict ready to merge
    into a data_attrs result."""
    fxs = [x for x in xs if isinstance(x, (int, float)) and x == x]
    fys = [y for y in ys if isinstance(y, (int, float)) and y == y]
    out = {}
    if fxs:
        out["x-min"] = min(fxs)
        out["x-max"] = max(fxs)
    if fys:
        out["y-min"] = min(fys)
        out["y-max"] = max(fys)
    return out


def _plot_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    if a["opts"].get("linestyle"):
        out["linestyle"] = a["opts"]["linestyle"]
    if a["opts"].get("marker"):
        out["marker"] = a["opts"]["marker"]
    return out


def _scatter_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _bar_data_attrs(a):
    fvals = [v for v in a["vals"] if isinstance(v, (int, float)) and v == v]
    out = {"n": len(a["cats"])}
    if fvals:
        out["y-min"] = min(fvals)
        out["y-max"] = max(fvals)
    return out


def _hist_data_attrs(a):
    raw = a["data"]
    out = {"n": len(raw), "bins": len(a.get("_bins", [])) or a["opts"].get("bins", 10)}
    bins = a.get("_bins") or []
    if bins:
        out["x-min"] = bins[0]["x0"]
        out["x-max"] = bins[-1]["x1"]
        out["count-max"] = max(b["count"] for b in bins)
    return out


def _fill_between_data_attrs(a):
    ys_all = list(a["y1"]) + list(a["y2"])
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], ys_all))
    return out


def _axhline_data_attrs(a):  return {"y": a["y"]}
def _axvline_data_attrs(a):  return {"x": a["x"]}
def _axhspan_data_attrs(a):  return {"ymin": a["ymin"], "ymax": a["ymax"]}
def _axvspan_data_attrs(a):  return {"xmin": a["xmin"], "xmax": a["xmax"]}


def _hlines_data_attrs(a):
    out = {"n": len(a["ys"])}
    if a["ys"]:
        out["y-min"] = min(a["ys"]); out["y-max"] = max(a["ys"])
    if a["xmins"] and a["xmaxs"]:
        out["x-min"] = min(a["xmins"]); out["x-max"] = max(a["xmaxs"])
    return out


def _vlines_data_attrs(a):
    out = {"n": len(a["xs"])}
    if a["xs"]:
        out["x-min"] = min(a["xs"]); out["x-max"] = max(a["xs"])
    if a["ymins"] and a["ymaxs"]:
        out["y-min"] = min(a["ymins"]); out["y-max"] = max(a["ymaxs"])
    return out


def _imshow_data_attrs(a):
    out = {
        "rows": a["_nrows"],
        "cols": a["_ncols"],
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "cmap": a["opts"].get("cmap", _D["default_cmap"]),
        # imshow is always raster (PNG-embedded above the rect threshold,
        # individual <rect>s below). The flag is here so AI tools know
        # which decoding strategy they're looking at.
        "data-encoding": "png-embedded" if (a["_nrows"] * a["_ncols"]
                                              > _D["imshow_max_rects"]) else "rects",
    }
    extent = a["opts"].get("extent")
    if extent is not None:
        out["extent"] = ",".join(repr(float(v)) for v in extent)
    return out




# --- plot (line) ------------------------------------------------------------

add_artist(ArtistSpec(
    name="plot",
    record=lambda args, kw: {"type": "plot", "xs": _to_pylist(args[0]),
                              "ys": _to_pylist(args[1]), "opts": kw},
    xdomain=_xs_of,
    ydomain=_ys_of,
    draw=lambda a, ctx: _artist_plot(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_swatch=_plot_legend_swatch,
    data_attrs=_plot_data_attrs,
))


# --- scatter ----------------------------------------------------------------

add_artist(ArtistSpec(
    name="scatter",
    record=lambda args, kw: {"type": "scatter", "xs": _to_pylist(args[0]),
                              "ys": _to_pylist(args[1]), "opts": kw},
    xdomain=_xs_of,
    ydomain=_ys_of,
    draw=lambda a, ctx: _artist_scatter(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_swatch=_scatter_legend_swatch,
    data_attrs=_scatter_data_attrs,
))


# --- bar --------------------------------------------------------------------
# Bar contributes its categories on x; the descriptor's auto-categorical
# detection picks them up the same way it would for any string-valued x.

add_artist(ArtistSpec(
    name="bar",
    record=lambda args, kw: {"type": "bar", "cats": _to_pylist(args[0]),
                              "vals": _to_pylist(args[1]), "opts": kw},
    xdomain=lambda a: a["cats"],
    ydomain=_vals_of,
    draw=lambda a, ctx: _artist_bar(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_swatch=_bar_legend_swatch,
    data_attrs=_bar_data_attrs,
))


# --- hist -------------------------------------------------------------------

add_artist(ArtistSpec(
    name="hist",
    record=lambda args, kw: {"type": "hist", "data": _to_pylist(args[0]), "opts": kw},
    xdomain=_bin_xs,
    ydomain=_bin_ys,
    draw=lambda a, ctx: _artist_hist(a, ctx.x_scale, ctx.y_scale, ctx.ih, ctx.color),
    legend_swatch=_bar_legend_swatch,
    data_attrs=_hist_data_attrs,
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
    legend_swatch=_plot_legend_swatch,
    data_attrs=_fill_between_data_attrs,
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
    legend_swatch=_refline_legend_swatch,
    data_attrs=_axhline_data_attrs,
))

add_artist(ArtistSpec(
    name="axvline",
    record=lambda args, kw: {"type": "axvline", "x": args[0], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axvline(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["refline_color"],
    legend_swatch=_refline_legend_swatch,
    data_attrs=_axvline_data_attrs,
))

add_artist(ArtistSpec(
    name="axhspan",
    record=lambda args, kw: {"type": "axhspan", "ymin": args[0], "ymax": args[1], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axhspan(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="background",
    uses_color_cycle=False,
    default_color=_D["refspan_color"],
    legend_swatch=_refspan_legend_swatch,
    data_attrs=_axhspan_data_attrs,
))

add_artist(ArtistSpec(
    name="axvspan",
    record=lambda args, kw: {"type": "axvspan", "xmin": args[0], "xmax": args[1], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axvspan(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="background",
    uses_color_cycle=False,
    default_color=_D["refspan_color"],
    legend_swatch=_refspan_legend_swatch,
    data_attrs=_axvspan_data_attrs,
))


# --- hlines / vlines --------------------------------------------------------
# Bounded line segments in data coordinates — unlike axhline/axvline (which
# span the full frame regardless of scale), these participate in autoscaling
# and use the color cycle so a labeled hlines/vlines acts like a series.

def _hlines_record(args, kw):
    ys, xmins, xmaxs = _broadcast_three(args[0], args[1], args[2])
    return {"type": "hlines", "ys": ys, "xmins": xmins, "xmaxs": xmaxs, "opts": kw}


def _vlines_record(args, kw):
    xs, ymins, ymaxs = _broadcast_three(args[0], args[1], args[2])
    return {"type": "vlines", "xs": xs, "ymins": ymins, "ymaxs": ymaxs, "opts": kw}


add_artist(ArtistSpec(
    name="hlines",
    record=_hlines_record,
    xdomain=lambda a: a["xmins"] + a["xmaxs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_hlines(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_swatch=_refline_legend_swatch,
    data_attrs=_hlines_data_attrs,
))


add_artist(ArtistSpec(
    name="vlines",
    record=_vlines_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ymins"] + a["ymaxs"],
    draw=lambda a, ctx: _artist_vlines(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_swatch=_refline_legend_swatch,
    data_attrs=_vlines_data_attrs,
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


def _imshow_legend_gradient(a):
    """Describe imshow's continuous mapping (cmap + range + user overrides) for legend rendering."""
    legend_opts = a["opts"].get("legend") or {}
    return {
        "kind": "continuous",
        "cmap": a["opts"].get("cmap", _D["default_cmap"]),
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "label": legend_opts.get("label"),
        "ticks": legend_opts.get("ticks"),
    }


add_artist(ArtistSpec(
    name="imshow",
    record=_imshow_record,
    xdomain=_imshow_xdomain,
    ydomain=_imshow_ydomain,
    draw=lambda a, ctx: _artist_imshow(a, ctx.x_scale, ctx.y_scale, None),
    legend_gradient=_imshow_legend_gradient,
    uses_color_cycle=False,
    data_attrs=_imshow_data_attrs,
))
