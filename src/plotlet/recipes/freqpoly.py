"""Custom artist: frequency polygon.

A frequency polygon is a histogram drawn as a line through the bin
midpoints (with the line dropping to zero at the outer edges). Better
than overlaid `hist` calls when comparing two or more distributions —
no fill-blocking, no semi-transparent muddle.

ggplot2's `geom_freqpoly`.

API:
    c.freqpoly(values, bins=20, density=False)

`density=True` normalizes so the *area* under the polygon is 1 (handy
for comparing distributions of different sample sizes).
"""

SUMMARY = 'Histogram drawn as a line through bin midpoints — cleaner than overlaid hist calls.'

from pathlib import Path

import plotlet as pt
from plotlet.draw import polyline, segment
from plotlet.utils import to_list


def freqpoly_record(args, kw):
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


def freqpoly_xdomain(a):
    return [a["_lo"], a["_hi"]] if a["_centers"] else []


def freqpoly_ydomain(a): return list(a["_heights"]) + [0]


def freqpoly_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.6)
    if not a["_centers"]:
        return ""
    # Add zero anchors at outer edges so the line meets the baseline.
    xs = [a["_lo"] - a["_w"] / 2] + a["_centers"] + [a["_hi"] + a["_w"] / 2]
    ys = [0] + list(a["_heights"]) + [0]
    pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(xs, ys)]
    return polyline(pts, color=col, width=lw)


def freqpoly_legend_swatch(a, ctx, x0, y_mid):
    return segment(x0, y_mid, x0 + 22, y_mid, color=a["_color"], width=1.6)


pt.add_artist(pt.ArtistSpec(
    name="freqpoly",
    record=freqpoly_record,
    xdomain=freqpoly_xdomain,
    ydomain=freqpoly_ydomain,
    draw=freqpoly_draw,
    legend_entries=pt.legend_from_swatch(freqpoly_legend_swatch),
    force_zero_y=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    a = [random.gauss(0, 1) for _ in range(400)]
    b = [random.gauss(1, 1.4) for _ in range(400)]
    c = pt.chart()
    c.freqpoly(a, bins=25, label="control")
    c.freqpoly(b, bins=25, label="treatment")
    c.title("Frequency polygon").xlabel("value").ylabel("count").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
