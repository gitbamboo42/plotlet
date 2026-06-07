"""Rug plot — short tick marks along an axis showing where each observation sits.

No-bin alternative (or companion) to a histogram. Pairs especially well
with `density_1d` to show both the smoothed estimate and the raw
observations.

  c.rug(values, axis="x")                       # wide-form
  c.rug(data=df, x="col")                       # long-form
  c.rug(data=df, x="col", color="group")        # ticks colored per group

Aesthetics:
  color=         tick color (literal) or column name → grouped ticks
  palette=       maps group levels → colors when `color=` is a column

Other styling kwargs:
  axis='x'       'y' draws ticks along the left axis instead
  length=0.04    tick length as a fraction of axis pixel extent
  alpha=0.6      tick opacity
  linewidth=0.8  tick stroke width
"""
import math

from ..registry import ArtistSpec, add_artist
from ..draw import segment
from ..utils import to_list, long_form_1d, resolve_aes, palette_color
from ..draw import TAB10, resolve_color


def _rug_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "rug requires long-form input: "
            "c.rug(data=df, x='col')."
        )
    data_df = kw.pop("data", None)
    x_col = kw.pop("x", None)
    if data_df is None or x_col is None:
        raise TypeError(
            "rug requires data=, x= (color= optional)."
        )
    color = kw.pop("color", None)
    color_kind, color_value = resolve_aes(data_df, color)
    group_col = color if color_kind == "column" else None
    groups, vals = long_form_1d(data_df, x_col, group_col)
    if color_kind == "literal" and color_value is not None:
        kw["_color_literal"] = color_value
    return {"type": "rug", "groups": groups, "vals": vals, "opts": kw}


def _rug_axis(a): return a["opts"].get("axis", "x")


def _rug_xdomain(a):
    if _rug_axis(a) != "x": return None
    return [v for g in a["vals"] for v in g]


def _rug_ydomain(a):
    if _rug_axis(a) != "y": return None
    return [v for g in a["vals"] for v in g]


def _group_color(groups, palette, j, fallback):
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def _rug_draw(a, ctx):
    palette = a["opts"].get("palette")
    lw = a["opts"].get("linewidth", 0.8)
    alpha = a["opts"].get("alpha", 0.6)
    length = a["opts"].get("length", 0.04)
    color_literal = resolve_color(a["opts"].get("_color_literal"))
    fallback = color_literal if color_literal is not None else ctx.color
    axis = _rug_axis(a)
    out = []
    for j, vals in enumerate(a["vals"]):
        col = _group_color(a["groups"], palette, j, fallback)
        if axis == "x":
            y_base = ctx.ih
            y_top = y_base - length * ctx.ih
            for v in vals:
                if isinstance(v, float) and math.isnan(v):
                    continue
                px = ctx.x_scale(v)
                out.append(segment(px, y_base, px, y_top,
                                   color=col, width=lw, alpha=alpha))
        else:
            x_base = 0
            x_right = length * ctx.iw
            for v in vals:
                if isinstance(v, float) and math.isnan(v):
                    continue
                py = ctx.y_scale(v)
                out.append(segment(x_base, py, x_right, py,
                                   color=col, width=lw, alpha=alpha))
    return "".join(out)


add_artist(ArtistSpec(
    name="rug",
    accepts_data_positional=True,
    record=_rug_record,
    xdomain=_rug_xdomain,
    ydomain=_rug_ydomain,
    draw=_rug_draw,
    layer="foreground",
))
