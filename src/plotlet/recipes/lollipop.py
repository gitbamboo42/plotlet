"""Custom artist: lollipop chart.

A lollipop is a stem from y=0 to y=value with a circle at the top — useful
for sparse comparisons (rankings, deltas, GWAS-style hits).

The whole recipe is below: no edits to plotlet's source. After registration,
`c.lollipop(xs, ys, ...)` Just Works on any `Chart` — autoscaling, gridlines,
color cycling, and the legend integrate for free. The optional
`legend_swatch` hook lets the legend entry actually look like a tiny
lollipop instead of the default colored line.
"""

SUMMARY = 'Stem-and-circle chart for sparse comparisons; optional mini-lollipop legend swatch.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import segment, circle


# 1. record(): turn args/kwargs into the artist dict stored in Chart._calls.
def lollipop_record(args, kw):
    return {
        "type": "lollipop",
        "xs": to_list(args[0]),
        "ys": to_list(args[1]),
        "opts": kw,
    }


# 2. xdomain / ydomain: contribute to autoscaling. Lollipops always include
#    0 on y so the stems are visible.
def lollipop_xdomain(a): return a["xs"]
def lollipop_ydomain(a): return list(a["ys"]) + [0]


# 3. draw(): emit SVG. ctx carries scales, dimensions, color, defaults.
def lollipop_draw(a, ctx):
    out = []
    y0 = ctx.y_scale(0)
    head_r = a["opts"].get("size", 5)
    lw = a["opts"].get("linewidth", 1.5)
    col = ctx.color
    for x, y in zip(a["xs"], a["ys"]):
        px = ctx.x_scale(x); py = ctx.y_scale(y)
        out.append(segment(px, y0, px, py, color=col, width=lw))
        out.append(circle(px, py, head_r, fill=col))
    return "".join(out)


# 4. (optional) legend_swatch(): draw a mini lollipop in the legend swatch
#    area instead of the default colored line. Without this, the legend
#    falls back to a small line segment in the artist's color.
def lollipop_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (
        segment(x0 + 11, y_mid + 5, x0 + 11, y_mid - 4, color=col, width=1.5)
        + circle(x0 + 11, y_mid - 4, 3.5, fill=col)
    )


# Register. After this line, every Chart has a .lollipop() method.
pt.add_artist(pt.ArtistSpec(
    name="lollipop",
    record=lollipop_record,
    xdomain=lollipop_xdomain,
    ydomain=lollipop_ydomain,
    draw=lollipop_draw,
    legend_swatch=lollipop_legend_swatch,
    force_zero_y=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    c = pt.chart()
    c.lollipop([1, 2, 3, 4, 5, 6, 7], [3, 7, 2, 9, 4, 8, 5], label="A")
    c.lollipop([1.3, 2.3, 3.3, 4.3, 5.3, 6.3, 7.3], [5, 3, 8, 2, 6, 4, 7],
               label="B", size=4)
    c.title("Lollipop chart").xlabel("position").ylabel("score")
    c.grid(True).legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
