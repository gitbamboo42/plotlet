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
  legend_swatch_overrides — per-artist `legend={...}` customization:
                        `{"glyph": "rect"}` renders the standard rect
                        swatch instead of the artist's tiny scatter marker
                        (size-aesthetic guide keeps its graded dots —
                        grouped entries are exempt); aesthetic overrides
                        (`{"alpha": 1}` on a translucent scatter) restyle
                        the key without touching the plot.
  legend_ncols        — `pt.legend(ncols=3)` wraps a 12-level categorical
                        list into 3 columns (filled down-then-across);
                        the size-aesthetic guide block wraps independently
                        below its own header.
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


def legend_colorbar_bottom():
    # Gradient-only + position="bottom" → horizontal colorbar under the
    # data area (vmin left, ticks below the strip).
    hm = pt.chart(title="heat", data_width=320, data_height=180)
    hm.imshow(_matrix(), cmap="viridis", legend={"label": "intensity"})
    hm.legend(True, position="bottom")
    return hm


def legend_colorbar_top():
    hm = pt.chart(title="heat", data_width=320, data_height=180)
    hm.imshow(_matrix(), cmap="plasma")
    hm.legend(True, position="top")
    return hm


def legend_mixed():
    xs = _xs()
    im = pt.chart(title="heat", data_width=180, data_height=140)
    im.imshow(_matrix(), cmap="plasma")
    lines = pt.chart(title="trace", data_width=180, data_height=140)
    lines.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin")
    lines.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y", label="cos")
    return im | lines | pt.legend()


def legend_reverse_manual():
    # reverse=True flips each section's discrete order; entries= appends
    # a free-form manual section (label + color, default rect swatch).
    xs = _xs()
    a = pt.chart(title="alpha", data_width=220, data_height=150)
    a.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin")
    a.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y", label="cos")
    return a | pt.legend(a, reverse=True,
                         entries=[{"label": "threshold", "color": "red"},
                                  {"label": "baseline", "color": "0.6"}])


def legend_inline_manual():
    xs = _xs()
    c = pt.chart(data_width=280, data_height=160)
    c.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin")
    c.legend(True, position="right",
             entries=[{"label": "cutoff", "color": "C3", "alpha": 0.4}])
    return c


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


def legend_swatch_overrides():
    # 1.5 px markers are unreadable as legend keys — `legend={"glyph":
    # "rect"}` swaps the series swatch for the standard rectangle. On `b`
    # the size guide keeps its graded dots: the override skips grouped
    # (aesthetic-guide) entries, only the "signal" label row becomes a rect.
    # On `c` the points are near-invisible at alpha=0.15 but the legend
    # key paints opaque and enlarged via aesthetic overrides.
    xs = [i * 0.2 for i in range(50)]
    df = {"x": xs,
          "y": [math.sin(x) for x in xs],
          "grp": ["even" if i % 2 == 0 else "odd" for i in range(50)],
          "mass": [1.0 + (i % 7) for i in range(50)]}
    a = pt.chart(title="tiny", data_width=200, data_height=140)
    a.scatter(data=df, x="x", y="y", color="grp", size=1.5,
              legend={"glyph": "rect"})
    b = pt.chart(title="sized", data_width=200, data_height=140)
    b.scatter(data=df, x="x", y="y", size="mass", sizes=(1, 5),
              label="signal", legend={"glyph": "rect"})
    c = pt.chart(title="faint", data_width=200, data_height=140)
    c.scatter(data=df, x="x", y="y", color="grp", alpha=0.15, size=2,
              legend={"alpha": 1, "size": 5})
    return (a | b | c) | pt.legend()


def legend_ncols():
    # 12 categories single-column would tower over the 160 px chart —
    # ncols=3 wraps them into 3 columns of 4 rows, short enough to sit
    # beside the chart in the usual right-hand position. The size guide
    # (a grouped block with its own header) wraps independently: 4 dots
    # at ncols=3 → 2 rows in 2 columns.
    n = 60
    cats = [f"type-{i % 12:02d}" for i in range(n)]
    df = {"x": [i * 0.1 for i in range(n)],
          "y": [math.sin(i * 0.35) + (i % 12) * 0.1 for i in range(n)],
          "cat": cats,
          "mass": [1.0 + (i % 9) for i in range(n)]}
    a = pt.chart(title="many levels", data_width=260, data_height=160)
    a.scatter(data=df, x="x", y="y", color="cat", size="mass", sizes=(1.5, 5))
    return a | pt.legend(ncols=3)


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
    "legend_colorbar_bottom": legend_colorbar_bottom,
    "legend_colorbar_top":  legend_colorbar_top,
    "legend_mixed":        legend_mixed,
    "legend_reverse_manual": legend_reverse_manual,
    "legend_inline_manual": legend_inline_manual,
    "legend_overrides":    legend_overrides,
    "legend_flat_fixed":   legend_flat_fixed,
    "legend_swatch_overrides": legend_swatch_overrides,
    "legend_ncols":        legend_ncols,
    "legend_joined_grid":  legend_joined_grid,
    "legend_gap_override": legend_gap_override,
}


import pytest

@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_legend_baseline(name, fn, baseline_compare):
    baseline_compare("legend", name, fn().to_svg())


def test_legend_ncols_invalid_raises():
    with pytest.raises(ValueError, match="ncols"):
        pt.legend(ncols=0)
    with pytest.raises(ValueError, match="ncols"):
        pt.legend(ncols=2.5)
    with pytest.raises(ValueError, match="ncols"):
        pt.chart().legend(ncols=0)


def test_inline_reverse_keeps_manual_entries_last():
    # Same contract as the pt.legend() leaf: reverse= flips each
    # section internally; entries= rows stay appended after the
    # harvested ones — not flipped to the front.
    import re
    xs = [0.0, 1.0, 2.0]

    def swatch_ys(reverse):
        c = pt.chart(data_width=200, data_height=120)
        c.line(data={"x": xs, "y": [1, 2, 1]}, x="x", y="y", label="sin")
        c.line(data={"x": xs, "y": [2, 1, 2]}, x="x", y="y", label="cos")
        c.legend(True, position="right", reverse=reverse,
                 entries=[{"label": "manual", "color": "#123456"}])
        svg = c.to_svg()
        # harvested line swatches: stroked segments; manual row: rect
        line_ys = [float(y) for y in
                   re.findall(r'<line[^>]*y1="([\d.]+)"[^>]*stroke="#(?:1f77b4|ff7f0e)"', svg)]
        manual_y = float(re.search(
            r'<rect[^>]*y="([\d.]+)"[^>]*fill="#123456"', svg).group(1))
        return line_ys, manual_y

    for reverse in (False, True):
        line_ys, manual_y = swatch_ys(reverse)
        assert len(line_ys) == 2
        assert manual_y > max(line_ys)


def test_legend_glyph_unknown_raises():
    c = pt.chart(data_width=120, data_height=100)
    c.scatter(data={"x": [1, 2], "y": [1, 2]}, x="x", y="y",
              label="s", legend={"glyph": "circle"})
    fig = c | pt.legend()
    with pytest.raises(ValueError, match="glyph"):
        fig.to_svg()
