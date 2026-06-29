"""Baseline tests for CircularCoordinate (panel-level non-affine coordinate).

Each plot wires a standard plotlet artist through
``c.coordinate(CircularCoordinate())`` and renders the chart through the
core warp_svg / draw_frame / draw_x_frame / draw_x_sector_chrome /
clip_path_d hooks — no cookbook ``circular()`` helper involved.
``ring_x_sectors`` exercises the Circos-style x-sector chrome (wall pairs,
ring-arc segments, wrap-around gap).  ``test_circular_with_y_sectors_raises``
pins the NotImplementedError guard for the deferred y-sector case.
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

_N_LINE = 12
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


def ring_line_chords():
    # `arc=False` — endpoints still warp to the right angle/ring, but
    # connecting segments are literal Cartesian chords (no per-edge
    # subdivision). Same data as `ring_line` so the two baselines are a
    # direct visual pair: same sample points, arc on vs off.
    c = _ring_chart("line — chords (arc=False)")
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#1D9E75", width=1.5, arc=False)
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


def ring_x_sectors():
    # Three named wedges with a continuous-sector scale on x. Data carries
    # a `sec` tag so the sector remap routes each point to its wedge;
    # line+scatter inside each wedge exercises warp_svg + per-sector ring
    # arc segments.
    sec_names = ["A", "B", "C"]
    sec_lens  = [0.45, 0.30, 0.25]
    ts_per    = 30
    pts_x, pts_y, pts_sec = [], [], []
    for sname, slen in zip(sec_names, sec_lens):
        for i in range(ts_per):
            t_in = (i + 0.5) / ts_per
            pts_x.append(t_in * slen)
            pts_y.append(_clamp01(0.5 + 0.35 * math.sin(4 * math.pi * t_in)))
            pts_sec.append(sname)

    c = pt.chart(title="ring — x-sectors",
                 xlim=(0, 1), ylim=(0, 1),
                 data_width=320, data_height=320)
    # `wrap_gap_deg=12` gives a visible whitespace gap at the 12 o'clock
    # wrap-around, comparable to the internal sector gaps from `gap=12`
    # px. Note: `gap` lives on the `Sectors` constructor — passing it as
    # a kwarg to `c.sectors()` alongside a pre-built Sectors is silently
    # dropped (kwargs are ignored when the spec is already a Sectors).
    c.coordinate(pt.CircularCoordinate(wrap_gap_deg=12))
    c.sectors(
        pt.Sectors(names=tuple(sec_names), lengths=tuple(sec_lens), gap=12),
        axis="x", column="sec",
    )
    c.yticks([0.0, 0.5, 1.0])
    # Per-sector line calls — a single polyline through all 90 points
    # would draw chords across the gap whitespace where consecutive
    # points span sectors. One call per sector keeps each wedge's line
    # self-contained.
    for sname in sec_names:
        xs = [x for x, s in zip(pts_x, pts_sec) if s == sname]
        ys = [y for y, s in zip(pts_y, pts_sec) if s == sname]
        ss = [sname] * len(xs)
        c.line(data={"x": xs, "y": ys, "sec": ss},
               x="x", y="y", color="#1D9E75", width=1.2)
    # Scatter has no connections — single call is fine.
    c.scatter(data={"x": pts_x, "y": pts_y, "sec": pts_sec},
              x="x", y="y", color="#534AB7", size=2.5, alpha=0.7)
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

def test_circular_with_y_sectors_raises():
    # y-sectors with CircularCoordinate (concentric bands) is not yet
    # supported — pinning the guard. x-sectors ARE supported and exercised
    # by the `ring_x_sectors` baseline below.
    c = pt.chart(xlim=(0, 1), ylim=(0, 1), data_width=200, data_height=200)
    c.coordinate(pt.CircularCoordinate())
    c.sectors({"A": ["x"], "B": ["y"]}, axis="y")
    c.line(data={"x": [0, 0.5, 1.0], "y": [0, 0.5, 1.0]}, x="x", y="y")
    with pytest.raises(NotImplementedError, match="sectors"):
        c.to_svg()


# ---------------------------------------------------------------------------
# PLOTS registry and parametrized baseline test
# ---------------------------------------------------------------------------

PLOTS = {
    "ring_scatter":      ring_scatter,
    "ring_line":         ring_line,
    "ring_line_chords":  ring_line_chords,
    "ring_line_band":    ring_line_band,
    "ring_numeric_bar":  ring_numeric_bar,
    "ring_inner_outer":  ring_inner_outer,
    "ring_x_sectors":    ring_x_sectors,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_circular_coordinate_baseline(name, fn, baseline_compare):
    baseline_compare("circular_coordinate", name, fn().to_svg())
