"""Shorthand for fill_between with a constant baseline (default 0). Records
into the same shape as fill_between (xs/y1/y2) and points draw straight
at fill_between's helper — no separate artist function needed. `base=`
is split out of opts so it's preserved across re-renders (record() is
called on every render against the stored kw dict).
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._artist_impl import _artist_fill_between
from ._shared import _xy_minmax, _bar_legend_entries


def _area_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["y1"]))
    out["base"] = a["base"]
    curve = a["opts"].get("curve")
    if curve and curve != "linear":
        out["curve"] = curve
    return out


def _area_record(args, kw):
    kw = dict(kw)
    base = kw.pop("base", 0)
    xs = to_list(args[0])
    ys = to_list(args[1])
    return {"type": "area", "xs": xs, "y1": ys, "y2": [base] * len(xs),
            "base": base, "opts": kw}


add_artist(ArtistSpec(
    name="area",
    record=_area_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: list(a["y1"]) + list(a["y2"]),
    draw=lambda a, ctx: _artist_fill_between(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_bar_legend_entries,
    data_attrs=_area_data_attrs,
))
