"""Baseline SVG regression tests for the ridge artist/topic.

    pytest tests/test_chart_ridge.py
    pytest tests/test_chart_ridge.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_ridge():
    rng = random.Random(15)
    labels = ["Jan", "Feb", "Mar", "Apr", "May"]
    rows_label, rows_value = [], []
    for i, lbl in enumerate(labels):
        for _ in range(200):
            rows_label.append(lbl)
            rows_value.append(rng.gauss(20 + i, 3))
    df = {"month": rows_label, "value": rows_value}
    c = pt.chart(data_width=320, data_height=260,
                 title="ridge", xlabel="value")
    c.add_ridge(data=df, mapping=aes(x="month", y="value"), overlap=1.6)
    c.yticks([])
    return c


def chart_ridge_color():
    """ridge color= grouping — overlaid sub-densities per row."""
    rng = random.Random(32)
    rows_m, rows_v, rows_g = [], [], []
    for i, month in enumerate(["Jan", "Feb", "Mar", "Apr"]):
        for g, shift in zip(["day", "night"], [0.0, 4.0]):
            for _ in range(150):
                rows_m.append(month); rows_g.append(g)
                rows_v.append(rng.gauss(15 + i * 2 + shift, 2.5))
    df = {"month": rows_m, "temp": rows_v, "period": rows_g}
    c = pt.chart(data_width=320, data_height=260,
                 title="grouped ridge", xlabel="temperature", legend=True)
    c.add_ridge(data=df, mapping=aes(x="month", y="temp", color="period"), overlap=1.6)
    c.yticks([])
    c.legend()
    return c


PLOTS = {
    "ridge": chart_ridge,
    "ridge_color": chart_ridge_color,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_ridge_baseline(name, fn, baseline_compare):
    baseline_compare("chart_ridge", name, fn().to_svg())


def test_ridge_color_series():
    import re
    df = {"m": ["Jan"] * 8, "v": [1, 2, 3, 4, 11, 12, 13, 14],
          "g": ["day"] * 4 + ["night"] * 4}
    c = pt.chart(df)
    c.add_ridge(aes(x="m", y="v", color="g"))
    fills = set(re.findall(r'<path[^>]*fill="(#[0-9a-f]+)"', c.to_svg()))
    assert {"#1f77b4", "#ff7f0e"} <= fills
