"""Frequency polygon — histogram drawn as a line through bin midpoints.

Better than overlaid `hist` calls when comparing two or more distributions
— no fill-blocking, no semi-transparent muddle. ggplot2's `geom_freqpoly`.

API: c.freqpoly(values, bins=20, density=False)

Styling kwargs:
  bins=20         number of bins
  density=False   True normalises so area under the polygon is 1
  linewidth=1.6   stroke width
  label=None      legend label (no legend entry when absent)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from ..draw import polyline, segment


def _freqpoly_record(args, kw):
    vals = to_list(args[0])
    bins = kw.get("bins", 20)
    density = kw.get("density", False)
    if not vals:
        return {"type": "freqpoly", "_centers": [], "_heights": [], "opts": kw}
    lo, hi = min(vals), max(vals)
    if lo == hi:
        hi = lo + 1
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        if v == hi:
            counts[-1] += 1
        else:
            i = int((v - lo) / width)
            if 0 <= i < bins:
                counts[i] += 1
    if density:
        total = sum(counts) * width or 1
        heights = [c / total for c in counts]
    else:
        heights = counts
    centers = [lo + (i + 0.5) * width for i in range(bins)]
    return {"type": "freqpoly", "_centers": centers, "_heights": heights,
            "_lo": lo, "_hi": hi, "_w": width, "opts": kw}


def _freqpoly_xdomain(a):
    return [a["_lo"], a["_hi"]] if a["_centers"] else []


def _freqpoly_ydomain(a):
    return list(a["_heights"]) + [0]


def _freqpoly_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.6)
    if not a["_centers"]:
        return ""
    xs = [a["_lo"] - a["_w"] / 2] + a["_centers"] + [a["_hi"] + a["_w"] / 2]
    ys = [0] + list(a["_heights"]) + [0]
    pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(xs, ys)]
    return polyline(pts, color=col, width=lw)


def _freqpoly_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        return segment(x0, y_mid, x0 + 22, y_mid, color=a["_color"], width=1.6)
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="freqpoly",
    record=_freqpoly_record,
    xdomain=_freqpoly_xdomain,
    ydomain=_freqpoly_ydomain,
    draw=_freqpoly_draw,
    legend_entries=_freqpoly_legend_entries,
    force_zero_y=True,
))
