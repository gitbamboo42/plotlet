from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._artist_impl import _artist_fill_between
from ._shared import _xy_minmax, _line_legend_entries


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
