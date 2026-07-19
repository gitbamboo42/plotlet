"""Baseline SVG regression tests for the ecdf artist/topic.

    pytest tests/test_chart_ecdf.py
    pytest tests/test_chart_ecdf.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_ecdf():
    rng = random.Random(8)
    a = [rng.gauss(0, 1) for _ in range(200)]
    b = [rng.gauss(0.6, 1.3) for _ in range(200)]
    c = pt.chart(data_width=300, data_height=200,
                 title="ECDF", xlabel="value", ylabel="F̂(x)",
                 legend=True)
    c.ecdf(data={"x": a}, x="x", label="control")
    c.ecdf(data={"x": b}, x="x", label="treatment")
    c.legend()
    return c


PLOTS = {
    "ecdf": chart_ecdf,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_ecdf_baseline(name, fn, baseline_compare):
    baseline_compare("chart_ecdf", name, fn().to_svg())
