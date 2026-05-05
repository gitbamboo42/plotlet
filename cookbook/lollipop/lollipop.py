"""Custom artist: lollipop chart.

A lollipop is a stem from y=0 to y=value with a circle at the top — useful
for sparse comparisons (rankings, deltas, GWAS-style hits).

The whole recipe is below: no edits to plotlet's source. After registration,
`fig.lollipop(xs, ys, ...)` Just Works — autoscaling, gridlines, color
cycling, and the legend integrate for free. The optional `legend_swatch`
hook lets the legend entry actually look like a tiny lollipop instead of
the default colored line.
"""
from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist


# 1. record(): turn args/kwargs into the artist dict stored in Figure._calls.
def lollipop_record(args, kw):
    return {
        "type": "lollipop",
        "xs": _to_pylist(args[0]),
        "ys": _to_pylist(args[1]),
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
        out.append(
            f'<line x1="{px:.2f}" x2="{px:.2f}" y1="{y0:.2f}" y2="{py:.2f}" '
            f'stroke="{col}" stroke-width="{lw}"/>'
        )
        out.append(
            f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{head_r}" fill="{col}"/>'
        )
    return "".join(out)


# 4. (optional) legend_swatch(): draw a mini lollipop in the legend swatch
#    area instead of the default colored line. Without this, the legend
#    falls back to a small line segment in the artist's color.
def lollipop_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (
        f'<line x1="{x0 + 11}" x2="{x0 + 11}" y1="{y_mid + 5}" y2="{y_mid - 4}" '
        f'stroke="{col}" stroke-width="1.5"/>'
        f'<circle cx="{x0 + 11}" cy="{y_mid - 4}" r="3.5" fill="{col}"/>'
    )


# Register. After this line, every Figure instance has a .lollipop() method.
pt.add_artist(pt.ArtistSpec(
    name="lollipop",
    record=lollipop_record,
    xdomain=lollipop_xdomain,
    ydomain=lollipop_ydomain,
    draw=lollipop_draw,
    legend_swatch=lollipop_legend_swatch,
))


if __name__ == "__main__":
    fig = pt.figure()
    fig.lollipop([1, 2, 3, 4, 5, 6, 7], [3, 7, 2, 9, 4, 8, 5], label="A")
    fig.lollipop([1.3, 2.3, 3.3, 4.3, 5.3, 6.3, 7.3], [5, 3, 8, 2, 6, 4, 7],
                 label="B", size=4)
    fig.title("Lollipop chart").xlabel("position").ylabel("score")
    fig.grid(True).legend(True)
    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
