"""Shared data-builder helpers for the split-out chart baseline suites.

Extracted verbatim from the former test_chart.py.
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes


class _MockDF:
    # Tiny stand-in for a pandas DataFrame so the DataFrameLite / duck-typed
    # `.values`/`.columns`/`.index` path gets exercised without a pandas dep.
    def __init__(self, values, index, columns):
        self.values = values
        self.index = index
        self.columns = columns


def _by_label(items, labels):
    """Group `items` by parallel `labels`, preserving first-seen group order.
    Returns ``{group: [items, ...]}`` — the categorical-Sectors shape."""
    out = {}
    for it, lbl in zip(items, labels):
        out.setdefault(lbl, []).append(it)
    return out


def _xs():
    return [i * 0.1 for i in range(64)]


def _tidy_heatmap(matrix, xlabels, ylabels, xname="col"):
    """Wide `matrix[y][x]` + axis labels → tidy dict for the heatmap's
    long-form input: each x label is a table row (→ a heatmap column),
    each y label is a value column (→ a track)."""
    data = {xname: list(xlabels)}
    for i, yl in enumerate(ylabels):
        data[yl] = list(matrix[i])
    return data


def _mock_tidy_df(tidy):
    """Wrap a tidy dict in a `_MockDF` (columns + row-major values) to
    exercise the DataFrameLite normalization path."""
    cols = list(tidy.keys())
    n = len(next(iter(tidy.values())))
    values = [[tidy[c][r] for c in cols] for r in range(n)]
    return _MockDF(values, index=list(range(n)), columns=cols)


def _dendro_sample():
    rng = random.Random(0)
    return [[rng.gauss(0, 1) for _ in range(4)] for _ in range(8)]


def _bar_quarterly_df():
    cats = ["Q1", "Q2", "Q3", "Q4"]
    labels = ["A", "B", "C"]
    series = [
        [12, 18, 15, 22],
        [ 8, 14, 16, 18],
        [ 5,  7,  9, 11],
    ]
    rows = []
    for i, cat in enumerate(cats):
        for j, lbl in enumerate(labels):
            rows.append({"quarter": cat, "series": lbl, "value": series[j][i]})
    return {"quarter": [r["quarter"] for r in rows],
            "series":  [r["series"] for r in rows],
            "value":   [r["value"] for r in rows]}


def _legend_position_chart(position):
    """A two-line chart with an outside-positioned in-frame legend. Used
    by the legend_outside_* baselines to exercise each `position=` value
    — the data region stays at the user-requested size; the canvas grows
    on the named side to accommodate the legend block."""
    xs = _xs()
    c = pt.chart(title=f"legend {position}",
                 xlabel="t", ylabel="value", gridlines=True,
                 data_width=300, data_height=180)
    df = {"x": xs, "y": [math.sin(x) for x in xs]}
    c.add_line(data=df, mapping=aes(x="x", y="y"), label="sin(t)")
    df2 = {"x": xs, "y": [math.cos(x) for x in xs]}
    c.add_line(data=df2, mapping=aes(x="x", y="y"), label="cos(t)", linestyle="--")
    c.legend(position=position)
    return c


def _peaks_grid(n=60):
    """Two-bump analytic surface shared by the contour-fill baselines."""
    grid = []
    for i in range(n):
        row = []
        for j in range(n):
            x = -3 + 6 * j / (n - 1)
            y = -3 + 6 * i / (n - 1)
            v = (math.exp(-(x * x + 1.5 * y * y) / 2)
                 + 0.5 * math.exp(-((x - 1.5) ** 2 + (y + 1.5) ** 2) / 0.6))
            row.append(v)
        grid.append(row)
    return grid


def _facet_grid_df():
    # 2x2 factor space with the (F, b) combination absent.
    return {
        "x": [1, 2, 3, 4, 5, 6],
        "y": [1, 2, 3, 4, 5, 6],
        "r": ["M", "M", "M", "M", "F", "F"],
        "c": ["a", "a", "b", "b", "a", "a"],
    }


def _unit_px_ratio(svg):
    """px-per-y-unit divided by px-per-x-unit for the (single) panel."""
    import re
    w, h = [float(v) for v in re.search(
        r'data-plotlet-data-area="([^"]*)"', svg).group(1).split(",")[2:4]]
    x0, x1 = [float(v) for v in re.search(
        r'data-plotlet-xlim="([^"]*)"', svg).group(1).split(",")]
    y0, y1 = [float(v) for v in re.search(
        r'data-plotlet-ylim="([^"]*)"', svg).group(1).split(",")]
    return (h / (y1 - y0)) / (w / (x1 - x0))


def _big_continuous_heatmap(with_y_sectors):
    tracks = [f"t{i}" for i in range(20)]
    data = {"x": [float(i) for i in range(501)]}
    for r, name in enumerate(tracks):
        data[name] = [math.sin(0.01 * i + r) for i in range(501)]
    c = pt.chart(data_width=400, data_height=300)
    if with_y_sectors:
        c.sectors({"A": tracks[:10], "B": tracks[10:]}, axis="y",
                  divider=False, label=False)
    c.add_heatmap(data=data, mapping=aes(x="x"), values=tracks, cmap="viridis")
    return c.to_svg()


def _png_dims(png: bytes) -> tuple[int, int]:
    """Width/height straight from the IHDR chunk."""
    import struct
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", png[16:24])
