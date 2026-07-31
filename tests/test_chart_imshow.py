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

from _chart_helpers import _embedded_png, _png_dims
from plotlet.artists._shared import pool_grid, pool_mean, pool_mode, pool_target


def chart_imshow_rect():
    data = [[math.sin(r * 0.4) * math.cos(c * 0.3) for c in range(20)]
            for r in range(15)]
    c = pt.chart(title="imshow (rect path)", xlabel="col", ylabel="row")
    c.add_imshow(data, cmap="viridis")
    c.legend()
    return c


def chart_imshow_png():
    data = [[math.sin(r * 0.07) + math.cos(c * 0.05) for c in range(160)]
            for r in range(120)]
    c = pt.chart(title="imshow (PNG path, magma)", xlabel="col", ylabel="row")
    c.add_imshow(data, cmap="magma")
    c.legend()
    return c


def chart_imshow_diverging():
    data = [[(r - 7) * (c - 7) for c in range(15)] for r in range(15)]
    c = pt.chart(title="imshow (bwr, extent, vmin/vmax)",
                 xlabel="x", ylabel="y")
    c.add_imshow(data, cmap="bwr", extent=(-1.5, 1.5, -1.5, 1.5),
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
    c.add_imshow(data, cmap="viridis", origin="upper",
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
    c.add_imshow(data, cmap="RdBu_r", center=0, vmin=-2, vmax=8,
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
    c.add_imshow(data, cmap="bwr2_demo", center=0, legend={"label": "value"})
    c.legend()
    return c


def chart_imshow_log_norm():
    # Multi-decade dynamic range — without log, all but the brightest
    # cells render near-black; with log, structure across decades shows.
    # Legend ticks are powers of 10.
    data = [[10 ** (0.05 * r + 0.05 * c) for c in range(20)] for r in range(15)]
    c = pt.chart(title="imshow norm='log'", xlabel="x", ylabel="y")
    c.add_imshow(data, cmap="magma", norm="log",
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
    c.add_imshow(data, cmap="viridis", origin="upper",
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
    c.add_imshow(data, cmap="viridis", annot=True, fmt=".1f")
    return c


def chart_imshow_png_pooled():
    # 150x150 grid in a 40x40-px data region — far past what the display
    # can resolve. The PNG path mean-pools down to `raster_oversample`
    # pixels per display pixel (an 80x80 image), which both bounds the
    # SVG and shows bin means instead of a nearest-neighbour subsample.
    data = [[math.sin(r * 0.4) + math.cos(c * 0.3) for c in range(150)]
            for r in range(150)]
    c = pt.chart(title="imshow (pooled PNG)", data_width=40, data_height=40)
    c.add_imshow(data, cmap="viridis")
    return c


PLOTS = {
    "imshow_rect": chart_imshow_rect,
    "imshow_png": chart_imshow_png,
    "imshow_png_pooled": chart_imshow_png_pooled,
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


def _dense_imshow(data_width, data_height):
    data = [[(r + c) % 7 for c in range(150)] for r in range(150)]
    c = pt.chart(data_width=data_width, data_height=data_height)
    c.add_imshow(data)
    return c.to_svg()


def test_imshow_png_downsamples_to_display_resolution():
    # 150x150 cells in 40x40 px → pooled to ceil(40 * raster_oversample)
    # = 80 per axis, and the markup says so.
    svg = _dense_imshow(40, 40)
    assert 'downsampled="true"' in svg
    assert _png_dims(_embedded_png(svg)) == (80, 80)


def test_imshow_png_full_resolution_when_it_fits():
    # Same grid with room to show every cell → untouched, no attr.
    svg = _dense_imshow(400, 400)
    assert "downsampled" not in svg
    assert _png_dims(_embedded_png(svg)) == (150, 150)


def test_vectorized_png_matches_scalar_bytes():
    # The vectorized pool + colormap pass must produce byte-identical
    # output to the scalar walk — that equality is what keeps SVG
    # byte-identical across machines and numpy versions. Exercised with
    # uneven pooling bins (37x23 -> 10x7), NaN and None cells, and both
    # vectorizable norms (linear, center).
    from plotlet.artists._shared import (png_value_cells, pool_grid,
                                         pool_mean, rgb_buffer)
    from plotlet.draw import colormap_lut, ContinuousNorm
    from plotlet.artists.imshow import _cell_rgb

    rows = [[math.sin(r * 1.7 + c * 0.9) * 10 for c in range(23)]
            for r in range(37)]
    rows[3][4] = float("nan")
    rows[20][22] = None
    rows[36][0] = float("nan")
    absent = (7, 8, 9)
    lut = colormap_lut("viridis")

    def scalar_rgb(v, norm):
        if v is None or v != v:
            return absent
        return _cell_rgb(v, norm, lut)

    for norm in (ContinuousNorm(-8.0, 9.0),
                 ContinuousNorm(-8.0, 9.0, center=0.5)):
        for out_h, out_w in ((10, 7), (37, 23)):
            fast, pooled = png_value_cells(rows, out_h, out_w,
                                           norm, lut, absent)
            assert pooled == ((out_h, out_w) != (37, 23))
            grid = rows if not pooled \
                else pool_grid(rows, out_h, out_w, pool_mean)
            slow = rgb_buffer(grid, lambda v: scalar_rgb(v, norm))
            assert fast == bytes(slow)


def test_imshow_log_norm_dense_falls_back_and_pools():
    # norm="log" has no vector form (np.log10 isn't bit-pinned across
    # machines) — the PNG path must fall back to the scalar walk and
    # still pool to display resolution.
    data = [[10 ** (0.001 * (r + c)) for c in range(150)] for r in range(150)]
    c = pt.chart(data_width=40, data_height=40)
    c.add_imshow(data, norm="log")
    svg = c.to_svg()
    assert 'downsampled="true"' in svg
    assert _png_dims(_embedded_png(svg)) == (80, 80)


def test_pool_helpers():
    nan = float("nan")
    # Mean pooling ignores NaN within a bin.
    assert pool_grid([[1.0, 3.0, nan, 5.0],
                      [2.0, 4.0, nan, nan]], 1, 2, pool_mean) == [[2.5, 5.0]]
    # An all-NaN bin stays NaN (renders as the absent color).
    v = pool_grid([[nan]], 1, 1, pool_mean)[0][0]
    assert v != v
    # Mode: majority wins, ties break to first-seen, NaN folds into None.
    assert pool_mode(["a", "b", "b"]) == "b"
    assert pool_mode(["a", "b"]) == "a"
    assert pool_mode([nan, None, "z"]) is None
    # Target: full resolution until raster_oversample cells/px, then capped.
    assert pool_target(100, 100.0) == 100
    assert pool_target(300, 100.0) == 200
