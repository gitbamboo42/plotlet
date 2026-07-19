"""Baseline SVG regression tests for the freqpoly artist/topic.

    pytest tests/test_chart_freqpoly.py
    pytest tests/test_chart_freqpoly.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_freqpoly():
    rng = random.Random(14)
    a = [rng.gauss(0, 1) for _ in range(400)]
    b = [rng.gauss(1, 1.4) for _ in range(400)]
    c = pt.chart(data_width=300, data_height=200,
                 title="frequency polygon", xlabel="value", ylabel="count",
                 legend=True)
    c.freqpoly(data={"x": a}, x="x", bins=25, label="control")
    c.freqpoly(data={"x": b}, x="x", bins=25, label="treatment")
    c.legend()
    return c


PLOTS = {
    "freqpoly": chart_freqpoly,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_freqpoly_baseline(name, fn, baseline_compare):
    baseline_compare("chart_freqpoly", name, fn().to_svg())
