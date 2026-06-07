#!/usr/bin/env python3
"""Baseline SVG regression tests for the layout-level legend.

    python tests/test_legend.py            # check vs. baselines, exit 1 on mismatch
    python tests/test_legend.py --update   # regenerate baselines (review the diff!)
    python tests/test_legend.py --gallery  # write baseline_images/legend/index.html

The in-frame overlay (`chart.legend(True)` / `legend=True`) is exercised
incidentally inside `tests/test_chart.py`. This file is dedicated to the
layout-level renderer in `plotlet/legend.py` — `pt.legend()` panel form,
grouping by source `title`, continuous
gradient strips for sources with `legend_gradient` (today: `imshow`),
and content-driven sizing.

Each plot below bundles several features so the suite isn't dominated by
near-duplicate baselines:

  legend_auto_grouped — `parent | pt.legend()` composition, no-source
                        auto-harvest, default grouping with chart `title`
                        headers, content-driven auto-sizing.
  legend_continuous   — pt.legend(hm) panel form with a continuous source;
                        per-imshow legend={"label", "ticks"} override.
  legend_mixed        — pt.legend() panel form harvesting both an imshow
                        (gradient strip) and a labeled line panel (swatch
                        row) — continuous stacks above discrete in-section.
  legend_overrides    — three sources with names={a: "Custom", b: None}
                        exercising the rename + hide-header paths.
  legend_flat_fixed   — group_by_chart=False flatten + explicit
                        `canvas_width=` / `canvas_height=` on the legend
                        leaf, overriding the content-driven auto-size.
  legend_joined_grid  — annotated-heatmap-shaped grid where the legend cell
                        sits next to a join-pair-collapsed assembly. Tests
                        that legend_gap (6 px) coexists with share-pair
                        zero-gaps in the same grid, and that the legend
                        cell is excluded from `_propagate_grid_joins` so
                        its row/column neighbors keep their own margins.
"""
from __future__ import annotations

import math
import sys

import plotlet as pt



def _xs():
    return [i * 0.1 for i in range(64)]


def _matrix():
    """Smooth 6x8 gradient — legible heatmap baseline for legend tests."""
    return [[(r + c) / 12.0 for c in range(8)] for r in range(6)]


def legend_auto_grouped():
    xs = _xs()
    a = pt.chart(title="alpha", data_width=180, data_height=140)
    a.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin")
    b = pt.chart(title="beta", data_width=180, data_height=140)
    b.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y", label="cos")
    return (a | b) | pt.legend()


def legend_continuous():
    hm = pt.chart(title="heat", data_width=320, data_height=180)
    hm.imshow(_matrix(), cmap="viridis",
              legend={"label": "intensity", "ticks": [0.0, 0.5, 1.0]})
    return hm | pt.legend(hm)


def legend_mixed():
    xs = _xs()
    im = pt.chart(title="heat", data_width=180, data_height=140)
    im.imshow(_matrix(), cmap="plasma")
    lines = pt.chart(title="trace", data_width=180, data_height=140)
    lines.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin")
    lines.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y", label="cos")
    return im | lines | pt.legend()


def legend_overrides():
    xs = _xs()
    a = pt.chart(title="alpha", data_width=100, data_height=140)
    a.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin")
    b = pt.chart(title="beta", data_width=100, data_height=140)
    b.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y", label="cos")
    c = pt.chart(title="gamma", data_width=100, data_height=140)
    c.line(data={"x": xs, "y": [math.sin(x) + 0.5 for x in xs]}, x="x", y="y", label="sin+0.5")
    return a | b | c | pt.legend(a, b, c, names={a: "Custom", b: None})


def legend_flat_fixed():
    # `pt.legend(canvas_width=…, canvas_height=…)` sets explicit canvas
    # dims on the legend leaf (legends don't have data axes — canvas IS
    # the dimensional primitive). Overrides the content-driven auto-size.
    xs = _xs()
    a = pt.chart(title="alpha", data_width=160, data_height=140)
    a.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin")
    b = pt.chart(title="beta", data_width=160, data_height=140)
    b.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y", label="cos")
    return a | b | pt.legend(a, b, group_by_chart=False,
                             canvas_width=140, canvas_height=160)


def legend_joined_grid():
    # Top track shares x with main (column 1); left tree shares y with main
    # (row 1). Both share-pairs are gap-collapsed (0 px). Legend sits to
    # the right of main with legend_gap (6 px) — distinct from the
    # share-pair joint.
    main = pt.chart(title="main", data_width=320, data_height=180)
    main.imshow(_matrix(), cmap="viridis", legend={"label": "value"})
    top  = pt.chart(title="top",  data_width=320, data_height=24)
    top.line(data={"x": [0, 1, 2, 3, 4, 5, 6, 7], "y": [3, 1, 2, 4, 1, 2, 3, 1]},
             x="x", y="y", label="counts")
    tree = pt.chart(title="tree", data_width=60,  data_height=180)
    tree.line(data={"x": [0, 1, 2], "y": [2, 3, 4]}, x="x", y="y")
    return pt.grid([
        [None, top,  None        ],
        [tree, main, pt.legend() ],
    ]).share_x("col").share_y("row")


def legend_gap_override():
    # `pt.legend(..., legend_gap=N)` overrides the default 6 px separation
    # between legend and source. Here we widen it to 24 — the legend sits
    # well clear of `hm`, distinct from a share-pair joint (which would be 0).
    hm = pt.chart(title="hm", data_width=240, data_height=140)
    hm.imshow(_matrix(), cmap="viridis")
    return hm | pt.legend(hm, legend_gap=24)


PLOTS = {
    "legend_auto_grouped": legend_auto_grouped,
    "legend_continuous":   legend_continuous,
    "legend_mixed":        legend_mixed,
    "legend_overrides":    legend_overrides,
    "legend_flat_fixed":   legend_flat_fixed,
    "legend_joined_grid":  legend_joined_grid,
    "legend_gap_override": legend_gap_override,
}


import pytest

@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_legend_baseline(name, fn, baseline_compare):
    baseline_compare("legend", name, fn().to_svg())
