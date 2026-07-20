"""Baseline SVG regression tests for the scatter artist/topic.

    pytest tests/test_chart_scatter.py
    pytest tests/test_chart_scatter.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_scatter_color():
    rng = random.Random(0)
    n = 60
    df = {
        "x":     [rng.random() * 10 for _ in range(2 * n)],
        "y":     [rng.random() * 10 for _ in range(2 * n)],
        "group": ["A"] * n + ["B"] * n,
    }
    c = pt.chart(df, title="scatter color",
                 xlabel="x", ylabel="y", legend=True, gridlines=True)
    c.scatter(x="x", y="y", color="group", size=3, alpha=0.6)
    return c


def chart_clip_data_area():
    # clip=False with full spines so the bleeding is visible — most
    # markers sit inside the data area, but a handful near the
    # upper-right edges extend past the spines into the margin space.
    # The default clip=True crops those halves at the data boundary.
    random.seed(3)
    n = 24
    xs = [random.uniform(0.5, 9.5) for _ in range(n)]
    ys = [random.uniform(0.5, 9.5) for _ in range(n)]
    sizes = [random.uniform(7, 10) for _ in range(n)]
    # Deliberate bleeders along the upper-right edges.
    xs    += [9.7, 9.5, 9.8, 8.6, 7.4]
    ys    += [9.5, 9.8, 7.4, 9.7, 9.5]
    sizes += [13, 14, 13, 14, 13]
    c = pt.chart(data_width=320, data_height=240, clip=False,
                 title="clip=False",
                 xlabel="x", ylabel="y",
                 xlim=(0, 10), ylim=(0, 10))
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y", size=sizes, color="C0", alpha=0.6)
    return c


def chart_scatter_size():
    # size= maps a numeric column to per-point area.
    random.seed(1)
    df = {
        "x":    list(range(40)),
        "y":    [math.sin(i / 5) + random.uniform(-0.2, 0.2) for i in range(40)],
        "mass": [abs(math.cos(i / 4)) * 50 + 5 for i in range(40)],
    }
    c = pt.chart(df, data_width=400, data_height=200,
                 title="bubble", xlabel="x", ylabel="y")
    c.scatter(x="x", y="y", size="mass", sizes=(2, 8))
    c.legend()
    return c


def chart_scatter_size_style_color():
    # size + style + color compose. Each column drives a separate aesthetic.
    random.seed(2)
    n = 36
    groups = ["alpha", "beta", "gamma"]
    df = {
        "x":     [random.uniform(0, 10) for _ in range(n)],
        "y":     [random.uniform(0, 10) for _ in range(n)],
        "mass":  [random.uniform(5, 50) for _ in range(n)],
        "group": [groups[i % 3] for i in range(n)],
    }
    c = pt.chart(df, data_width=400, data_height=240,
                 title="color + size + style", xlabel="x", ylabel="y",
                 legend=True)
    c.scatter(x="x", y="y", color="group", size="mass", style="group")
    return c


def chart_scatter_long_color():
    import pandas as pd
    rng = random.Random(17)
    n = 60
    rows = []
    for g, (mx, my) in zip(["a", "b", "c"], [(0, 0), (2, 1), (1, 2.5)]):
        for _ in range(n):
            rows.append({"x": rng.gauss(mx, 0.6),
                         "y": rng.gauss(my, 0.6),
                         "group": g})
    df = pd.DataFrame(rows)
    c = pt.chart(data_width=300, data_height=240,
                 title="scatter (long-form, color)",
                 xlabel="x", ylabel="y", legend=True)
    c.scatter(data=df, x="x", y="y", color="group")
    c.legend()
    return c


def chart_scatter_alpha_col():
    # alpha= names a column — points fan out per (color, alpha) level
    # and alpha levels map onto the default opacity ramp.
    rng = random.Random(19)
    rows = []
    for period in ("early", "late"):
        for g, (mx, my) in (("a", (0, 0)), ("b", (2, 1.5))):
            for _ in range(30):
                rows.append({"x": rng.gauss(mx, 0.7),
                             "y": rng.gauss(my, 0.7),
                             "group": g, "period": period})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=300, data_height=240,
                 title="scatter (alpha column)", xlabel="x", ylabel="y",
                 legend=True)
    c.scatter(data=data, x="x", y="y", color="group", alpha="period")
    c.legend()
    return c


PLOTS = {
    "scatter_color": chart_scatter_color,
    "clip_data_area": chart_clip_data_area,
    "scatter_size": chart_scatter_size,
    "scatter_size_style_color": chart_scatter_size_style_color,
    "scatter_long_color": chart_scatter_long_color,
    "scatter_alpha_col": chart_scatter_alpha_col,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_scatter_baseline(name, fn, baseline_compare):
    baseline_compare("chart_scatter", name, fn().to_svg())
