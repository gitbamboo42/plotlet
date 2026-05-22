"""Rug plot: short tick marks along an axis showing where each observation sits.

No-bin alternative (or companion) to a histogram. Pairs especially well with
`density_1d` to show both the smoothed estimate and the raw observations.

API: c.rug(values, axis="x")

Styling kwargs:
  axis='x'       'y' draws ticks along the left axis instead
  length=0.04    tick length as a fraction of axis pixel extent
  alpha=0.6      tick opacity
  linewidth=0.8  tick stroke width
"""
from ..registry import ArtistSpec, add_artist
from ..draw import segment
from ..utils import to_list


def _rug_record(args, kw):
    return {"type": "rug", "vals": to_list(args[0]), "opts": kw}


def _rug_xdomain(a):
    return a["vals"] if a["opts"].get("axis", "x") == "x" else None


def _rug_ydomain(a):
    return a["vals"] if a["opts"].get("axis", "x") == "y" else None


def _rug_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 0.8)
    alpha = a["opts"].get("alpha", 0.6)
    length = a["opts"].get("length", 0.04)
    axis = a["opts"].get("axis", "x")
    out = []
    if axis == "x":
        y_base = ctx.ih
        y_top = y_base - length * ctx.ih
        for v in a["vals"]:
            px = ctx.x_scale(v)
            out.append(segment(px, y_base, px, y_top,
                               color=col, width=lw, alpha=alpha))
    else:
        x_base = 0
        x_right = length * ctx.iw
        for v in a["vals"]:
            py = ctx.y_scale(v)
            out.append(segment(x_base, py, x_right, py,
                               color=col, width=lw, alpha=alpha))
    return "".join(out)


add_artist(ArtistSpec(
    name="rug",
    record=_rug_record,
    xdomain=_rug_xdomain,
    ydomain=_rug_ydomain,
    draw=_rug_draw,
    layer="foreground",
))
