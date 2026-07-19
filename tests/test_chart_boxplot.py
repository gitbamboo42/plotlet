"""Baseline SVG regression tests for the boxplot artist/topic.

    pytest tests/test_chart_boxplot.py
    pytest tests/test_chart_boxplot.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
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
    c = pt.chart(data_width=380, data_height=220,
                 title="boxplot fill", xlabel="group", ylabel="score",
                 legend=True)
    c.xscale("category", order=["ctrl", "low", "mid", "high"])
    c.boxplot(data=data, x="group", y="score", fill="trt",
              palette={"A": "#3F97C5", "B": "#F99917"})
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
    c = pt.chart(df, x="group", y="value",
                 data_width=320, data_height=240,
                 title="aes inheritance (boxplot + strip)")
    c.boxplot()
    c.strip(size=3, alpha=0.5)
    return c


PLOTS = {
    "boxplot": chart_boxplot,
    "aes_inheritance": chart_aes_inheritance,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_boxplot_baseline(name, fn, baseline_compare):
    baseline_compare("chart_boxplot", name, fn().to_svg())
