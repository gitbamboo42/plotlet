"""Baseline SVG regression tests for the numeric_bar artist.

Numeric-x bars at explicit positions with a fixed data-unit width — the
regime where the categorical band scale of `c.bar` doesn't apply. (The
ring form is covered in test_coord_circular.py.)

    pytest tests/test_chart_numeric_bar.py
    pytest tests/test_chart_numeric_bar.py --update
"""
from __future__ import annotations

import plotlet as pt
from plotlet import aes
import pytest


def chart_numeric_bar_uneven():
    # Bars at uneven numeric positions with a fixed width= — spacing is
    # honest to the data, not equal band slots. x autoscales by half a
    # width on each side; y always includes 0 (force_zero_y).
    c = pt.chart(data_width=360, data_height=180, title="numeric_bar",
                 xlabel="pos", ylabel="score")
    df = {"x": [0.5, 1.2, 3.0, 3.4, 6.0, 8.5],
      "y": [3, 7, 4, 9, 2, 6]}
    c.add_numeric_bar(data=df, mapping=aes(x="x", y="y"), width=0.4, color="#4C72B0")
    return c


def chart_numeric_bar_labeled():
    # label= drives a single legend swatch; alpha applied to the fill.
    c = pt.chart(data_width=340, data_height=180, title="numeric_bar labeled",
                 xlabel="pos", ylabel="score", legend=True)
    df = {"x": [1.0, 2.0, 3.0, 4.0, 5.0],
      "y": [5, 8, 3, 6, 4]}
    c.add_numeric_bar(data=df, mapping=aes(x="x", y="y"), width=0.7, color="#DD8452", alpha=0.85,
                  label="signal")
    c.legend()
    return c


PLOTS = {
    "numeric_bar_uneven": chart_numeric_bar_uneven,
    "numeric_bar_labeled": chart_numeric_bar_labeled,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_numeric_bar_baseline(name, fn, baseline_compare):
    baseline_compare("chart_numeric_bar", name, fn().to_svg())
