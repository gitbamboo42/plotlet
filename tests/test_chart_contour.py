"""Baseline SVG regression tests for the contour artist/topic.

    pytest tests/test_chart_contour.py
    pytest tests/test_chart_contour.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest
from _chart_helpers import _peaks_grid


def chart_contour():
    c = pt.chart(data_width=300, data_height=300,
                 title="contour", xlabel="x", ylabel="y")
    c.contour(_peaks_grid(), extent=(-3, 3, -3, 3), cmap="viridis",
              levels=[0.05, 0.1, 0.2, 0.4, 0.6, 0.8])
    c.legend()
    return c


def chart_contour_filled():
    c = pt.chart(data_width=300, data_height=300,
                 title="filled contour", xlabel="x", ylabel="y")
    c.contour(_peaks_grid(), extent=(-3, 3, -3, 3), cmap="viridis",
              levels=[0.05, 0.1, 0.2, 0.4, 0.6, 0.8], fill=True)
    c.legend()
    return c


PLOTS = {
    "contour": chart_contour,
    "contour_filled": chart_contour_filled,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_contour_baseline(name, fn, baseline_compare):
    baseline_compare("chart_contour", name, fn().to_svg())


def test_filled_level_polys():
    from plotlet.artists._marching import filled_level_polys
    # fully-inside 2x3 grid → one merged rectangle per cell row
    polys = filled_level_polys([[1, 1, 1], [1, 1, 1]], 0.5, 2, 3)
    assert polys == [[(0, 0), (2, 0), (2, 1), (0, 1)]]
    # saddle (TL/BR inside) → two disconnected triangles, matching the
    # iso-line topology
    polys = filled_level_polys([[1.0, 0.0], [0.0, 1.0]], 0.5, 2, 2)
    assert len(polys) == 2 and all(len(p) == 3 for p in polys)
    # nothing above the level → nothing drawn
    assert filled_level_polys([[0.0, 0.0], [0.0, 0.0]], 0.5, 2, 2) == []


def test_contour_fill_replaces_lines():
    import re
    grid = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
    c = pt.chart()
    c.contour(grid, levels=[0.5], fill=True, cmap="viridis")
    svg = c.to_svg()
    body = re.search(
        r'<g[^>]*data-plotlet-type="contour"[^>]*>(.*?)</g>', svg, re.S
    ).group(1)
    assert "<path" in body and "<line" not in body


def test_contour_nan_cells_masked():
    from plotlet.artists._marching import filled_level_polys
    nan = float("nan")
    # NaN corner masks its cells; the finite half of the grid still fills
    polys = filled_level_polys([[1, 1, nan], [1, 1, nan]], 0.5, 2, 3)
    assert polys == [[(0, 0), (1, 0), (1, 1), (0, 1)]]
    # end-to-end: no NaN coordinate ever reaches the path data
    grid = [[0, 0, 0], [0, 1, nan], [0, 0, 0]]
    for fill in (True, False):
        c = pt.chart()
        c.contour(grid, levels=[0.5], fill=fill, cmap="viridis")
        svg = c.to_svg()
        assert "nan" not in svg
        assert 'data-plotlet-type="contour"' in svg
