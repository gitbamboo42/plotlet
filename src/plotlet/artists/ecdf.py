"""Empirical CDF as a step function — no bin choice, every observation visible.

F̂(x) = (#{xi ≤ x}) / n as a step function. ECDFs are the statistician-
preferred alternative to histograms: no bin choice, no smoothing, every
observation visible — overlaying multiple groups makes distribution
differences obvious.

  c.ecdf(values)                                # wide-form
  c.ecdf(data=df, x="col")                      # long-form
  c.ecdf(data=df, x="col", hue="group")         # one curve per hue

Styling kwargs:
  complement=False   True draws 1 - F̂(x) (survival function)
  linewidth=1.5      stroke width
  label=None         legend label (single-series only)
"""
from ..registry import ArtistSpec, add_artist
from ..draw import polyline, segment
from ..utils import to_list, long_form_1d, hue_color
from .._spec import _LEGSPEC


def _ecdf_record(args, kw):
    kw = dict(kw)
    if "data" in kw or "x" in kw or "y" in kw:
        data_df = kw.pop("data", None)
        x_col = kw.pop("x", None)
        hue_col = kw.pop("hue", None)
        if data_df is None or x_col is None:
            raise TypeError(
                "ecdf long-form requires data=, x= (hue= optional)."
            )
        hues, groups = long_form_1d(data_df, x_col, hue_col)
    else:
        hues = [None]
        groups = [to_list(args[0])]
    groups = [sorted(g) for g in groups]
    return {"type": "ecdf", "hues": hues, "groups": groups, "opts": kw}


def _ecdf_xdomain(a):
    return [v for g in a["groups"] for v in g]


def _ecdf_ydomain(a): return [0, 1]


def _ecdf_draw(a, ctx):
    palette = a["opts"].get("palette")
    lw = a["opts"].get("linewidth", 1.5)
    complement = a["opts"].get("complement", False)
    out = []
    for j, data in enumerate(a["groups"]):
        n = len(data)
        if n == 0: continue
        col = hue_color(a["hues"], palette, j, ctx.color)
        pts = []
        prev_y = 1 if complement else 0
        pts.append((ctx.x_scale(data[0]), ctx.y_scale(prev_y)))
        for i, x in enumerate(data, start=1):
            f = i / n
            y = (1 - f) if complement else f
            px = ctx.x_scale(x)
            pts.append((px, ctx.y_scale(prev_y)))
            pts.append((px, ctx.y_scale(y)))
            prev_y = y
        out.append(polyline(pts, color=col, width=lw))
    return "".join(out)


def _ecdf_legend_entries(a):
    hues = a["hues"]
    opts = a["opts"]
    lw = opts.get("linewidth", 1.5)
    sw = _LEGSPEC["swatch_width"]
    if hues == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            col = _a.get("_color", _ctx.color)
            return segment(x0, y_mid, x0 + sw, y_mid, color=col, width=lw)
        return [{"label": label, "color": None, "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return segment(x0, y_mid, x0 + sw, y_mid, color=_col, width=lw)
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="ecdf",
    record=_ecdf_record,
    xdomain=_ecdf_xdomain,
    ydomain=_ecdf_ydomain,
    draw=_ecdf_draw,
    legend_entries=_ecdf_legend_entries,
))
