"""Custom artist: dumbbell chart.

Two values per category — a "before" point and an "after" point — connected
by a line, with optional color encoding of the direction of change. The
go-to plot for "how did X change between two time points" or "method A vs
method B" comparisons. Easier to read than a paired bar chart for many
categories.

API:
    c.dumbbell(data=df, y="category_col", a="col", b="col",
               a_color="#1f77b4", b_color="#ff7f0e",
               up_color="#2ca02c", down_color="#d62728",
               size=4)

The `y=` column is categorical; `a=` and `b=` are numeric. The connector
picks `up_color` if `b > a`, `down_color` if `b < a`. Set
`c.yscale("category", order=...)` to keep the rows in your supplied order
(alphabetical default is rarely what you want here); plotlet places the
first category at the *top* of the y axis.
"""

SUMMARY = 'Categorical before/after: two dots connected by a line per row, color-coded by direction.'

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import segment, circle


def dumbbell_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "dumbbell requires long-form input: "
            "c.dumbbell(data=df, y='category_col', a='col', b='col')."
        )
    data = kw.pop("data", None)
    y_col = kw.pop("y", None)
    a_col = kw.pop("a", None)
    b_col = kw.pop("b", None)
    if data is None or y_col is None or a_col is None or b_col is None:
        raise TypeError("dumbbell requires data=, y=, a=, b=.")
    labels = to_list(data[y_col])
    a = to_list(data[a_col])
    b = to_list(data[b_col])
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
        out.append(segment(ax, py, bx, py, color=line_col, width=lw))
        out.append(
            circle(ax, py, r, fill=a_col)
            + circle(bx, py, r, fill=b_col)
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
    df = {"country": countries, "y1980": year_a, "y2020": year_b}
    c = pt.chart()
    c.yscale("category", order=countries)
    c.dumbbell(df, y="country", a="y1980", b="y2020")
    c.title("Life expectancy: 1980 → 2020").xlabel("years")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
