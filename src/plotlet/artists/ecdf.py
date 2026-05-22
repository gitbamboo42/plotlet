"""Empirical CDF as a step function — no bin choice, every observation visible.

F̂(x) = (#{xi ≤ x}) / n as a step function. ECDFs are the statistician-preferred
alternative to histograms: no bin choice, no smoothing, every observation
visible — overlaying multiple groups makes distribution differences obvious.

API: c.ecdf(values, complement=False)

Styling kwargs:
  complement=False   True draws 1 - F̂(x) (survival function)
  linewidth=1.5      stroke width
  label=None         legend label (no legend entry when absent)
"""
from ..registry import ArtistSpec, add_artist
from ..draw import polyline, segment
from ..utils import to_list


def _ecdf_record(args, kw):
    data = sorted(to_list(args[0]))
    return {"type": "ecdf", "data": data, "opts": kw}


def _ecdf_xdomain(a): return a["data"]
def _ecdf_ydomain(a): return [0, 1]


def _ecdf_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.5)
    complement = a["opts"].get("complement", False)
    n = len(a["data"])
    if n == 0:
        return ""
    pts = []
    prev_y = 1 if complement else 0
    pts.append((ctx.x_scale(a["data"][0]), ctx.y_scale(prev_y)))
    for i, x in enumerate(a["data"], start=1):
        f = i / n
        y = (1 - f) if complement else f
        px = ctx.x_scale(x)
        pts.append((px, ctx.y_scale(prev_y)))
        pts.append((px, ctx.y_scale(y)))
        prev_y = y
    return polyline(pts, color=col, width=lw)


def _ecdf_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(_a, _ctx, _x0, _y_mid):
        col = _a.get("_color", _ctx.color)
        return segment(_x0, _y_mid, _x0 + 22, _y_mid, color=col, width=1.5)
    return [{"label": label, "color": None, "paint": paint}]


add_artist(ArtistSpec(
    name="ecdf",
    record=_ecdf_record,
    xdomain=_ecdf_xdomain,
    ydomain=_ecdf_ydomain,
    draw=_ecdf_draw,
    legend_entries=_ecdf_legend_entries,
))
