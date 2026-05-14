"""Cookbook recipe: pair plot / scatter matrix.

Unlike most recipes, this one is *not* a registered artist — it's a
composition helper that builds an n × n grid of charts using plotlet's
`pt.grid([[...]])` subplot composer:
  - off-diagonal cells: scatter of variable i vs variable j
  - diagonal cells:     univariate histogram of variable i

The seaborn / pandas EDA staple. Showcases how plotlet's composition
algebra makes "many small multiples" recipes trivial.

API:
    pair_plot({"x": xs, "y": ys, "z": zs}, ...)

`vars` is a dict of {name: 1-D iterable}. All columns must share length.
"""

SUMMARY = 'EDA pair-plot: n × n grid of scatter + histogram cells, built via plotlet `grid()` composition.'

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list


def pair_plot(vars: dict, hue: list | None = None,
              scatter_size: int = 8, panel_size: int = 140,
              hist_bins: int = 20) -> "pt.Chart":
    """Build a pair-plot for `vars` (dict of name -> 1-D values).

    `hue` is an optional per-row category vector; matching rows get the
    same tab10 color in scatter cells. Returns the assembled chart so
    the caller can `.save_svg(...)` or `.title(...)` it.
    """
    names = list(vars.keys())
    series = {k: to_list(v) for k, v in vars.items()}
    n = len(names)
    rows = []
    for i, ni in enumerate(names):
        row = []
        for j, nj in enumerate(names):
            c = pt.chart(data_width=panel_size, data_height=panel_size)
            if i == j:
                c.hist(series[ni], bins=hist_bins)
            else:
                if hue is None:
                    c.scatter(series[nj], series[ni], s=scatter_size)
                else:
                    # Split by category and emit one scatter per group so
                    # the color cycle picks them up.
                    cats = []
                    by_cat = {}
                    for x, y, h in zip(series[nj], series[ni], hue):
                        if h not in by_cat:
                            cats.append(h); by_cat[h] = ([], [])
                        by_cat[h][0].append(x); by_cat[h][1].append(y)
                    for cat in cats:
                        xs, ys = by_cat[cat]
                        c.scatter(xs, ys, s=scatter_size, label=str(cat))
            # Only the outer cells get axis labels — interior is busy enough.
            if i == n - 1:
                c.xlabel(nj)
            else:
                c.xticks([])
            if j == 0:
                c.ylabel(ni)
            else:
                c.yticks([])
            row.append(c)
        rows.append(row)
    return pt.grid(rows)


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random, math
    random.seed(0)
    n = 200
    # Three correlated variables with a categorical hue.
    sepal_l = [random.gauss(5, 0.7) for _ in range(n)]
    sepal_w = [s * 0.5 + random.gauss(1, 0.3) for s in sepal_l]
    petal_l = [s * 1.2 - 3 + random.gauss(0, 0.5) for s in sepal_l]
    petal_w = [p * 0.4 + random.gauss(0, 0.2) for p in petal_l]
    species = ["A" if p < 1.0 else ("B" if p < 1.5 else "C") for p in petal_w]
    fig = pair_plot(
        {"sepal len": sepal_l, "sepal wid": sepal_w,
         "petal len": petal_l, "petal wid": petal_w},
        hue=species,
        panel_size=110,
    )
    return fig


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
