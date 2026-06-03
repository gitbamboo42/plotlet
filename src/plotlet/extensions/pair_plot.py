"""Cookbook recipe: pair plot / scatter matrix.

Unlike most recipes, this one is *not* a registered artist — it's a
composition helper that builds an n × n grid of charts using plotlet's
`pt.grid([[...]])` subplot composer:
  - off-diagonal cells: scatter of variable i vs variable j
  - diagonal cells:     univariate histogram of variable i

Showcases how plotlet's composition algebra makes "many small multiples"
recipes trivial.

API:
    pair_plot(df, color="species", palette={"A": "#3F97C5", ...})

`data` is a DataFrame or dict-of-columns ({name: 1-D iterable}); the
`color` column (if given) is excluded from the pair grid and used for
categorical coloring in scatter cells.
"""
from __future__ import annotations

SUMMARY = 'EDA pair-plot: n × n grid of scatter + histogram cells, built via plotlet `grid()` composition.'

from pathlib import Path

import plotlet as pt


def pair_plot(data, color: str | None = None, palette=None,
              scatter_size: int = 8, panel_size: int = 140,
              hist_bins: int = 20) -> "pt.Chart":
    """Build a pair-plot for the numeric columns of `data`.

    `color` is an optional column name; matching rows get the same color
    (and a categorical legend entry) in scatter cells. `palette=` pins
    categories to specific colors (forwarded to `c.scatter`)."""
    cols = list(data.columns) if hasattr(data, "columns") else list(data.keys())
    names = [c for c in cols if c != color]
    n = len(names)
    rows = []
    for i, ni in enumerate(names):
        row = []
        for j, nj in enumerate(names):
            c = pt.chart(data_width=panel_size, data_height=panel_size)
            if i == j:
                c.hist(x=ni, data=data, bins=hist_bins)
            elif color is None:
                c.scatter(x=nj, y=ni, data=data, s=scatter_size)
            else:
                c.scatter(x=nj, y=ni, color=color, palette=palette,
                          data=data, s=scatter_size)
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
    import random
    random.seed(0)
    n = 200
    # Three correlated variables with a categorical grouping column.
    sepal_l = [random.gauss(5, 0.7) for _ in range(n)]
    sepal_w = [s * 0.5 + random.gauss(1, 0.3) for s in sepal_l]
    petal_l = [s * 1.2 - 3 + random.gauss(0, 0.5) for s in sepal_l]
    petal_w = [p * 0.4 + random.gauss(0, 0.2) for p in petal_l]
    species = ["A" if p < 1.0 else ("B" if p < 1.5 else "C") for p in petal_w]
    fig = pair_plot(
        {"sepal len": sepal_l, "sepal wid": sepal_w,
         "petal len": petal_l, "petal wid": petal_w,
         "species": species},
        color="species",
        panel_size=110,
    )
    return fig


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
