"""Baseline SVG regression tests for the spines artist/topic.

    pytest tests/test_chart_spines.py
    pytest tests/test_chart_spines.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _xs


def chart_despined():
    # `c.spines(top=False, right=False)` drops the top and right spines.
    # Ticks are independent of spine visibility and live on the
    # bottom/left sides, which stay visible.
    xs = _xs()
    df = {"t": xs, "v": [math.sin(x) for x in xs]}
    c = pt.chart(df, title="despined frame", xlabel="t", ylabel="v")
    c.add_line(aes(x="t", y="v"))
    c.spines(top=False, right=False)
    return c


def chart_restyled_spines():
    # Per-side dict syntax: visible by default, color/width override the
    # spec.json defaults. Tick marks adopt the same side's stroke for
    # visual consistency.
    xs = _xs()
    df = {"t": xs, "v": [math.sin(x) for x in xs]}
    c = pt.chart(df, title="restyled spines", xlabel="t", ylabel="v")
    c.add_line(aes(x="t", y="v"))
    c.spines(top=False, right=False,
             left={"color": "red", "width": 1.5},
             bottom={"color": "gray"})
    return c


PLOTS = {
    "despined": chart_despined,
    "restyled_spines": chart_restyled_spines,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_spines_baseline(name, fn, baseline_compare):
    baseline_compare("chart_spines", name, fn().to_svg())
