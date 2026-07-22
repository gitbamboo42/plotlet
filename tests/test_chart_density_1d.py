"""Baseline SVG regression tests for the density_1d artist/topic.

    pytest tests/test_chart_density_1d.py
    pytest tests/test_chart_density_1d.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_density_1d():
    rng = random.Random(10)
    a = [rng.gauss(0, 1) for _ in range(300)]
    b = [rng.gauss(1.2, 1.3) for _ in range(300)]
    df = {"x": a}

    c = pt.chart(data_width=300, data_height=200,
                 title="density", xlabel="value", ylabel="density",
                 legend=True)
    c.add_density_1d(df, aes(x="x"), label="control", fill=True)
    df2 = {"x": b}
    c.add_density_1d(df2, aes(x="x"), label="treatment", fill=True)
    c.legend()
    return c


def chart_density_1d_long_color():
    import pandas as pd
    rng = random.Random(18)
    rows = []
    for g, mu in zip(["control", "treatment"], [0, 1.2]):
        for _ in range(300):
            rows.append({"val": rng.gauss(mu, 1.0), "group": g})
    df = pd.DataFrame(rows)

    c = pt.chart(df, aes(x="val", color="group"),
                 data_width=320, data_height=200,
                 title="density (long-form, color)",
                 xlabel="value", ylabel="density", legend=True)
    c.add_density_1d(fill=True)
    c.legend()
    return c


PLOTS = {
    "density_1d": chart_density_1d,
    "density_1d_long_color": chart_density_1d_long_color,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_density_1d_baseline(name, fn, baseline_compare):
    baseline_compare("chart_density_1d", name, fn().to_svg())