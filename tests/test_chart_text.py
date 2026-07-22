"""Baseline SVG regression tests for the text artist.

    pytest tests/test_chart_text.py
    pytest tests/test_chart_text.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_text():
    # Data-anchored text labels. Single-point and batched-list forms.
    xs = [1, 2, 3, 4, 5]
    ys = [3, 7, 4, 9, 5]
    df = {"x": xs, "y": ys}
    df2 = {"x": xs, "y": ys, "label": ["A", "B", "C", "D", "E"]}

    c = pt.chart(df, aes(x="x", y="y"), title="text annotations", xlabel="x", ylabel="y")
    c.add_scatter()
    c.add_text(data=df2, mapping=aes(x="x", y="y", label="label"), dy=-10, ha="center")
    c.add_annotate("peak", xy=(3, 9.5), color="C3", ha="center")
    return c


def chart_text_bbox():
    # Text labels with a background box — readable over dense data.
    xs = [i * 0.1 for i in range(120)]
    ys = [math.sin(x * 3) * math.exp(-x * 0.1) for x in xs]
    df = {"x": xs, "y": ys}

    c = pt.chart(df, aes(x="x", y="y"), data_width=420, data_height=200,
                 title="text bbox", xlabel="t", ylabel="y")
    c.add_line()
    c.add_annotate("plain", xy=(2.0, 0.5), fontsize=12)
    c.add_annotate("on white", xy=(4.0, 0.5), fontsize=12, bbox=True)
    c.add_annotate("tinted", xy=(6.0, 0.5), fontsize=12,
               bbox={"facecolor": "#ffe", "edgecolor": "#888", "pad": 4, "alpha": 0.95})
    c.add_annotate("peak", xy=(xs[3], ys[3]), xytext=(0.6, 0.85),
               bbox={"facecolor": "#fff", "edgecolor": "#555", "pad": 3})
    return c


def chart_annotate():
    # Text label + arrow to a data point. Both endpoints in data coords.
    xs = [i * 0.2 for i in range(40)]
    ys = [math.sin(x) + math.sin(2 * x) * 0.4 for x in xs]
    df = {"x": xs, "y": ys}

    c = pt.chart(df, aes(x="x", y="y"), data_width=400, data_height=200,
                 title="annotate", xlabel="x", ylabel="y")
    c.add_line()
    max_i = ys.index(max(ys))
    # Label sits left of the peak (ha="right" → glyphs extend left from
    # the anchor): margins only reserve chrome space, so a left-anchored
    # label this close to the right edge would run off the canvas.
    c.add_annotate("global max",
               xy=(xs[max_i], ys[max_i]),
               xytext=(xs[max_i] - 1.5, ys[max_i] + 0.3), ha="right")
    c.add_annotate("first zero",
               xy=(math.pi, 0),
               xytext=(math.pi - 2, 0.6), ha="center")
    # dx/dy nudge the label end in screen space (arrow tail follows);
    # rotation spins the text around its anchor, arrow unrotated.
    min_i = ys.index(min(ys))
    c.add_annotate("global min",
               xy=(xs[min_i], ys[min_i]),
               xytext=(xs[min_i], ys[min_i]), dx=14, dy=-10)
    c.add_annotate("rotated",
               xy=(6.0, ys[30]),
               xytext=(6.0, ys[30] + 0.8), ha="center", rotation=30)
    return c


PLOTS = {
    "text": chart_text,
    "text_bbox": chart_text_bbox,
    "annotate": chart_annotate,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_text_baseline(name, fn, baseline_compare):
    baseline_compare("chart_text", name, fn().to_svg())
