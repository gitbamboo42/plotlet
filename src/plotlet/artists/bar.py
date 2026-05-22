"""Bar contributes its categories on x; the descriptor's auto-categorical
detection picks them up the same way it would for any string-valued x."""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._artist_impl import _artist_bar
from ._shared import _bar_legend_entries


def _bar_data_attrs(a):
    fvals = [v for v in a["vals"] if isinstance(v, (int, float)) and v == v]
    out = {"n": len(a["cats"])}
    if fvals:
        out["y-min"] = min(fvals)
        out["y-max"] = max(fvals)
    return out


def _bar_horizontal(a): return a["opts"].get("orientation") == "h"
def _bar_vals_domain(a):
    return list(a["vals"]) + [0, a["opts"].get("bottom", 0)]
def _bar_xdomain(a): return _bar_vals_domain(a) if _bar_horizontal(a) else a["cats"]
def _bar_ydomain(a): return a["cats"] if _bar_horizontal(a) else _bar_vals_domain(a)


add_artist(ArtistSpec(
    name="bar",
    record=lambda args, kw: {"type": "bar", "cats": to_list(args[0]),
                              "vals": to_list(args[1]), "opts": kw},
    xdomain=_bar_xdomain,
    ydomain=_bar_ydomain,
    draw=lambda a, ctx: _artist_bar(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_bar_legend_entries,
    data_attrs=_bar_data_attrs,
    force_zero_y=lambda a: not _bar_horizontal(a),
    force_zero_x=_bar_horizontal,
))
