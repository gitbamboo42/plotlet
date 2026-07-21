"""Baseline SVG regression tests for the violin artist/topic.

    pytest tests/test_chart_violin.py
    pytest tests/test_chart_violin.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_violin():
    rng = random.Random(1)
    rows = []
    for group in ("ctrl", "+drug", "low", "high"):
        for trt, shift in (("A", 0.0), ("B", 1.2)):
            mu = {"ctrl": 5, "+drug": 4, "low": 7, "high": 5.5}[group] + shift
            sd = {"ctrl": 1, "+drug": 0.8, "low": 1.4, "high": 1.0}[group]
            for _ in range(80):
                rows.append({"grp": group, "trt": trt,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart(data_width=380, data_height=220,
                 title="violin fill", xlabel="group", ylabel="value",
                 legend=True)
    c.xscale("category", order=["ctrl", "+drug", "low", "high"])
    c.add_violin(data=data, mapping=aes(x="grp", y="value", fill="trt"),
             palette={"A": "#3F97C5", "B": "#F99917"}, inner="box")
    c.legend()
    return c


PLOTS = {
    "violin": chart_violin,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_violin_baseline(name, fn, baseline_compare):
    baseline_compare("chart_violin", name, fn().to_svg())
