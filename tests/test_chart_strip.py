"""Baseline SVG regression tests for the strip artist/topic.

    pytest tests/test_chart_strip.py
    pytest tests/test_chart_strip.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_strip():
    rng = random.Random(3)
    rows = []
    for cond in ("A", "B", "C", "D"):
        for series, shift in (("a", 0.0), ("b", 0.8)):
            mu = {"A": 3.0, "B": 4.5, "C": 5.2, "D": 6.1}[cond] + shift
            sd = {"A": 0.8, "B": 1.0, "C": 0.6, "D": 1.2}[cond]
            for _ in range(25):
                rows.append({"cond": cond, "series": series,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=360, data_height=220,
                 title="strip fill", xlabel="condition", ylabel="value",
                 legend=True)
    c.xscale("category", order=["A", "B", "C", "D"])
    c.strip(data=data, x="cond", y="value", fill="series",
            palette={"a": "#3F97C5", "b": "#F99917"})
    c.legend()
    return c


PLOTS = {
    "strip": chart_strip,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_strip_baseline(name, fn, baseline_compare):
    baseline_compare("chart_strip", name, fn().to_svg())
