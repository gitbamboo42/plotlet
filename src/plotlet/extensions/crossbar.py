"""Custom artist: crossbar.

Three horizontal lines per category — middle (median or mean), upper, and
lower — forming a flat "I". The `geom_crossbar` from ggplot2: a clean
"summary mark" to layer over a strip / swarm so you see the raw points
plus the central tendency and spread without the visual weight of a
full boxplot.

API:
    c.crossbar(cats, mids, lowers, uppers, width=0.5, lw_mid=2.2, lw_outer=1.2)
"""

SUMMARY = "Three horizontal lines (lo / mid / hi) per category — clean summary overlay over strips/swarms."

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import segment


def crossbar_record(args, kw):
    cats = to_list(args[0])
    mids = to_list(args[1])
    lows = to_list(args[2])
    his = to_list(args[3])
    return {"type": "crossbar", "cats": cats, "mids": mids, "los": lows,
            "his": his, "opts": kw}


def crossbar_xdomain(a): return a["cats"]


def crossbar_ydomain(a):
    return list(a["mids"]) + list(a["los"]) + list(a["his"])


def crossbar_draw(a, ctx):
    col = ctx.color
    bw_frac = a["opts"].get("width", 0.5)
    lw_mid = a["opts"].get("lw_mid", 2.2)
    lw_outer = a["opts"].get("lw_outer", 1.2)
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    half_w = band * bw_frac / 2
    out = []
    for cat, m, lo, hi in zip(a["cats"], a["mids"], a["los"], a["his"]):
        cx = ctx.x_scale(cat)
        py_m = ctx.y_scale(m)
        py_lo = ctx.y_scale(lo); py_hi = ctx.y_scale(hi)
        x_l = cx - half_w; x_r = cx + half_w
        # Two outer + one inner horizontal line.
        out.append(
            segment(x_l, py_lo, x_r, py_lo, color=col, width=lw_outer)
            + segment(x_l, py_hi, x_r, py_hi, color=col, width=lw_outer)
            + segment(x_l, py_m, x_r, py_m, color=col, width=lw_mid)
        )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="crossbar",
    record=crossbar_record,
    xdomain=crossbar_xdomain,
    ydomain=crossbar_ydomain,
    draw=crossbar_draw,
    layer="foreground",
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    cats = ["A", "B", "C", "D"]
    groups = [
        [random.gauss(3, 0.6) for _ in range(40)],
        [random.gauss(4.5, 0.7) for _ in range(40)],
        [random.gauss(5.2, 0.5) for _ in range(40)],
        [random.gauss(6.0, 0.9) for _ in range(40)],
    ]
    means = [sum(g) / len(g) for g in groups]
    sds = [(sum((x - m) ** 2 for x in g) / len(g)) ** 0.5
           for g, m in zip(groups, means)]
    los = [m - sd for m, sd in zip(means, sds)]
    his = [m + sd for m, sd in zip(means, sds)]
    c = pt.chart()
    c.xscale("category", order=cats)
    # Imagine a strip plot under it; we just demo the crossbar here.
    c.crossbar(cats, means, los, his, color="#222")
    c.title("Mean ± SD (crossbar)").ylabel("value")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
