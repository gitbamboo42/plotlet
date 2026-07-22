"""Baseline SVG regression tests for the pointplot artist/topic.

    pytest tests/test_chart_pointplot.py
    pytest tests/test_chart_pointplot.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_pointplot():
    rng = random.Random(7)
    cats = ["1 wk", "2 wk", "4 wk", "8 wk"]
    # Generate values in the same RNG order as the original wide-form to
    # preserve byte-identical baselines.
    ctrl_t, ctrl_score = [], []
    for i, t in enumerate(cats):
        for _ in range(20):
            ctrl_t.append(t); ctrl_score.append(rng.gauss(5.0 + 0.04 * i, 1.0))
    drug_t, drug_score = [], []
    for i, t in enumerate(cats):
        for _ in range(20):
            drug_t.append(t); drug_score.append(rng.gauss(5.0 + 0.45 * i, 1.0))
    c = pt.chart(data_width=320, data_height=200,
                 title="pointplot", xlabel="timepoint", ylabel="score",
                 legend=True)
    c.xscale("category", order=cats)
    df = {"t": ctrl_t, "score": ctrl_score}
    c.add_pointplot(df, aes(x="t", y="score"), label="control")
    df2 = {"t": drug_t, "score": drug_score}
    c.add_pointplot(df2, aes(x="t", y="score"), label="drug")
    c.legend()
    return c


def chart_pointplot_color():
    """pointplot color= grouping — one series + CI per level."""
    rng = random.Random(30)
    cats = ["1 wk", "2 wk", "4 wk", "8 wk"]
    rows_t, rows_s, rows_a = [], [], []
    for arm, slope in zip(["control", "drug"], [0.04, 0.45]):
        for i, t in enumerate(cats):
            for _ in range(20):
                rows_t.append(t); rows_a.append(arm)
                rows_s.append(rng.gauss(5.0 + slope * i, 1.0))
    df = {"t": rows_t, "score": rows_s, "arm": rows_a}
    c = pt.chart(df, aes(x="t", y="score", color="arm"),
                 data_width=320, data_height=200,
                 title="pointplot color=", xlabel="timepoint",
                 ylabel="score", legend=True)
    c.xscale("category", order=cats)
    c.add_pointplot()
    c.legend()
    return c


PLOTS = {
    "pointplot": chart_pointplot,
    "pointplot_color": chart_pointplot_color,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_pointplot_baseline(name, fn, baseline_compare):
    baseline_compare("chart_pointplot", name, fn().to_svg())


def test_pointplot_rejects_unknown_ci():
    # pointplot used to fall through to the bootstrap branch on any
    # unknown ci=; it now shares bar/line's validation
    df = {"t": ["a", "a"], "v": [1, 2]}
    c = pt.chart(df, aes(x="t", y="v"))
    c.add_pointplot(ci="x")
    with pytest.raises(ValueError, match="ci='x'"):
        c.to_svg()


def test_pointplot_color_series():
    import re
    df = {"t": ["a", "a", "b", "b"], "v": [1, 2, 3, 4], "g": ["x", "y", "x", "y"]}
    c = pt.chart(df, aes(x="t", y="v", color="g"))
    c.add_pointplot(ci=None)
    fills = set(re.findall(r'<circle[^>]*fill="(#[0-9a-f]+)"', c.to_svg()))
    assert {"#1f77b4", "#ff7f0e"} <= fills
