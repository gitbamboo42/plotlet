"""Baseline SVG regression tests for the errorbar artist/topic.

    pytest tests/test_chart_errorbar.py
    pytest tests/test_chart_errorbar.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _bar_quarterly_df


def chart_errorbar():
    # Vertical error bars: symmetric (column) and asymmetric (tuple of columns).
    df_meas = {"x": [1, 2, 3, 4, 5, 6],
               "y": [2.1, 3.4, 4.0, 3.8, 5.1, 6.2],
               "sd": [0.4, 0.3, 0.6, 0.5, 0.4, 0.7]}
    df_model = {"x": [1.2, 2.2, 3.2, 4.2, 5.2, 6.2],
                "y": [1.5, 2.6, 3.3, 4.7, 5.9, 6.8],
                "lo": [0.2, 0.3, 0.2, 0.4, 0.3, 0.5],
                "hi": [0.5, 0.4, 0.6, 0.3, 0.5, 0.4]}
    c = pt.chart(title="error bars", xlabel="x", ylabel="y", legend=True)
    c.add_errorbar(data=df_meas, mapping=aes(x="x", y="y", yerr="sd"), label="measurement")
    c.add_errorbar(data=df_model, mapping=aes(x="x", y="y"), yerr=("lo", "hi"),
               marker="s", label="model")
    return c


def chart_errorbar_grouped():
    # color= column → one series per level, dodged within each band,
    # per-group legend entries.
    df = _bar_quarterly_df()
    df["sd"] = [round(0.4 + 0.08 * v, 2) for v in df["value"]]
    c = pt.chart(data_width=320, data_height=200,
                 title="errorbar grouped (dodged)", ylabel="$M", legend=True)
    c.add_errorbar(data=df, mapping=aes(x="quarter", y="value", yerr="sd", color="series"))
    c.legend()
    return c


PLOTS = {
    "errorbar": chart_errorbar,
    "errorbar_grouped": chart_errorbar_grouped,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_errorbar_baseline(name, fn, baseline_compare):
    baseline_compare("chart_errorbar", name, fn().to_svg())
