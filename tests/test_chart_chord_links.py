"""Baseline SVG regression tests for the chord_links artist.

Covers the Cartesian (no-coord) path: half-ellipse arcs above y=0 — the
classic arc-diagram look. The circular/Circos Bezier-through-disc path
lives in test_coord_circular.py.

    pytest tests/test_chart_chord_links.py
    pytest tests/test_chart_chord_links.py --update
"""
from __future__ import annotations

import plotlet as pt
from plotlet import aes
import pytest


def chart_chord_links_arcs():
    # Basic arc diagram: half-ellipse arcs from x1 to x2 with the default
    # semicircle bulge (height = |x2 - x1| / 2), so ylim autoscales to fit.
    # yticks([]) for the clean arc-diagram frame.
    df = {"a": [1, 2, 1, 5, 3], "b": [4, 6, 8, 7, 9]}

    c = pt.chart(df, aes(x1="a", x2="b"), data_width=380, data_height=160,
                 title="arc diagram", xlabel="position")
    c.add_chord_links(color="#4C72B0", width=1.5)
    c.yticks([])
    return c


def chart_chord_links_color():
    # Categorical color= — one arc series per level, palette colors and
    # per-level legend entries.
    df = {"a": [0, 1, 2, 3, 4],
          "b": [5, 6, 7, 8, 9],
          "grp": ["x", "y", "x", "y", "x"]}

    c = pt.chart(df, aes(x1="a", x2="b", color="grp"), data_width=380,
                 data_height=175, title="arcs by group", xlabel="position",
                 legend=True)
    c.add_chord_links(palette={"x": "#4C72B0", "y": "#DD8452"},
                       width=1.5, alpha=0.85)
    c.yticks([])
    c.legend()
    return c


def chart_chord_links_height():
    # Explicit height= (px) flattens the bulge below the semicircle
    # default; width + alpha also exercised.
    df = {"a": [1, 2, 3, 4], "b": [8, 7, 9, 6]}

    c = pt.chart(df, aes(x1="a", x2="b"), data_width=380, data_height=130,
                 title="flattened arcs", xlabel="position")
    c.add_chord_links(color="#55A868", height=30, width=2.5, alpha=0.7)
    c.yticks([])
    return c


PLOTS = {
    "chord_links_arcs": chart_chord_links_arcs,
    "chord_links_color": chart_chord_links_color,
    "chord_links_height": chart_chord_links_height,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_chord_links_baseline(name, fn, baseline_compare):
    baseline_compare("chart_chord_links", name, fn().to_svg())
