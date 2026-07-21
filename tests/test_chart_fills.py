"""Baseline SVG regression tests for the fills artist/topic.

    pytest tests/test_chart_fills.py
    pytest tests/test_chart_fills.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _xs


def chart_fill_between():
    xs = _xs()
    df = {
        "x":    xs,
        "mean": [math.sin(x) for x in xs],
        "lo":   [math.sin(x) - 0.3 for x in xs],
        "hi":   [math.sin(x) + 0.3 for x in xs],
    }
    c = pt.chart(df, title="fill_between from table",
                 xlabel="x", ylabel="y", legend=True)
    c.add_fill_between(aes(x="x", y1="lo", y2="hi"), fill="C0", alpha=0.25, label="band")
    c.add_line(aes(x="x", y="mean", label="mean"), color="C0")
    return c


def chart_curve_fills():
    # curve= on fill_between and area. Use case: a sensor reading band
    # that holds between samples (step-after) — diagonal interpolation
    # would imply smooth transitions the data doesn't have.
    xs = [0, 1, 2, 3, 4, 5]
    lo = [0.5, 0.8, 1.2, 1.5, 1.1, 0.9]
    hi = [1.5, 1.8, 2.2, 2.5, 2.1, 1.9]
    c = pt.chart(title="curve= on fill_between / area",
                 xlabel="t", ylabel="value", legend=True)
    df = {"x": xs, "y1": lo, "y2": hi}
    c.add_fill_between(data=df, mapping=aes(x="x", y1="y1", y2="y2"),
                   curve="step-after", fill="C0", alpha=0.3, label="step band")
    df_area = {"x": xs, "y": [1.0, 1.3, 1.7, 2.0, 1.6, 1.4]}
    c.add_area(data=df_area, mapping=aes(x="x", y="y"), curve="step-after",
           color="C1", alpha=0.5, label="step area")
    return c


def chart_area():
    # Area under a curve (base=0, default) and area between a curve and
    # a non-zero baseline. Same artist, different `base=`.
    xs = _xs()
    df = {"t": xs,
          "sin": [math.sin(x) for x in xs],
          "cos_shifted": [math.cos(x) - 0.5 for x in xs]}
    c = pt.chart(title="area (base=0 and base=-0.5)",
                 xlabel="t", ylabel="y", legend=True)
    c.add_area(data=df, mapping=aes(x="t", y="sin", label="sin"), color="C0", alpha=0.3)
    c.add_area(data=df, mapping=aes(x="t", y="cos_shifted"), base=-0.5,
           color="C3", alpha=0.4, label="cos shifted")
    return c


def chart_step():
    # step() sugar — all three where= modes.
    xs = list(range(8))
    c = pt.chart(data_width=400, data_height=180,
                 title="step modes", xlabel="x", ylabel="y", legend=True)
    df = {"x": xs, "y": [1, 3, 2, 5, 4, 3, 6, 5]}
    c.add_step(data=df, mapping=aes(x="x", y="y"), where="post", label="post")
    df2 = {"x": xs, "y": [1.5, 3.5, 2.5, 5.5, 4.5, 3.5, 6.5, 5.5]}
    c.add_step(data=df2, mapping=aes(x="x", y="y"), where="pre", label="pre", color="C1")
    df3 = {"x": xs, "y": [2, 4, 3, 6, 5, 4, 7, 6]}
    c.add_step(data=df3, mapping=aes(x="x", y="y"), where="mid", label="mid", color="C2")
    return c


def chart_area_stack():
    import math
    xs = list(range(0, 30))
    series_data = {
        "coal":       [max(0, 100 - 2 * x + 5 * math.sin(x / 3)) for x in xs],
        "gas":        [50 + 10 * math.sin(x / 4 + 1) for x in xs],
        "nuclear":    [40 for _ in xs],
        "renewables": [5 + 2.5 * x + 8 * math.sin(x / 5) for x in xs],
    }
    rows_year, rows_src, rows_val = [], [], []
    for x in xs:
        for src, vals in series_data.items():
            rows_year.append(x); rows_src.append(src)
            rows_val.append(vals[x])
    c = pt.chart(data_width=320, data_height=220,
                 title="generation mix", xlabel="year", ylabel="TWh",
                 legend=True)
    df = {"year": rows_year, "source": rows_src, "twh": rows_val}
    c.add_area(data=df, mapping=aes(x="year", y="twh", fill="source"))
    c.legend()
    return c


PLOTS = {
    "fill_between": chart_fill_between,
    "curve_fills": chart_curve_fills,
    "area": chart_area,
    "step": chart_step,
    "area_stack": chart_area_stack,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_fills_baseline(name, fn, baseline_compare):
    baseline_compare("chart_fills", name, fn().to_svg())
