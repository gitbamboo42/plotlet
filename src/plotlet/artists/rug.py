"""Rug plot — short tick marks along an axis showing where each observation sits.

No-bin alternative (or companion) to a histogram. Pairs especially well
with `density_1d` to show both the smoothed estimate and the raw
observations.

  c.rug(values, axis="x")                       # wide-form
  c.rug(data=df, x="col")                       # long-form
  c.rug(data=df, x="col", hue="group")          # ticks coloured per hue

Styling kwargs:
  axis='x'       'y' draws ticks along the left axis instead
  length=0.04    tick length as a fraction of axis pixel extent
  alpha=0.6      tick opacity
  linewidth=0.8  tick stroke width
"""
from ..registry import ArtistSpec, add_artist
from ..draw import segment
from ..utils import to_list, long_form_1d, hue_color


def _rug_record(args, kw):
    kw = dict(kw)
    if "data" in kw or "x" in kw or "y" in kw:
        data_df = kw.pop("data", None)
        x_col = kw.pop("x", None)
        hue_col = kw.pop("hue", None)
        if data_df is None or x_col is None:
            raise TypeError(
                "rug long-form requires data=, x= (hue= optional)."
            )
        hues, groups = long_form_1d(data_df, x_col, hue_col)
    else:
        hues = [None]
        groups = [to_list(args[0])]
    return {"type": "rug", "hues": hues, "groups": groups, "opts": kw}


def _rug_axis(a): return a["opts"].get("axis", "x")


def _rug_xdomain(a):
    if _rug_axis(a) != "x": return None
    return [v for g in a["groups"] for v in g]


def _rug_ydomain(a):
    if _rug_axis(a) != "y": return None
    return [v for g in a["groups"] for v in g]


def _rug_draw(a, ctx):
    palette = a["opts"].get("palette")
    lw = a["opts"].get("linewidth", 0.8)
    alpha = a["opts"].get("alpha", 0.6)
    length = a["opts"].get("length", 0.04)
    axis = _rug_axis(a)
    out = []
    for j, vals in enumerate(a["groups"]):
        col = hue_color(a["hues"], palette, j, ctx.color)
        if axis == "x":
            y_base = ctx.ih
            y_top = y_base - length * ctx.ih
            for v in vals:
                px = ctx.x_scale(v)
                out.append(segment(px, y_base, px, y_top,
                                   color=col, width=lw, alpha=alpha))
        else:
            x_base = 0
            x_right = length * ctx.iw
            for v in vals:
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
