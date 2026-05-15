"""Custom artist: rug plot.

Short tick marks along an axis showing where each observation sits. The
no-bin alternative (or companion) to a histogram — pairs especially well
with `density_1d` to show both the smoothed estimate and the raw
observations underneath.

API:
    c.rug(values, axis="x", length=0.04, alpha=0.6, linewidth=0.8)

`axis="x"` draws ticks along the bottom; `axis="y"` along the left.
`length` is in *axis fraction* (so the tick height is independent of
the data range).
"""

SUMMARY = 'Short tick marks along an axis showing where each observation sits.'

from pathlib import Path

import plotlet as pt
from plotlet.draw import segment
from plotlet.utils import to_list


def rug_record(args, kw):
    return {"type": "rug", "vals": to_list(args[0]), "opts": kw}


def rug_xdomain(a):
    return a["vals"] if a["opts"].get("axis", "x") == "x" else None


def rug_ydomain(a):
    return a["vals"] if a["opts"].get("axis", "x") == "y" else None


def rug_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 0.8)
    alpha = a["opts"].get("alpha", 0.6)
    length = a["opts"].get("length", 0.04)
    axis = a["opts"].get("axis", "x")
    out = []
    if axis == "x":
        # Ticks rise from the bottom spine upward by `length` of ih.
        y_base = ctx.ih
        y_top = y_base - length * ctx.ih
        for v in a["vals"]:
            px = ctx.x_scale(v)
            out.append(segment(px, y_base, px, y_top,
                               color=col, width=lw, alpha=alpha))
    else:
        # Ticks extend right from the left spine.
        x_base = 0
        x_right = length * ctx.iw
        for v in a["vals"]:
            py = ctx.y_scale(v)
            out.append(segment(x_base, py, x_right, py,
                               color=col, width=lw, alpha=alpha))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="rug",
    record=rug_record,
    xdomain=rug_xdomain,
    ydomain=rug_ydomain,
    draw=rug_draw,
    layer="foreground",
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    vals = [random.gauss(0, 1) for _ in range(150)]
    c = pt.chart()
    c.hist(vals, bins=24)
    c.rug(vals, color="#444")
    c.title("Histogram with rug").xlabel("value").ylabel("count")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
