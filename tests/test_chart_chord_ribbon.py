"""Baseline SVG regression tests for the chord_ribbon artist.

Covers the Cartesian (no-coord) path: the linear-bow fallback — a filled
ribbon between two x-ranges. The circular through-center Bezier ribbon
lives in test_coord_circular.py.

    pytest tests/test_chart_chord_ribbon.py
    pytest tests/test_chart_chord_ribbon.py --update
"""
from __future__ import annotations

import plotlet as pt
from plotlet import aes
import pytest


def chart_chord_ribbon_flat():
    # Linear-bow ribbons connecting an x-range on the left to an x-range
    # on the right — the flat unroll of a circular chord ribbon.
    df = {"a0": [0.0, 2.0], "a1": [1.5, 3.5],
          "b0": [6.0, 8.0], "b1": [7.5, 9.5]}

    c = pt.chart(df, aes(x1_start="a0", x1_end="a1", x2_start="b0", x2_end="b1"),
                 data_width=400, data_height=170, title="ribbons",
                 xlabel="position")
    c.add_chord_ribbon(color="#4C72B0", alpha=0.6)
    c.yticks([])
    return c


def chart_chord_ribbon_color():
    # color= grouping with palette, plus an edge stroke (edge_color /
    # edge_width) outlining each ribbon.
    df = {"a0": [0.0, 1.0, 2.0], "a1": [0.8, 1.8, 2.8],
          "b0": [5.0, 6.5, 8.0], "b1": [5.8, 7.3, 8.8],
          "grp": ["p", "q", "p"]}

    c = pt.chart(df, aes(x1_start="a0", x1_end="a1", x2_start="b0", x2_end="b1", color="grp"),
                 data_width=400, data_height=185, title="ribbons by group",
                 xlabel="position", legend=True)
    c.add_chord_ribbon(palette={"p": "#C44E52", "q": "#8172B3"},
                        alpha=0.55, edge_color="#333333", edge_width=0.5)
    c.yticks([])
    c.legend()
    return c


PLOTS = {
    "chord_ribbon_flat": chart_chord_ribbon_flat,
    "chord_ribbon_color": chart_chord_ribbon_color,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_chord_ribbon_baseline(name, fn, baseline_compare):
    baseline_compare("chart_chord_ribbon", name, fn().to_svg())
