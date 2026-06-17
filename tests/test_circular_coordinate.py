"""Baseline tests for CircularCoordinate (panel-level non-affine coordinate).

Each plot wires a standard plotlet artist through
``c.coordinate(CircularCoordinate())`` and renders the chart through the
core warp_svg / draw_frame / draw_x_frame / clip_path_d hooks — no
cookbook ``circular()`` helper involved.  The sector_error test pins the
NotImplementedError guard when sectors are combined with a ring.
"""
from __future__ import annotations

import math
import random

import plotlet as pt
import plotlet.extensions.numeric_bar  # noqa — registers numeric_bar
import pytest


# ---------------------------------------------------------------------------
# Shared deterministic data
# ---------------------------------------------------------------------------

def _clamp01(v):
    return max(0.0, min(1.0, v))


_RNG = random.Random(11)

_N_LINE = 80
_LINE_TS = [i / _N_LINE for i in range(_N_LINE + 1)]
_LINE_V  = [_clamp01(0.5 + 0.35 * math.sin(2 * math.pi * t)) for t in _LINE_TS]
_BAND_LO = [_clamp01(v - 0.08) for v in _LINE_V]
_BAND_HI = [_clamp01(v + 0.08) for v in _LINE_V]

_SCATTER_T = [_RNG.random() for _ in range(60)]
_SCATTER_V = [_clamp01(0.5 + 0.4 * math.sin(2 * math.pi * t)
                       + _RNG.gauss(0, 0.06))
              for t in _SCATTER_T]

_N_BAR = 24
_BAR_T = [(i + 0.5) / _N_BAR for i in range(_N_BAR)]
_BAR_V = [_clamp01(0.3 + 0.5 * abs(math.sin(2 * math.pi * t))) for t in _BAR_T]


def _ring_chart(title):
    c = pt.chart(title=title, xlim=(0, 1), ylim=(0, 1),
                 data_width=300, data_height=300)
    c.coordinate(pt.CircularCoordinate())
    c.xticks([0.0, 0.25, 0.5, 0.75])
    c.yticks([0.0, 0.5, 1.0])
    return c


# ---------------------------------------------------------------------------
# Single-artist rings
# ---------------------------------------------------------------------------

def ring_scatter():
    c = _ring_chart("scatter — ring")
    c.scatter(data={"x": _SCATTER_T, "y": _SCATTER_V}, x="x", y="y",
              color="#534AB7", size=3, alpha=0.55)
    return c


def ring_line():
    c = _ring_chart("line — ring")
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#1D9E75", width=1.5)
    return c


def ring_line_band():
    c = _ring_chart("line + band — ring")
    c.fill_between(data={"x": _LINE_TS, "lo": _BAND_LO, "hi": _BAND_HI},
                   x="x", y1="lo", y2="hi", fill="#1D9E75", alpha=0.25)
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#1D9E75", width=1.5)
    return c


def ring_numeric_bar():
    c = _ring_chart("numeric_bar — ring")
    c.numeric_bar(data={"x": _BAR_T, "y": _BAR_V}, x="x", y="y",
                  width=0.025, color="#D9534F", alpha=0.85)
    return c


def ring_inner_outer():
    # Custom inner radius — exercises the r_inner=0.55 path so the
    # geometry helper isn't accidentally collapsed to defaults.
    c = pt.chart(title="ring — r_inner=0.55", xlim=(0, 1), ylim=(0, 1),
                 data_width=300, data_height=300)
    c.coordinate(pt.CircularCoordinate(r_inner=0.55, gap=0.08))
    c.xticks([0.0, 0.5])
    c.yticks([0.0, 1.0])
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#534AB7", width=1.5)
    return c


# ---------------------------------------------------------------------------
# Sector × CircularCoordinate guard
# ---------------------------------------------------------------------------

def test_circular_with_x_sectors_raises():
    # Categorical sectors (don't require a column= tag) — minimal repro.
    c = pt.chart(xlim=(0, 1), ylim=(0, 1), data_width=200, data_height=200)
    c.coordinate(pt.CircularCoordinate())
    c.sectors({"A": ["x"], "B": ["y"]}, axis="x")
    c.line(data={"x": [0, 0.5, 1.0], "y": [0, 0.5, 1.0]}, x="x", y="y")
    with pytest.raises(NotImplementedError, match="sectors"):
        c.to_svg()


# ---------------------------------------------------------------------------
# PLOTS registry and parametrized baseline test
# ---------------------------------------------------------------------------

PLOTS = {
    "ring_scatter":      ring_scatter,
    "ring_line":         ring_line,
    "ring_line_band":    ring_line_band,
    "ring_numeric_bar":  ring_numeric_bar,
    "ring_inner_outer":  ring_inner_outer,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_circular_coordinate_baseline(name, fn, baseline_compare):
    baseline_compare("circular_coordinate", name, fn().to_svg())
