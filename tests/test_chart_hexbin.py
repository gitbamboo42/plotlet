"""Baseline SVG regression tests for the hexbin artist/topic.

    pytest tests/test_chart_hexbin.py
    pytest tests/test_chart_hexbin.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_hexbin():
    rng = random.Random(13)
    n = 3000
    xs = [rng.gauss(0, 1) + rng.gauss(0, 0.4) for _ in range(n)]
    ys = [x + rng.gauss(0, 1) for x in xs]
    c = pt.chart(data_width=300, data_height=260,
                 title="hexbin", xlabel="x", ylabel="y")
    c.add_hexbin(data={"x": xs, "y": ys}, x="x", y="y", gridsize=22)
    return c | pt.legend(c)


PLOTS = {
    "hexbin": chart_hexbin,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_hexbin_baseline(name, fn, baseline_compare):
    baseline_compare("chart_hexbin", name, fn().to_svg())


def test_hexbin_colorbar_matches_drawn_counts():
    # The colorbar must label the range the cells were actually colored
    # with. It used to default to a record-time density guess
    # (n / (gridsize²/4)) — for clustered data the real max is far
    # higher, so the legend silently labeled the wrong range.
    c = pt.chart({"x": [1.0] * 100, "y": [2.0] * 100}, legend=True)
    c.add_hexbin(x="x", y="y")   # every point lands in one cell: true max 100
    labels = [r["meta"].get("text") for r in c.regions()
              if r["kind"] == "text" and r["name"] == "legend-text"]
    assert labels == ["0", "50", "100"]
