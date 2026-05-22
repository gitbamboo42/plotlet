from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._artist_impl import _artist_hist
from ._shared import _bar_legend_entries


def _bin_xs(a): return [b["x0"] for b in a["_bins"]] + [b["x1"] for b in a["_bins"]]
def _bin_ys(a): return [b["count"] for b in a["_bins"]] + [0]


def _hist_data_attrs(a):
    raw = a["data"]
    out = {"n": len(raw), "bins": len(a.get("_bins", [])) or a["opts"].get("bins", 10)}
    bins = a.get("_bins") or []
    if bins:
        out["x-min"] = bins[0]["x0"]
        out["x-max"] = bins[-1]["x1"]
        out["count-max"] = max(b["count"] for b in bins)
    return out


def _hist_horizontal(a): return a["opts"].get("orientation") == "h"
def _hist_xdomain(a): return _bin_ys(a) if _hist_horizontal(a) else _bin_xs(a)
def _hist_ydomain(a): return _bin_xs(a) if _hist_horizontal(a) else _bin_ys(a)


add_artist(ArtistSpec(
    name="hist",
    record=lambda args, kw: {"type": "hist", "data": to_list(args[0]), "opts": kw},
    xdomain=_hist_xdomain,
    ydomain=_hist_ydomain,
    draw=lambda a, ctx: _artist_hist(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_bar_legend_entries,
    data_attrs=_hist_data_attrs,
    force_zero_y=lambda a: not _hist_horizontal(a),
    force_zero_x=_hist_horizontal,
))
