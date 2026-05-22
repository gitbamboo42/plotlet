import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from ..draw import marker
from .._spec import _LEGSPEC
from .._artist_impl import _artist_scatter
from ._shared import _xy_minmax


def _scatter_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _scatter_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        # When `s` or `marker` is per-point (size=/style= mappings), the legend
        # swatch picks the median size and the first marker so the entry stays
        # a single recognizable glyph.
        raw_s = a["opts"].get("s", ctx.defaults["scatter_s"])
        raw_mk = a["opts"].get("marker", "o")
        s_val = sorted(raw_s)[len(raw_s) // 2] if isinstance(raw_s, (list, tuple)) and raw_s else (
            raw_s if not isinstance(raw_s, (list, tuple)) else ctx.defaults["scatter_s"])
        mk_val = raw_mk[0] if isinstance(raw_mk, (list, tuple)) and raw_mk else (
            raw_mk if not isinstance(raw_mk, (list, tuple)) else "o")
        s_size = math.sqrt(s_val) / 2
        return marker(mk_val, x0 + sw / 2, y_mid, s_size, a["_color"],
                      a["opts"].get("alpha", ctx.defaults["scatter_alpha"]))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="scatter",
    record=lambda args, kw: {"type": "scatter", "xs": to_list(args[0]),
                              "ys": to_list(args[1]), "opts": kw},
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_scatter(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_scatter_legend_entries,
    data_attrs=_scatter_data_attrs,
))
