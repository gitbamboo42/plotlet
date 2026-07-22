"""Baseline SVG regression tests for the qq artist/topic.

    pytest tests/test_chart_qq.py
    pytest tests/test_chart_qq.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_qq():
    rng = random.Random(16)
    sample = [rng.gauss(0, 1) + 0.2 * (rng.expovariate(1) - 1)
              for _ in range(150)]
    df = {"s": sample}

    c = pt.chart(df, aes(sample="s"), data_width=280, data_height=240,
                 title="Q-Q vs N(0, 1)",
                 xlabel="theoretical quantile",
                 ylabel="sample quantile")
    c.add_qq(dist="normal")
    return c


def chart_qq_color():
    """qq color= grouping — per-level quantiles and robust reference lines."""
    rng = random.Random(33)
    rows_v, rows_g = [], []
    for _ in range(120):
        rows_v.append(rng.gauss(0, 1)); rows_g.append("normal-ish")
    for _ in range(120):
        rows_v.append(rng.gauss(0, 1) + 0.8 * (rng.expovariate(1) - 1))
        rows_g.append("skewed")
    df = {"v": rows_v, "g": rows_g}

    c = pt.chart(df, aes(sample="v", color="g"), data_width=280, data_height=240,
                 title="grouped Q-Q vs N(0, 1)",
                 xlabel="theoretical quantile",
                 ylabel="sample quantile", legend=True)
    c.add_qq()
    c.legend()
    return c


PLOTS = {
    "qq": chart_qq,
    "qq_color": chart_qq_color,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_qq_baseline(name, fn, baseline_compare):
    baseline_compare("chart_qq", name, fn().to_svg())


def test_qq_color_grouping():
    import re
    rng = random.Random(1)
    df = {"v": [rng.gauss(0, 1) for _ in range(40)],
          "g": ["a", "b"] * 20}
    c = pt.chart(df, aes(sample="v", color="g"))
    c.add_qq()
    svg = c.to_svg()
    assert svg.count('data-plotlet-type="qq"') == 2
    # each group's robust reference line takes the group color
    dashed = re.findall(r'<line[^>]*stroke="(#[0-9a-f]+)"[^>]*stroke-dasharray',
                        svg)
    assert {"#1f77b4", "#ff7f0e"} <= set(dashed)
