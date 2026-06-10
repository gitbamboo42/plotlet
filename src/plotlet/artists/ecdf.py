"""Empirical CDF as a step function — no bin choice, every observation visible.

F̂(x) = (#{xi ≤ x}) / n as a step function. ECDFs are the statistician-
preferred alternative to histograms: no bin choice, no smoothing, every
observation visible — overlaying multiple groups makes distribution
differences obvious.

  c.ecdf(data=df, x="col")                      # long-form
  c.ecdf(data=df, x="col", color="group")       # one curve per group

Aesthetics:
  color=         line color (literal) or column name → grouped curves
  palette=       maps group levels → colors when `color=` is a column

Other styling kwargs:
  complement=False   True draws 1 - F̂(x) (survival function)
  linewidth=1.5      stroke width
  label=None         legend label (single-series only)
"""
from ..registry import ArtistSpec, add_artist
from ..draw import polyline, segment
from ..utils import to_list, long_form_1d, resolve_aes, palette_color
from ..draw import TAB10, resolve_color
from .._spec import _LEGSPEC


def _ecdf_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "ecdf requires long-form input: "
            "c.ecdf(data=df, x='col')."
        )
    data_df = kw.pop("data", None)
    x_col = kw.pop("x", None)
    if data_df is None or x_col is None:
        raise TypeError(
            "ecdf requires data=, x= (color= optional)."
        )
    color = kw.pop("color", None)
    color_kind, color_value = resolve_aes(data_df, color)
    group_col = color if color_kind == "column" else None
    groups, vals = long_form_1d(data_df, x_col, group_col)
    if color_kind == "literal" and color_value is not None:
        kw["_color_literal"] = color_value
    vals = [sorted(g) for g in vals]
    return {"type": "ecdf", "groups": groups, "vals": vals, "opts": kw}


def _ecdf_xdomain(a):
    return [v for g in a["vals"] for v in g]


def _ecdf_ydomain(a): return [0, 1]


def _group_color(groups, palette, j, fallback):
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def _ecdf_draw(a, ctx):
    palette = a["opts"].get("palette")
    lw = a["opts"].get("linewidth", 1.5)
    complement = a["opts"].get("complement", False)
    color_literal = resolve_color(a["opts"].get("_color_literal"))
    fallback = color_literal if color_literal is not None else ctx.color
    out = []
    for j, data in enumerate(a["vals"]):
        n = len(data)
        if n == 0: continue
        col = _group_color(a["groups"], palette, j, fallback)
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
    groups = a["groups"]
    opts = a["opts"]
    lw = opts.get("linewidth", 1.5)
    sw = _LEGSPEC["swatch_width"]
    if groups == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            col = _a.get("_color", _ctx.color)
            return segment(x0, y_mid, x0 + sw, y_mid, color=col, width=lw)
        return [{"label": label, "color": None, "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, g in enumerate(groups):
        col = _group_color(groups, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return segment(x0, y_mid, x0 + sw, y_mid, color=_col, width=lw)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="ecdf",
    record=_ecdf_record,
    xdomain=_ecdf_xdomain,
    ydomain=_ecdf_ydomain,
    draw=_ecdf_draw,
    legend_entries=_ecdf_legend_entries,
))
