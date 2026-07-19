"""Baseline SVG regression tests for the swarm artist/topic.

    pytest tests/test_chart_swarm.py
    pytest tests/test_chart_swarm.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_swarm():
    rng = random.Random(2)
    rows = []
    for group in ("A", "B", "C", "D"):
        for series, shift in (("a", 0.0), ("b", 0.8)):
            mu = {"A": 3.0, "B": 4.5, "C": 5.2, "D": 6.0}[group] + shift
            sd = {"A": 0.6, "B": 0.7, "C": 0.5, "D": 0.9}[group]
            for _ in range(20):
                rows.append({"group": group, "series": series,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=360, data_height=220,
                 title="swarm fill", xlabel="group", ylabel="value",
                 legend=True)
    c.xscale("category", order=["A", "B", "C", "D"])
    c.swarm(data=data, x="group", y="value", fill="series",
            palette={"a": "#3F97C5", "b": "#F99917"})
    c.legend()
    return c


PLOTS = {
    "swarm": chart_swarm,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_swarm_baseline(name, fn, baseline_compare):
    baseline_compare("chart_swarm", name, fn().to_svg())


def test_swarm_drops_nan():
    # NaN has no position: it used to emit cy="nan" circles and degrade
    # collision placement of every neighboring point.
    nan = float("nan")
    c = pt.chart({"cat": ["a", "a", "a", "b"], "v": [1.0, nan, 2.0, nan]})
    c.swarm(x="cat", y="v")
    svg = c.to_svg()
    assert "nan" not in svg
    assert svg.count("<circle") == 2
