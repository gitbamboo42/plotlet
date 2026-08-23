"""Baseline SVG regression tests for the strip artist/topic.

    pytest tests/test_chart_strip.py
    pytest tests/test_chart_strip.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_strip():
    rng = random.Random(3)
    rows = []
    for cond in ("A", "B", "C", "D"):
        for series, shift in (("a", 0.0), ("b", 0.8)):
            mu = {"A": 3.0, "B": 4.5, "C": 5.2, "D": 6.1}[cond] + shift
            sd = {"A": 0.8, "B": 1.0, "C": 0.6, "D": 1.2}[cond]
            for _ in range(25):
                rows.append({"cond": cond, "series": series,
                             "value": rng.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart(data, aes(x="cond", y="value", color="series"),
                 data_width=360, data_height=220,
                 title="strip color", xlabel="condition", ylabel="value",
                 legend=True)
    c.xscale("category", order=["A", "B", "C", "D"])
    c.add_strip(palette={"a": "#3F97C5", "b": "#F99917"})
    c.legend()
    return c


def chart_strip_outline():
    # edgecolor= alone turns the outline on (width defaults to the spec
    # marker stroke) — the matplotlib/ggplot2 rule: hidden because no
    # edge color is set, never because of a zero width.
    rng = random.Random(5)
    rows = []
    for cond in ("A", "B", "C"):
        mu = {"A": 3.0, "B": 4.5, "C": 5.5}[cond]
        for _ in range(20):
            rows.append({"cond": cond, "value": rng.gauss(mu, 0.9)})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart(data, aes(x="cond", y="value"),
                 data_width=300, data_height=200,
                 title="strip outline", xlabel="condition", ylabel="value")
    c.add_strip(color="#F9C917", edgecolor="#333333", size=4)
    return c


PLOTS = {
    "strip": chart_strip,
    "strip_outline": chart_strip_outline,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_strip_baseline(name, fn, baseline_compare):
    baseline_compare("chart_strip", name, fn().to_svg())


def _dot_circles(**strip_kw):
    import re
    data = {"cat": ["a", "a", "b", "b"], "v": [1.0, 2.0, 1.5, 2.5]}
    c = pt.chart(data, aes(x="cat", y="v"))
    c.add_strip(**strip_kw)
    return re.findall(r"<circle[^>]*>", c.to_svg())


def test_edgecolor_alone_draws_outline():
    circles = _dot_circles(edgecolor="#000000")
    assert circles
    from plotlet._spec import _D
    for tag in circles:
        assert 'stroke="#000000"' in tag
        assert f'stroke-width="{_D["marker_stroke_width"]:.2f}"' in tag


def test_no_outline_without_edgecolor():
    # linewidth alone has nothing to draw — no edge color, no outline.
    for kw in ({"linewidth": 2}, {}):
        circles = _dot_circles(**kw)
        assert circles
        assert all("stroke" not in tag for tag in circles)


def test_color_is_the_point_color():
    # Scatter's vocabulary: color= fills the dots (no outline involved).
    circles = _dot_circles(color="#cc0000")
    assert circles
    for tag in circles:
        assert 'fill="#cc0000"' in tag
        assert "stroke" not in tag
