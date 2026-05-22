"""Filled-region artists over x/y series.

`fill_between(xs, y1, y2)` fills between two curves. `area(xs, ys, base=0)`
is shorthand for fill_between with a constant baseline — same draw fn,
just a different recorder.
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._spec import _D
from ..draw import polygon as draw_polygon
from ._shared import (_xy_minmax, _line_legend_entries, _bar_legend_entries,
                       _CURVE_VALUES, _step_coords)


# --- fill_between ---

def _artist_fill_between(a, xs_, ys_, col):
    opts = a["opts"]
    curve = opts.get("curve", "linear")
    if curve not in _CURVE_VALUES:
        raise ValueError(
            f"unknown curve={curve!r}; expected one of {_CURVE_VALUES}"
        )
    # Apply step interleaving to both edges so the polygon zips correctly
    # — for constant baselines (area) this still interleaves x-coords,
    # which the upper edge needs to pair with.
    if curve == "linear":
        upper_xs, upper_ys = a["xs"], a["y1"]
        lower_xs, lower_ys = a["xs"], a["y2"]
    else:
        mode = curve[5:]
        upper_xs, upper_ys = _step_coords(a["xs"], a["y1"], mode)
        lower_xs, lower_ys = _step_coords(a["xs"], a["y2"], mode)
    upper = [(xs_(x), ys_(y)) for x, y in zip(upper_xs, upper_ys)]
    lower = [(xs_(x), ys_(y)) for x, y in zip(lower_xs, lower_ys)]
    pts = upper + list(reversed(lower))
    return draw_polygon(pts, fill=col,
                        alpha=opts.get("alpha", _D["fill_alpha"]))


def _fill_between_data_attrs(a):
    ys_all = list(a["y1"]) + list(a["y2"])
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], ys_all))
    curve = a["opts"].get("curve")
    if curve and curve != "linear":
        out["curve"] = curve
    return out


add_artist(ArtistSpec(
    name="fill_between",
    record=lambda args, kw: {"type": "fill_between",
                              "xs": to_list(args[0]),
                              "y1": to_list(args[1]),
                              "y2": to_list(args[2]),
                              "opts": kw},
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: list(a["y1"]) + list(a["y2"]),
    draw=lambda a, ctx: _artist_fill_between(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_line_legend_entries,
    data_attrs=_fill_between_data_attrs,
))


# --- area ---

def _area_record(args, kw):
    kw = dict(kw)
    base = kw.pop("base", 0)
    xs = to_list(args[0])
    ys = to_list(args[1])
    return {"type": "area", "xs": xs, "y1": ys, "y2": [base] * len(xs),
            "base": base, "opts": kw}


def _area_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["y1"]))
    out["base"] = a["base"]
    curve = a["opts"].get("curve")
    if curve and curve != "linear":
        out["curve"] = curve
    return out


add_artist(ArtistSpec(
    name="area",
    record=_area_record,
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: list(a["y1"]) + list(a["y2"]),
    draw=lambda a, ctx: _artist_fill_between(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_bar_legend_entries,
    data_attrs=_area_data_attrs,
))
