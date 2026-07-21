"""Baseline SVG regression tests for the hist2d artist/topic.

    pytest tests/test_chart_hist2d.py
    pytest tests/test_chart_hist2d.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest


def chart_hist2d():
    rng = random.Random(24)
    n = 3000
    xs = [rng.gauss(0, 1) for _ in range(n)]
    ys = [x * 0.6 + rng.gauss(0, 0.8) for x in xs]
    c = pt.chart(data_width=300, data_height=260,
                 title="2-D histogram", xlabel="x", ylabel="y")
    df = {"x": xs, "y": ys}
    c.add_hist2d(data=df, mapping=aes(x="x", y="y"), bins=25)
    return c | pt.legend(c)


PLOTS = {
    "hist2d": chart_hist2d,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_hist2d_baseline(name, fn, baseline_compare):
    baseline_compare("chart_hist2d", name, fn().to_svg())


def test_hist2d_counts_and_transparent_empties():
    import re
    df = {"x": [0.5, 0.5, 1.5, 2.5], "y": [0.5, 0.5, 0.5, 1.5]}
    c = pt.chart(df)
    c.add_hist2d(aes(x="x", y="y"), bins=([0, 1, 2, 3], [0, 1, 2]))
    svg = c.to_svg()
    assert 'data-plotlet-count-max="2"' in svg
    assert 'data-plotlet-bins-x="3"' in svg
    assert 'data-plotlet-bins-y="2"' in svg
    # 3 occupied cells drawn, 3 empty cells transparent (no rect at all)
    assert len(re.findall(r'fill="rgb\(', svg)) == 3


def test_hist2d_validation():
    df = {"x": [1, 2], "y": [1, 2]}
    c = pt.chart(df)
    c.add_hist2d(aes(x="x", y="y"), bins=5, binwidth=0.5)
    with pytest.raises(TypeError, match="bins= or binwidth="):
        c.to_svg()


def test_hist2d_two_item_bins():
    # bins=[0, 5] is a shared edge sequence (0 can't be a bin count) —
    # the int form must mean the same as the float form, not (0, 5) counts
    df = {"x": [1.0, 2.0, 4.0], "y": [1.0, 2.0, 4.0]}
    for edges in ([0, 5], [0.0, 5.0]):
        c = pt.chart(df)
        c.add_hist2d(aes(x="x", y="y"), bins=edges)
        svg = c.to_svg()
        assert 'data-plotlet-bins-x="1"' in svg
        assert 'data-plotlet-count-max="3"' in svg
    # a valid 2-int pair keeps the numpy (x_bins, y_bins) meaning
    c = pt.chart(df)
    c.add_hist2d(aes(x="x", y="y"), bins=[2, 5])
    svg = c.to_svg()
    assert 'data-plotlet-bins-x="2"' in svg
    assert 'data-plotlet-bins-y="5"' in svg


def test_hist2d_cell_color_matches_legend_norm():
    # vmin=0 must reach the norm untouched — the old `vmin or 1e-9`
    # rewrite nudged count=1 with vmax=2 across the t=0.5 LUT boundary,
    # so cells and the legend gradient disagreed by one LUT level
    df = {"x": [0.5], "y": [0.5]}
    c = pt.chart(df)
    c.add_hist2d(aes(x="x", y="y"), bins=([0, 1], [0, 1]), vmin=0, vmax=2)
    r, g, b = pt.colormap("viridis")(0.5)
    assert f'fill="rgb({r},{g},{b})"' in c.to_svg()


def test_hist2d_all_nan_column_is_empty():
    # valid x + all-NaN y must take the same empty-record path all-NaN x
    # does, not crash in min([])
    nan = float("nan")
    for xs, ys in (([1.0, 2.0], [nan, nan]), ([nan, nan], [1.0, 2.0])):
        df = {"x": xs, "y": ys}
        c = pt.chart(df)
        c.add_hist2d(aes(x="x", y="y"))
        assert 'data-plotlet-n="0"' in c.to_svg()


def test_hist2d_binwidth_pair():
    df = {"x": [0.25, 1.25], "y": [0.5, 2.5]}
    c = pt.chart(df)
    c.add_hist2d(aes(x="x", y="y"), binwidth=(0.5, 1.0), binrange=((0, 2), (0, 3)))
    svg = c.to_svg()
    assert 'data-plotlet-bins-x="4"' in svg
    assert 'data-plotlet-bins-y="3"' in svg
