"""Baseline SVG regression tests for the rug artist.

    pytest tests/test_chart_rug.py
    pytest tests/test_chart_rug.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_rug():
    rng = random.Random(9)
    vals = [rng.gauss(0, 1) for _ in range(150)]
    c = pt.chart(data_width=300, data_height=200,
                 title="density + rug", xlabel="value", ylabel="density")
    c.add_density_1d(data={"x": vals}, x="x", fill=True)
    c.add_rug(data={"x": vals}, x="x", color="#444444")
    return c


PLOTS = {
    "rug": chart_rug,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_rug_baseline(name, fn, baseline_compare):
    baseline_compare("chart_rug", name, fn().to_svg())
