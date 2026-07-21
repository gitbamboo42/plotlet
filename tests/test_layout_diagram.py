#!/usr/bin/env python3
"""Baseline SVG regression tests for `pt.layout_diagram`.

    python tests/test_layout_diagram.py            # check vs. baselines, exit 1 on mismatch
    python tests/test_layout_diagram.py --update   # regenerate baselines (review diff!)
    python tests/test_layout_diagram.py --gallery  # write baseline_images/layout_diagram/index.html

Locks in the visual format of the layout-diagram helper so refactors to
the render internals (which alter the panel-bbox / data-area attrs the diagram
reads) surface as a baseline diff here too.
"""
from __future__ import annotations

import math
import sys

import plotlet as pt



def _xs():
    return [i * 0.1 for i in range(64)]


def diag_single():
    c = pt.chart(title="single", data_width=400, data_height=240,
                 xlabel="x", ylabel="sin x")
    c.add_line(data={"x": _xs(), "y": [math.sin(t) for t in _xs()]}, x="x", y="y")
    return pt.layout_diagram(c)


def diag_two_plot():
    # (a | b) / c — three gaps: a-b vertical strip, a-c and b-c horizontal slabs.
    xs = _xs()
    sin = [math.sin(t) for t in xs]
    cos = [math.cos(t) for t in xs]
    a = pt.chart(title="a", data_width=290, data_height=140); a.add_line(data={"x": xs, "y": sin}, x="x", y="y")
    b = pt.chart(title="b", data_width=290, data_height=140); b.add_line(data={"x": xs, "y": cos}, x="x", y="y")
    c = pt.chart(title="c", data_width=600, data_height=140)
    c.add_line(data={"x": xs, "y": [s + co for s, co in zip(sin, cos)]}, x="x", y="y")
    return pt.layout_diagram((a | b) / c)


def diag_share_pair():
    # (a / c) | b with share_x on the (a/c) stack — a-c gap collapses to 0.
    xs = _xs()
    sin = [math.sin(t) for t in xs]
    cos = [math.cos(t) for t in xs]
    a = pt.chart(title="a", data_width=290, data_height=140); a.add_line(data={"x": xs, "y": sin}, x="x", y="y")
    c = pt.chart(title="c", data_width=290, data_height=140)
    c.add_line(data={"x": xs, "y": [s + co for s, co in zip(sin, cos)]}, x="x", y="y")
    b = pt.chart(title="b", data_width=290, data_height=280); b.add_line(data={"x": xs, "y": cos}, x="x", y="y")
    return pt.layout_diagram((a / c).share_x() | b)


def diag_multi_share_grid():
    # 2x2 grid with main↔top (column-shared x) and main↔tree (row-shared y).
    # Verifies share_x="col" and share_y="row" produce the expected joins.
    main = pt.chart(title="main", data_width=440, data_height=260)
    main.add_line(data={"x": [1, 2, 3, 4, 5], "y": [2, 4, 1, 5, 3]}, x="x", y="y")
    top  = pt.chart(title="top",  data_width=440, data_height=80)
    top.add_line(data={"x": [1, 2, 3, 4, 5], "y": [1, 1, 3, 1, 1]}, x="x", y="y")
    tree = pt.chart(title="tree", data_width=120, data_height=260)
    tree.add_line(data={"x": [0, 1, 2], "y": [2, 3, 4]}, x="x", y="y")
    return pt.layout_diagram(pt.grid([
        [None, top ],
        [tree, main],
    ]).share_x("col").share_y("row"))


def diag_composed_with_source():
    # `c | layout_diagram(c)` — the diagram leaf participates in plotlet's
    # composition algebra. Locks in: (a) the chart and its diagram render
    # side by side at the same height; (b) the diagram <g> in the layout
    # SVG carries data-plotlet-kind="diagram" so consumers can identify it.
    c = pt.chart(title="src", data_width=300, data_height=180,
                 xlabel="x", ylabel="y")
    c.add_line(data={"x": [0, 1, 2, 3, 4], "y": [0, 1, 0, 1, 0]}, x="x", y="y")
    return c | pt.layout_diagram(c)


PLOTS = {
    "single":              diag_single,
    "two_plot":            diag_two_plot,
    "share_pair":          diag_share_pair,
    "multi_share_grid":    diag_multi_share_grid,
    "composed_with_source": diag_composed_with_source,
}


import pytest

@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_layout_diagram_baseline(name, fn, baseline_compare):
    baseline_compare("layout_diagram", name, fn().to_svg())
