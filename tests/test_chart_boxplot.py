"""Baseline SVG regression tests for the boxplot artist/topic.

    pytest tests/test_chart_boxplot.py
    pytest tests/test_chart_boxplot.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_boxplot():
    rng = random.Random(0)
    rows = []
    for group in ("ctrl", "low", "mid", "high"):
        for trt, shift in (("A", 0.0), ("B", 1.4)):
            mu = {"ctrl": 5, "low": 6, "mid": 7.5, "high": 9}[group] + shift
            sd = {"ctrl": 1, "low": 1.2, "mid": 1.5, "high": 1.8}[group]
            for _ in range(30):
                rows.append({"group": group, "trt": trt,
                             "score": rng.gauss(mu, sd)})
    rows += [{"group": "low", "trt": "A", "score": 12},
             {"group": "high", "trt": "B", "score": 16}]
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart(data, aes(x="group", y="score", fill="trt"),
                 data_width=380, data_height=220,
                 title="boxplot fill", xlabel="group", ylabel="score",
                 legend=True)
    c.xscale("category", order=["ctrl", "low", "mid", "high"])
    c.add_boxplot(palette={"A": "#3F97C5", "B": "#F99917"})
    c.legend()
    return c


def chart_aes_inheritance():
    """Chart-level aes (x=, y=, color=, fill=) inherited by multiple artist
    calls. The boxplot+strip overlay is the canonical use case."""
    import pandas as pd
    rng = random.Random(20)
    rows = []
    for g in ["A", "B", "C"]:
        mu = {"A": 0, "B": 1.5, "C": 0.7}[g]
        for _ in range(40):
            rows.append({"group": g, "value": rng.gauss(mu, 0.6)})
    df = pd.DataFrame(rows)

    c = pt.chart(df, aes(x="group", y="value"),
                 data_width=320, data_height=240,
                 title="aes inheritance (boxplot + strip)")
    c.add_boxplot()
    c.add_strip(size=3, alpha=0.5)
    return c


def chart_boxplot_notch_h():
    # Horizontal + notch=True (median-CI indent, box points swapped to
    # (value, cat) space) + showmeans markers.
    rng = random.Random(7)
    rows = []
    for site, mu in (("north", 4.0), ("center", 6.0), ("south", 5.0)):
        for _ in range(40):
            rows.append({"site": site, "ph": rng.gauss(mu, 1.1)})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart(data, aes(x="site", y="ph"),
                 data_width=320, data_height=200,
                 title="boxplot horizontal + notch + means", xlabel="pH")
    c.add_boxplot(orientation="h", notch=True, showmeans=True)
    return c


def chart_boxplot_unfilled():
    # fill=False draws line-only boxes; showfliers=False drops the
    # outlier dots; whis=1.0 tightens the whisker fences.
    rng = random.Random(8)
    rows = []
    for batch, mu in (("b1", 10.0), ("b2", 12.5), ("b3", 11.0)):
        for _ in range(35):
            rows.append({"batch": batch, "amount": rng.gauss(mu, 1.4)})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart(data, aes(x="batch", y="amount"),
                 data_width=300, data_height=200,
                 title="boxplot unfilled, no fliers", ylabel="amount")
    c.add_boxplot(fill=False, showfliers=False, whis=1.0, color="#336699")
    return c


PLOTS = {
    "boxplot": chart_boxplot,
    "aes_inheritance": chart_aes_inheritance,
    "boxplot_notch_h": chart_boxplot_notch_h,
    "boxplot_unfilled": chart_boxplot_unfilled,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_boxplot_baseline(name, fn, baseline_compare):
    baseline_compare("chart_boxplot", name, fn().to_svg())
