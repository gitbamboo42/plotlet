"""Frequency polygon — histogram drawn as a line through bin midpoints.

Better than overlaid `hist` calls when comparing two or more distributions
— no fill-blocking, no semi-transparent muddle. ggplot2's `geom_freqpoly`.

  c.freqpoly(values)                                 # wide-form
  c.freqpoly(data=df, x="col")                       # long-form
  c.freqpoly(data=df, x="col", hue="group")          # one polygon per hue

Multi-hue overlays share bin edges so the polygons are comparable.

Styling kwargs:
  bins=20         number of bins
  density=False   True normalises so area under each polygon is 1
  linewidth=1.6   stroke width
  label=None      legend label (single-series only)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list, long_form_1d, hue_color
from ..utils import _drop_nan
from .._spec import _LEGSPEC
from ..draw import polyline, segment


def _bin_one(vals, lo, hi, width, bins, density):
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
        return [c / total for c in counts]
    return counts


def _freqpoly_record(args, kw):
    kw = dict(kw)
    if "data" in kw or "x" in kw or "y" in kw:
        data_df = kw.pop("data", None)
        x_col = kw.pop("x", None)
        hue_col = kw.pop("hue", None)
        if data_df is None or x_col is None:
            raise TypeError(
                "freqpoly long-form requires data=, x= (hue= optional)."
            )
        hues, groups = long_form_1d(data_df, x_col, hue_col)
    else:
        hues = [None]
        groups = [to_list(args[0])]
    bins = kw.get("bins", 20)
    density = kw.get("density", False)
    groups = [_drop_nan(g) for g in groups]
    all_vals = [v for g in groups for v in g]
    if not all_vals:
        return {"type": "freqpoly", "hues": hues,
                "_centers_groups": [[] for _ in groups],
                "_heights_groups": [[] for _ in groups], "opts": kw}
    lo, hi = min(all_vals), max(all_vals)
    if lo == hi: hi = lo + 1
    width = (hi - lo) / bins
    centers = [lo + (i + 0.5) * width for i in range(bins)]
    heights_groups = [_bin_one(g, lo, hi, width, bins, density) for g in groups]
    centers_groups = [centers if g else [] for g in groups]
    return {"type": "freqpoly", "hues": hues,
            "_centers_groups": centers_groups,
            "_heights_groups": heights_groups,
            "_lo": lo, "_hi": hi, "_w": width, "opts": kw}


def _freqpoly_xdomain(a):
    if not a["_centers_groups"] or not any(a["_centers_groups"]):
        return []
    return [a["_lo"], a["_hi"]]


def _freqpoly_ydomain(a):
    return [v for hs in a["_heights_groups"] for v in hs] + [0]


def _freqpoly_draw(a, ctx):
    palette = a["opts"].get("palette")
    lw = a["opts"].get("linewidth", 1.6)
    out = []
    for j, (centers, heights) in enumerate(zip(a["_centers_groups"],
                                                a["_heights_groups"])):
        if not centers: continue
        col = hue_color(a["hues"], palette, j, ctx.color)
        xs = [a["_lo"] - a["_w"] / 2] + centers + [a["_hi"] + a["_w"] / 2]
        ys = [0] + list(heights) + [0]
        pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(xs, ys)]
        out.append(polyline(pts, color=col, width=lw))
    return "".join(out)


def _freqpoly_legend_entries(a):
    hues = a["hues"]
    opts = a["opts"]
    lw = opts.get("linewidth", 1.6)
    sw = _LEGSPEC["swatch_width"]
    if hues == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(a, ctx, x0, y_mid):
            return segment(x0, y_mid, x0 + sw, y_mid,
                           color=a["_color"], width=lw)
        return [{"label": label, "color": a.get("_color"), "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return segment(x0, y_mid, x0 + sw, y_mid, color=_col, width=lw)
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="freqpoly",
    record=_freqpoly_record,
    xdomain=_freqpoly_xdomain,
    ydomain=_freqpoly_ydomain,
    draw=_freqpoly_draw,
    legend_entries=_freqpoly_legend_entries,
    force_zero_y=True,
))
