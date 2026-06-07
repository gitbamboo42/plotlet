"""Custom artist: lollipop chart.

A lollipop is a stem from y=0 to y=value with a circle at the top — useful
for sparse comparisons (rankings, deltas, GWAS-style hits).

The whole recipe is below: no edits to plotlet's source. After registration,
`c.lollipop(data=df, x="col", y="col")` Just Works on any `Chart` —
autoscaling, gridlines, color cycling, and the legend integrate for free.
The optional `legend_entries` hook lets the legend entry actually look
like a tiny lollipop instead of the default colored line.
"""

SUMMARY = 'Stem-and-circle chart for sparse comparisons; optional mini-lollipop legend entry.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import segment, circle


# 1. record(): turn args/kwargs into the artist dict stored in Chart._calls.
def lollipop_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "lollipop requires long-form input: "
            "c.lollipop(data=df, x='col', y='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError("lollipop requires data=, x=, y=.")
    return {
        "type": "lollipop",
        "xs": to_list(data[x_col]),
        "ys": to_list(data[y_col]),
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


# 4. (optional) legend_entries(): draw a mini lollipop in the legend swatch
#    area instead of the default colored line. Without this, the legend
#    falls back to a small line segment in the artist's color.
def lollipop_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        col = a["_color"]
        return (
            segment(x0 + 11, y_mid + 5, x0 + 11, y_mid - 4, color=col, width=1.5)
            + circle(x0 + 11, y_mid - 4, 3.5, fill=col)
        )
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


# Register. After this line, every Chart has a .lollipop() method.
pt.add_artist(pt.ArtistSpec(
    name="lollipop",
    record=lollipop_record,
    xdomain=lollipop_xdomain,
    ydomain=lollipop_ydomain,
    draw=lollipop_draw,
    legend_entries=lollipop_legend_entries,
    force_zero_y=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    c = pt.chart()
    a = {"x": [1, 2, 3, 4, 5, 6, 7], "y": [3, 7, 2, 9, 4, 8, 5]}
    b = {"x": [1.3, 2.3, 3.3, 4.3, 5.3, 6.3, 7.3], "y": [5, 3, 8, 2, 6, 4, 7]}
    c.lollipop(a, x="x", y="y", label="A")
    c.lollipop(b, x="x", y="y", label="B", size=4)
    c.title("Lollipop chart").xlabel("position").ylabel("score")
    c.grid(True).legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
