"""Baseline SVG regression tests for the facets artist/topic.

    pytest tests/test_chart_facets.py
    pytest tests/test_chart_facets.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest
from _chart_helpers import _facet_grid_df, _unit_px_ratio


def chart_facet_scatter():
    # Facet by category: one panel per unique value, shared axes, titles
    # default to the group label.
    random.seed(11)
    species = ["setosa", "versicolor", "virginica"]
    n_each = 24
    df = {
        "bill_length": [random.gauss(5, 1) + i * 2 for i in range(3) for _ in range(n_each)],
        "bill_depth":  [random.gauss(3, 0.4) + i * 0.5 for i in range(3) for _ in range(n_each)],
        "species":     [s for s in species for _ in range(n_each)],
    }
    g = pt.facet(df, by="species", col_wrap=3,
                 data_width=180, data_height=140,
                 xlabel="bill_length", ylabel="bill_depth")
    g.scatter(x="bill_length", y="bill_depth", size=2)
    return g


def chart_facet_wrap_two_rows():
    # 5 groups + col_wrap=3 → 2x3 grid with one empty trailing cell.
    random.seed(12)
    groups = ["A", "B", "C", "D", "E"]
    n = 30
    df = {
        "x": [i * 0.2 for _ in groups for i in range(n)],
        "y": [math.sin(i * 0.2) * (1.0 + gi * 0.3) + random.uniform(-0.3, 0.3)
              for gi, _ in enumerate(groups) for i in range(n)],
        "g": [grp for grp in groups for _ in range(n)],
    }
    g = pt.facet(df, by="g", col_wrap=3,
                 data_width=160, data_height=110,
                 xlabel="x", ylabel="y")
    g.line(x="x", y="y")
    return g


def chart_facet_grid_two_factor():
    # row= x col= grid: one grid row per sex, one column per stage, shared
    # axes. The (F, mid) combination has no rows -> blank cell.
    random.seed(13)
    df = {"x": [], "y": [], "sex": [], "stage": []}
    for sex in ("M", "F"):
        for stage in ("early", "mid", "late"):
            if sex == "F" and stage == "mid":
                continue
            for _ in range(18):
                df["x"].append(random.gauss(0, 1) + (1.5 if sex == "F" else 0))
                df["y"].append(random.gauss(0, 1) + (2 if stage == "late" else 0))
                df["sex"].append(sex)
                df["stage"].append(stage)
    g = pt.facet(df, row="sex", col="stage",
                 data_width=150, data_height=110,
                 xlabel="x", ylabel="y")
    g.scatter(x="x", y="y", size=2)
    return g


def chart_aspect_equal():
    # Data-space aspect lock: the ring reads as a circle because one
    # x unit and one y unit render the same pixel length (the requested
    # data_height is rederived from the resolved domains).
    angles = [i * math.pi / 36 for i in range(72)]
    df = {"x": [3 * math.cos(a) for a in angles],
          "y": [3 * math.sin(a) for a in angles]}
    c = pt.chart(df, title="aspect('equal') — circles stay circular",
                 data_width=320, data_height=200, xlabel="x", ylabel="y")
    c.scatter(x="x", y="y", size=2)
    c.aspect("equal")
    return c


PLOTS = {
    "facet_scatter": chart_facet_scatter,
    "facet_wrap_two_rows": chart_facet_wrap_two_rows,
    "facet_grid_two_factor": chart_facet_grid_two_factor,
    "aspect_equal": chart_aspect_equal,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_facets_baseline(name, fn, baseline_compare):
    baseline_compare("chart_facets", name, fn().to_svg())


def test_facet_grid_missing_combo_is_blank():
    g = pt.facet(_facet_grid_df(), row="r", col="c")
    g.scatter(x="x", y="y")
    assert g.to_svg().count('data-plotlet-kind="panel"') == 3


def test_facet_single_factor_orientation():
    import re

    def panel_origins(**facet_kw):
        g = pt.facet(_facet_grid_df(), **facet_kw)
        g.scatter(x="x", y="y")
        boxes = re.findall(r'data-plotlet-panel-bbox="([^"]*)"', g.to_svg())
        return [tuple(float(v) for v in b.split(",")[:2]) for b in boxes]

    rows = panel_origins(row="r")     # stacked: same x, distinct y
    assert len(rows) == 2
    assert rows[0][0] == rows[1][0] and rows[0][1] != rows[1][1]
    cols = panel_origins(col="c")     # side by side: distinct x, same y
    assert len(cols) == 2
    assert cols[0][0] != cols[1][0] and cols[0][1] == cols[1][1]


def test_facet_mode_validation():
    df = _facet_grid_df()
    with pytest.raises(TypeError, match="not both"):
        pt.facet(df, by="r", col="c")
    with pytest.raises(TypeError, match="requires by="):
        pt.facet(df)
    with pytest.raises(TypeError, match="col_wrap= applies to by="):
        pt.facet(df, row="r", col_wrap=2)


def test_facet_grid_json_roundtrip():
    import json
    from plotlet.record.journal import to_json, from_json

    def build():
        g = pt.facet(_facet_grid_df(), row="r", col="c")
        g.scatter(x="x", y="y")
        return g

    node = from_json(json.loads(json.dumps(to_json(build()))))
    assert node.to_svg() == build().to_svg()


def test_aspect_locks_unit_ratio():
    df = {"x": [0, 10], "y": [0, 5]}
    for r in (1.0, 2.0, 0.5):
        c = pt.chart(df, data_width=300, data_height=137)
        c.scatter(x="x", y="y")
        c.aspect(r)
        assert abs(_unit_px_ratio(c.to_svg()) - r) < 1e-9
    c = pt.chart(df, data_width=300)
    c.scatter(x="x", y="y")
    c.aspect("equal")
    assert abs(_unit_px_ratio(c.to_svg()) - 1.0) < 1e-9


def test_aspect_survives_fit():
    # The derived dim rounds to whole pixels, so after fit() the lock is
    # exact to half a pixel over the panel, not to float precision.
    c = pt.chart({"x": [0, 10], "y": [0, 5]}, data_width=300)
    c.scatter(x="x", y="y")
    c.aspect("equal")
    assert abs(_unit_px_ratio(c.fit(canvas_width=180).to_svg()) - 1.0) < 0.01


def test_aspect_anchor_height_propagates_to_share_class():
    import re
    a = pt.chart({"x": [0, 10], "y": [0, 5]}, data_width=200)
    a.scatter(x="x", y="y")
    a.aspect("equal")
    b = pt.chart({"x": [0, 10], "y": [0, 5]}, data_width=200)
    b.scatter(x="x", y="y")
    svg = (a | b).share_y().to_svg()
    heights = [box.split(",")[3] for box in
               re.findall(r'data-plotlet-data-area="([^"]*)"', svg)]
    assert len(heights) == 2 and heights[0] == heights[1]


def test_aspect_validation():
    c = pt.chart({"x": ["a", "b"], "y": [1, 2]})
    c.bar(x="x", y="y")
    c.aspect(1)
    with pytest.raises(ValueError, match="same scale kind"):
        c.to_svg()

    c = pt.chart({"x": [1, 100], "y": [0, 5]})
    c.scatter(x="x", y="y")
    c.xscale("log")
    c.aspect(1)
    with pytest.raises(ValueError, match="same scale kind"):
        c.to_svg()

    c = pt.chart({"x": [0, 1], "y": [0, 1]})
    c.scatter(x="x", y="y")
    c.aspect(-2)
    with pytest.raises(ValueError, match="positive"):
        c.to_svg()

    a = pt.chart({"x": [0, 1], "y": [0, 1]})
    a.scatter(x="x", y="y")
    b = pt.chart({"x": [0, 1], "y": [0, 1]})
    b.scatter(x="x", y="y")
    b.aspect(1)
    fig = (a | b).share_x(True).share_y(True)
    with pytest.raises(ValueError, match="sharing both axes"):
        fig.to_svg()


def test_facet_aspect_lock():
    # facet defaults share_x=share_y=True and replays aspect() onto every
    # panel; the forced anchor dims satisfy the lock (same union domains),
    # so this must render — with the ratio holding in each panel.
    import re
    g = pt.facet(_facet_grid_df(), col="c")
    g.scatter(x="x", y="y")
    g.aspect("equal")
    svg = g.to_svg()
    areas = re.findall(r'data-plotlet-data-area="([^"]*)"', svg)
    xlims = re.findall(r'data-plotlet-xlim="([^"]*)"', svg)
    ylims = re.findall(r'data-plotlet-ylim="([^"]*)"', svg)
    assert len(areas) == 2
    for area, xl, yl in zip(areas, xlims, ylims):
        w, h = [float(v) for v in area.split(",")[2:4]]
        x0, x1 = [float(v) for v in xl.split(",")]
        y0, y1 = [float(v) for v in yl.split(",")]
        assert abs((h / (y1 - y0)) / (w / (x1 - x0)) - 1.0) < 0.01
