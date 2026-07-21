"""Baseline SVG regression tests for the references artist/topic.

    pytest tests/test_chart_references.py
    pytest tests/test_chart_references.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest
from _chart_helpers import _xs


def chart_reflines():
    xs = _xs()
    df = {"t": xs, "v": [math.sin(x) for x in xs]}
    c = pt.chart(df, title="reference lines",
                 xlabel="t", ylabel="v", legend=True, gridlines=True)
    c.add_axhspan(-0.5, 0.5, color="C2")
    c.add_axvspan(2.0, 3.5)
    c.add_line(x="t", y="v", label="sin(t)")
    c.add_axhline(0)
    c.add_axhline(0.8, color="red", linestyle="--", label="upper")
    c.add_axvline(math.pi, color="gray", linestyle=":")
    return c


def chart_axline():
    """Infinite reference lines in arbitrary directions: the y=x identity
    line via slope=, a two-point line, both clipped to the frame."""
    rng = random.Random(31)
    obs = [i * 0.5 + rng.gauss(0, 0.6) for i in range(20)]
    pred = [v + rng.gauss(0, 0.5) for v in obs]
    c = pt.chart(data_width=260, data_height=220,
                 title="observed vs predicted",
                 xlabel="observed", ylabel="predicted", legend=True)
    c.add_scatter(data={"o": obs, "p": pred}, x="o", y="p", size=2.5, alpha=0.7)
    c.add_axline((0, 0), slope=1, linestyle="--", label="y = x")
    c.add_axline((0, 8), (8, 4), color="C3", label="two-point")
    return c


def chart_hlines_vlines():
    # Bounded segment artists in data coordinates. Unlike axhline/axvline
    # they participate in autoscaling and use the color cycle.
    c = pt.chart(title="hlines / vlines", xlabel="x", ylabel="y", legend=True)
    c.add_hlines([1, 2, 3], 0, 5, label="thresholds", linestyle="--")
    c.add_vlines([1.5, 3.5], 0.5, 3.5, label="markers", color="C3")
    return c


PLOTS = {
    "reflines": chart_reflines,
    "axline": chart_axline,
    "hlines_vlines": chart_hlines_vlines,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_references_baseline(name, fn, baseline_compare):
    baseline_compare("chart_references", name, fn().to_svg())
