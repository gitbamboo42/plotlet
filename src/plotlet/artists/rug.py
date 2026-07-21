"""Rug plot — short tick marks along an axis showing where each observation sits.

No-bin alternative (or companion) to a histogram. Pairs especially well
with `density_1d` to show both the smoothed estimate and the raw
observations.

  c.add_rug(aes(x="col"))                       # columns via aes (orientation="y" too)
  c.add_rug(aes(x="col", color="group"))        # ticks colored per group

Aesthetics:
  color=         bare → literal tick color; aes(color="col") → grouped ticks
  palette=       maps group levels → colors when color is mapped in aes

Other styling kwargs:
  orientation='x'  'y' draws ticks along the left axis instead
  length=0.04    tick length as a fraction of axis pixel extent
  alpha=0.6      tick opacity
  linewidth=0.8  tick stroke width
"""
import math

from ..registry import ArtistSpec, add_artist
from ..draw import segment
from ..utils import to_list, long_form_1d, resolve_aes, pack_opts
from ..draw import resolve_color
from ..utils import group_color


def _rug_record(data=None, x=None, color=None,
                # style — packed into opts for the draw side
                orientation=None, palette=None, length=None,
                alpha=None, linewidth=None, label=None, legend=None):
    if data is None or x is None:
        raise TypeError(
            "rug requires data=, x= (color= optional)."
        )
    color_kind, color_value = resolve_aes(data, color)
    group_col = color if color_kind == "column" else None
    groups, vals = long_form_1d(data, x, group_col)
    opts = pack_opts(orientation=orientation, palette=palette, length=length,
                     alpha=alpha, linewidth=linewidth, label=label,
                     legend=legend)
    if color_kind == "literal" and color_value is not None:
        opts["_color_literal"] = color_value
    return {"type": "rug", "groups": groups, "vals": vals, "opts": opts}


def _rug_axis(a): return a["opts"].get("orientation", "x")


def _rug_xdomain(a):
    if _rug_axis(a) != "x": return None
    return [v for g in a["vals"] for v in g]


def _rug_ydomain(a):
    if _rug_axis(a) != "y": return None
    return [v for g in a["vals"] for v in g]


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
        col = group_color(a["groups"], palette, j, fallback)
        if axis == "x":
            y_base = ctx.ih
            y_top = y_base - length * ctx.ih
            for v in vals:
                if isinstance(v, float) and math.isnan(v):
                    continue
                px = ctx.x_scale(v)
                out.append(segment(px, y_base, px, y_top,
                                   color=col, width=lw, alpha=alpha,
                                   project=ctx.warp))
        else:
            x_base = 0
            x_right = length * ctx.iw
            for v in vals:
                if isinstance(v, float) and math.isnan(v):
                    continue
                py = ctx.y_scale(v)
                out.append(segment(x_base, py, x_right, py,
                                   color=col, width=lw, alpha=alpha,
                                   project=ctx.warp))
    return "".join(out)


add_artist(ArtistSpec(
    name="rug",
    record=_rug_record,
    xdomain=_rug_xdomain,
    ydomain=_rug_ydomain,
    draw=_rug_draw,
    layer="foreground",
))
