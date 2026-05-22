"""Reference-line / span artists — decorate the frame.

`axhline` / `axvline` / `axhspan` / `axvspan` ignore autoscaling and span
the full frame regardless of the data scale. `hlines` / `vlines` are the
bounded, data-coordinate counterparts that participate in autoscaling and
use the color cycle so a labeled call acts like a series.
"""
from ..registry import ArtistSpec, add_artist
from ..utils import broadcast
from .._spec import _D
from .._artist_impl import (
    _artist_axhline, _artist_axvline,
    _artist_axhspan, _artist_axvspan,
    _artist_hlines, _artist_vlines,
)
from ._shared import _refline_legend_entries, _refspan_legend_entries


# --- axhline ---

def _axhline_data_attrs(a):  return {"y": a["y"]}


add_artist(ArtistSpec(
    name="axhline",
    record=lambda args, kw: {"type": "axhline", "y": args[0], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axhline(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["refline_color"],
    legend_entries=_refline_legend_entries,
    data_attrs=_axhline_data_attrs,
))


# --- axvline ---

def _axvline_data_attrs(a):  return {"x": a["x"]}


add_artist(ArtistSpec(
    name="axvline",
    record=lambda args, kw: {"type": "axvline", "x": args[0], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axvline(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="foreground",
    uses_color_cycle=False,
    default_color=_D["refline_color"],
    legend_entries=_refline_legend_entries,
    data_attrs=_axvline_data_attrs,
))


# --- axhspan ---

def _axhspan_data_attrs(a):  return {"ymin": a["ymin"], "ymax": a["ymax"]}


add_artist(ArtistSpec(
    name="axhspan",
    record=lambda args, kw: {"type": "axhspan", "ymin": args[0], "ymax": args[1], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axhspan(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="background",
    uses_color_cycle=False,
    default_color=_D["refspan_color"],
    legend_entries=_refspan_legend_entries,
    data_attrs=_axhspan_data_attrs,
))


# --- axvspan ---

def _axvspan_data_attrs(a):  return {"xmin": a["xmin"], "xmax": a["xmax"]}


add_artist(ArtistSpec(
    name="axvspan",
    record=lambda args, kw: {"type": "axvspan", "xmin": args[0], "xmax": args[1], "opts": kw},
    xdomain=lambda a: None, ydomain=lambda a: None,
    draw=lambda a, ctx: _artist_axvspan(a, ctx.x_scale, ctx.y_scale, ctx.iw, ctx.ih, ctx.color),
    layer="background",
    uses_color_cycle=False,
    default_color=_D["refspan_color"],
    legend_entries=_refspan_legend_entries,
    data_attrs=_axvspan_data_attrs,
))


# --- hlines ---

def _hlines_data_attrs(a):
    out = {"n": len(a["ys"])}
    if a["ys"]:
        out["y-min"] = min(a["ys"]); out["y-max"] = max(a["ys"])
    if a["xmins"] and a["xmaxs"]:
        out["x-min"] = min(a["xmins"]); out["x-max"] = max(a["xmaxs"])
    return out


def _hlines_record(args, kw):
    ys, xmins, xmaxs = broadcast(args[0], args[1], args[2])
    return {"type": "hlines", "ys": ys, "xmins": xmins, "xmaxs": xmaxs, "opts": kw}


add_artist(ArtistSpec(
    name="hlines",
    record=_hlines_record,
    xdomain=lambda a: a["xmins"] + a["xmaxs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_hlines(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_refline_legend_entries,
    data_attrs=_hlines_data_attrs,
))


# --- vlines ---

def _vlines_data_attrs(a):
    out = {"n": len(a["xs"])}
    if a["xs"]:
        out["x-min"] = min(a["xs"]); out["x-max"] = max(a["xs"])
    if a["ymins"] and a["ymaxs"]:
        out["y-min"] = min(a["ymins"]); out["y-max"] = max(a["ymaxs"])
    return out


def _vlines_record(args, kw):
    xs, ymins, ymaxs = broadcast(args[0], args[1], args[2])
    return {"type": "vlines", "xs": xs, "ymins": ymins, "ymaxs": ymaxs, "opts": kw}


add_artist(ArtistSpec(
    name="vlines",
    record=_vlines_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ymins"] + a["ymaxs"],
    draw=lambda a, ctx: _artist_vlines(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_refline_legend_entries,
    data_attrs=_vlines_data_attrs,
))
