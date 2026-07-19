"""Baseline SVG regression tests for the kde_2d artist/topic.

    pytest tests/test_chart_kde_2d.py
    pytest tests/test_chart_kde_2d.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_kde_2d():
    rng = random.Random(12)
    n = 200
    xs = ([rng.gauss(-1, 0.7) for _ in range(n)]
          + [rng.gauss(1.2, 1.0) for _ in range(n)])
    ys = ([rng.gauss(0, 1.0) for _ in range(n)]
          + [rng.gauss(2, 0.8) for _ in range(n)])
    c = pt.chart(data_width=300, data_height=260,
                 title="2-D KDE", xlabel="x", ylabel="y")
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y", size=1.2, alpha=0.25, color="#444444")
    c.kde_2d(data={"x": xs, "y": ys}, x="x", y="y", n_grid=40, cmap="viridis")
    c.legend()
    return c


def chart_kde_2d_filled_color():
    """kde_2d color= grouping: one single-colored filled density per level."""
    rng = random.Random(23)
    n = 150
    rows_x, rows_y, rows_g = [], [], []
    for g, (mx, my) in zip(["A", "B"], [(-1.0, 0.0), (1.3, 1.8)]):
        for _ in range(n):
            rows_x.append(rng.gauss(mx, 0.8))
            rows_y.append(rng.gauss(my, 0.7))
            rows_g.append(g)
    df = {"x": rows_x, "y": rows_y, "g": rows_g}
    c = pt.chart(data_width=300, data_height=260,
                 title="grouped 2-D KDE (filled)", xlabel="x", ylabel="y",
                 legend=True)
    c.kde_2d(data=df, x="x", y="y", color="g", fill=True, n_grid=40)
    c.legend()
    return c


PLOTS = {
    "kde_2d": chart_kde_2d,
    "kde_2d_filled_color": chart_kde_2d_filled_color,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_kde_2d_baseline(name, fn, baseline_compare):
    baseline_compare("chart_kde_2d", name, fn().to_svg())


def test_kde_2d_color_grouping():
    df = {"x": [0.0, 0.1, 0.2, 5.0, 5.1, 5.2],
          "y": [0.0, 0.1, 0.2, 5.0, 5.1, 5.2],
          "g": ["a", "a", "a", "b", "b", "b"]}
    c = pt.chart(df)
    c.kde_2d(x="x", y="y", color="g", n_grid=12)
    assert c.to_svg().count('data-plotlet-type="kde_2d"') == 2

    c = pt.chart(df)
    c.kde_2d(x="x", y="y", color="g", cmap="viridis")
    with pytest.raises(TypeError, match="palette="):
        c.to_svg()
