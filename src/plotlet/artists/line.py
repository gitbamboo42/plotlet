from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._artist_impl import _artist_line
from ._shared import _xy_minmax, _line_legend_entries


def _line_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    if a["opts"].get("linestyle"):
        out["linestyle"] = a["opts"]["linestyle"]
    if a["opts"].get("marker"):
        out["marker"] = a["opts"]["marker"]
    curve = a["opts"].get("curve")
    if curve and curve != "linear":
        out["curve"] = curve
    return out


add_artist(ArtistSpec(
    name="line",
    record=lambda args, kw: {"type": "line", "xs": to_list(args[0]),
                              "ys": to_list(args[1]), "opts": kw},
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_line(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_line_legend_entries,
    data_attrs=_line_data_attrs,
))
