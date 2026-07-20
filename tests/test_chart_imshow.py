"""Baseline SVG regression tests for the imshow artist/topic.

    pytest tests/test_chart_imshow.py
    pytest tests/test_chart_imshow.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
import pytest


def chart_imshow_rect():
    data = [[math.sin(r * 0.4) * math.cos(c * 0.3) for c in range(20)]
            for r in range(15)]
    c = pt.chart(title="imshow (rect path)", xlabel="col", ylabel="row")
    c.imshow(data, cmap="viridis")
    c.legend()
    return c


def chart_imshow_png():
    data = [[math.sin(r * 0.07) + math.cos(c * 0.05) for c in range(160)]
            for r in range(120)]
    c = pt.chart(title="imshow (PNG path, magma)", xlabel="col", ylabel="row")
    c.imshow(data, cmap="magma")
    c.legend()
    return c


def chart_imshow_diverging():
    data = [[(r - 7) * (c - 7) for c in range(15)] for r in range(15)]
    c = pt.chart(title="imshow (bwr, extent, vmin/vmax)",
                 xlabel="x", ylabel="y")
    c.imshow(data, cmap="bwr", extent=(-1.5, 1.5, -1.5, 1.5),
             vmin=-49, vmax=49)
    c.legend()
    return c


def chart_imshow_origin_upper():
    # origin="upper" opts into matrix-style display (row 0 at top). The
    # panel's y-axis auto-inverts so tick "0" lands at the top next to
    # row 0 — labels and image rows stay aligned.
    # Asymmetric ramp makes the flip vs. the default ("lower") obvious.
    data = [[r + 0.4 * c for c in range(20)] for r in range(15)]
    c = pt.chart(title="imshow origin='upper'", xlabel="x", ylabel="y")
    c.imshow(data, cmap="viridis", origin="upper",
             extent=(0, 20, 0, 15))
    c.legend()
    return c


def chart_imshow_diverging_center():
    # Asymmetric range (-2 to 8) with center=0 — colorbar shows zero
    # pinned to the middle of the strip even though zero is far from
    # the geometric midpoint of [-2, 8]. Explicit position="left" also
    # exercises the inline-colorbar left-side tick rendering.
    data = [[(r - 4) * 0.5 + (c - 4) * 0.7 for c in range(12)] for r in range(10)]
    c = pt.chart(title="imshow center=0", xlabel="x", ylabel="y")
    c.imshow(data, cmap="RdBu_r", center=0, vmin=-2, vmax=8,
             legend={"label": "value"})
    c.legend(True, position="left")
    return c


def chart_imshow_user_cmap():
    # register_colormap flows through both the imshow cell path and the
    # gradient legend; center=0 pins the white anchor to zero on the
    # asymmetric range, so anchoring stays the norm's job.
    pt.register_colormap("bwr2_demo", ["#2166ac", "#f7f7f7", "#b2182b"])
    data = [[(r - 4) * 0.5 + (c - 4) * 0.7 for c in range(12)] for r in range(10)]
    c = pt.chart(title="user colormap (bwr2_demo)", xlabel="x", ylabel="y")
    c.imshow(data, cmap="bwr2_demo", center=0, legend={"label": "value"})
    c.legend()
    return c


def chart_imshow_log_norm():
    # Multi-decade dynamic range — without log, all but the brightest
    # cells render near-black; with log, structure across decades shows.
    # Legend ticks are powers of 10.
    data = [[10 ** (0.05 * r + 0.05 * c) for c in range(20)] for r in range(15)]
    c = pt.chart(title="imshow norm='log'", xlabel="x", ylabel="y")
    c.imshow(data, cmap="magma", norm="log",
             legend={"label": "intensity"})
    c.legend(True)
    return c


def chart_imshow_annot_custom():
    # annot=<2D array> for independent labels; annot_color fixed.
    # Mixes numbers (formatted via fmt) and strings (verbatim).
    data = [[i + j for j in range(4)] for i in range(3)]
    annot = [["a", "b", "c", "d"],
             [1.0, 2.5, 3.75, 4.125],
             ["x", "y", "z", "w"]]
    c = pt.chart(title="imshow (custom annot, fixed color)")
    c.imshow(data, cmap="viridis", origin="upper",
             annot=annot, fmt=".1f", annot_color="#222222", annot_fontsize=12)
    c.legend()
    return c


def chart_imshow_annot_auto():
    # annot=True labels each cell with its own value; annot_color="auto"
    # flips black/white by cell luminance. The NaN cell renders black
    # and gets no label.
    data = [[0.5, 2.0, 4.5],
            [6.0, float("nan"), 8.0],
            [9.5, 7.5, 1.0]]
    c = pt.chart(title="imshow (annot=True, auto color)")
    c.imshow(data, cmap="viridis", annot=True, fmt=".1f")
    return c


PLOTS = {
    "imshow_rect": chart_imshow_rect,
    "imshow_png": chart_imshow_png,
    "imshow_diverging": chart_imshow_diverging,
    "imshow_origin_upper": chart_imshow_origin_upper,
    "imshow_center": chart_imshow_diverging_center,
    "imshow_user_cmap": chart_imshow_user_cmap,
    "imshow_log": chart_imshow_log_norm,
    "imshow_annot_custom": chart_imshow_annot_custom,
    "imshow_annot_auto": chart_imshow_annot_auto,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_imshow_baseline(name, fn, baseline_compare):
    baseline_compare("chart_imshow", name, fn().to_svg())
