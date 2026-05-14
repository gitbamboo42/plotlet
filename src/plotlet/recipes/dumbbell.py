"""Custom artist: dumbbell chart.

Two values per category — a "before" point and an "after" point — connected
by a line, with optional color encoding of the direction of change. The
go-to plot for "how did X change between two time points" or "method A vs
method B" comparisons. Easier to read than a paired bar chart for many
categories.

API:
    c.dumbbell(labels, a_vals, b_vals,
               a_color="#1f77b4", b_color="#ff7f0e",
               up_color="#2ca02c", down_color="#d62728",
               size=4)

`labels` go on the y axis (categorical); `a_vals` and `b_vals` are
numeric. The connector picks `up_color` if `b > a`, `down_color` if
`b < a`. Set `c.yscale("category", order=labels)` to keep the rows in
your supplied order (alphabetical default is rarely what you want here);
plotlet places the first category at the *top* of the y axis.
"""

SUMMARY = 'Categorical before/after: two dots connected by a line per row, color-coded by direction.'

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list


def dumbbell_record(args, kw):
    labels = to_list(args[0])
    a = to_list(args[1])
    b = to_list(args[2])
    return {"type": "dumbbell", "labels": labels, "a": a, "b": b, "opts": kw}


def dumbbell_xdomain(a): return list(a["a"]) + list(a["b"])
def dumbbell_ydomain(a): return a["labels"]


def dumbbell_draw(a, ctx):
    a_col = a["opts"].get("a_color", "#1f77b4")
    b_col = a["opts"].get("b_color", "#ff7f0e")
    up_col = a["opts"].get("up_color", "#2ca02c")
    down_col = a["opts"].get("down_color", "#d62728")
    r = a["opts"].get("size", 4)
    lw = a["opts"].get("linewidth", 2)
    out = []
    for label, av, bv in zip(a["labels"], a["a"], a["b"]):
        py = ctx.y_scale(label)
        ax = ctx.x_scale(av); bx = ctx.x_scale(bv)
        line_col = up_col if bv > av else (down_col if bv < av else "#888")
        out.append(
            f'<line x1="{ax:.2f}" x2="{bx:.2f}" y1="{py:.2f}" y2="{py:.2f}" '
            f'stroke="{line_col}" stroke-width="{lw}"/>'
        )
        out.append(
            f'<circle cx="{ax:.2f}" cy="{py:.2f}" r="{r}" fill="{a_col}"/>'
            f'<circle cx="{bx:.2f}" cy="{py:.2f}" r="{r}" fill="{b_col}"/>'
        )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="dumbbell",
    record=dumbbell_record,
    xdomain=dumbbell_xdomain,
    ydomain=dumbbell_ydomain,
    draw=dumbbell_draw,
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    countries = ["USA", "UK", "Germany", "France", "Japan", "Brazil",
                 "India", "China", "Mexico", "Indonesia"]
    year_a = [70, 68, 72, 71, 78, 65, 60, 67, 69, 62]
    year_b = [78, 75, 81, 80, 83, 72, 72, 79, 75, 70]
    c = pt.chart()
    c.yscale("category", order=countries)
    c.dumbbell(countries, year_a, year_b)
    c.title("Life expectancy: 1980 → 2020").xlabel("years")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
