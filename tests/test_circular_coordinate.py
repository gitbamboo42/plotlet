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
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#534AB7", width=1.5)
    return c


def ring_references():
    # Reference primitives under Circular: axhline → concentric ring,
    # axvline → radial spoke, hlines/vlines → bounded arc / spoke
    # segments, axhspan → ring band, axvspan → angular wedge.
    c = _ring_chart("references — ring")
    c.axhspan(0.65, 0.85, color="#9CC3D5", alpha=0.4)   # outer ring band
    c.axvspan(0.10, 0.30, color="#F2C57C", alpha=0.4)   # angular wedge
    c.axhline(0.50, color="#444", linewidth=1)          # mid ring
    c.axvline(0.50, color="#888", linestyle="--",
              linewidth=0.8)                            # half-turn spoke
    c.hlines([0.25, 0.75], [0.05, 0.55], [0.45, 0.95],
             color="#1D9E75", linewidth=1.2)
    c.vlines([0.20, 0.80], [0.10, 0.10], [0.60, 0.60],
             color="#D9534F", linewidth=1.2)
    return c


def ring_shapes():
    # Shape primitives under Circular: rect → annular sector, polygon →
    # warped closed contour, polyline → warped open stroke.
    c = _ring_chart("shapes — ring")
    c.rect(0.10, 0.20, 0.25, 0.40, color="#A0C4E2", alpha=0.5)
    poly_x = [0.55, 0.75, 0.85, 0.70, 0.55]
    poly_y = [0.30, 0.30, 0.55, 0.70, 0.55]
    c.polygon(poly_x, poly_y, color="#F2C57C", alpha=0.6)
    line_x = [0.05, 0.20, 0.40, 0.60, 0.80, 0.95]
    line_y = [0.90, 0.70, 0.85, 0.65, 0.80, 0.60]
    c.polyline(line_x, line_y, color="#534AB7", linewidth=1.5)
    return c


def ring_partial_arc():
    # Partial arc — `start_deg=90, end_deg=360` sweeps 270° clockwise
    # from 3 o'clock around through 6 / 9 / 12. Exercises the open-arc
    # spine path (no sectors) and y-tick placement along start_rad
    # (3 o'clock, the t=0 open edge).
    c = pt.chart(title="partial arc — 90°→360°", xlim=(0, 1), ylim=(0, 1),
                 data_width=320, data_height=320)
    c.coordinate(pt.CircularCoordinate(start_deg=90, end_deg=360))
    c.xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    c.yticks([0.0, 0.5, 1.0])
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#1D9E75", width=1.5)
    return c


def ring_partial_arc_right_side():
    # Same partial arc with `yticks(side="right")` — labels move to
    # `end_rad` (the t=1 open edge) instead of `start_rad`.
    c = pt.chart(title="partial arc — side=right", xlim=(0, 1), ylim=(0, 1),
                 data_width=320, data_height=320)
    c.coordinate(pt.CircularCoordinate(start_deg=90, end_deg=360))
    c.xticks([0.0, 0.5, 1.0])
    c.yticks([0.0, 0.5, 1.0], side="right")
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#534AB7", width=1.5)
    return c


def ring_partial_arc_sectors():
    # Partial arc + x-sectors — exercises non-cyclic sector walls
    # (no wrap-around walls at the open ends) and the per-sector arc
    # spine path.
    sec_names = ["A", "B", "C"]
    sec_lens  = [0.40, 0.35, 0.25]
    ts_per    = 24
    pts_x, pts_y, pts_sec = [], [], []
    for sname, slen in zip(sec_names, sec_lens):
        for i in range(ts_per):
            t_in = (i + 0.5) / ts_per
            pts_x.append(t_in * slen)
            pts_y.append(_clamp01(0.5 + 0.30 * math.sin(3 * math.pi * t_in)))
            pts_sec.append(sname)
    c = pt.chart(title="partial arc — A/B/C sectors",
                 xlim=(0, 1), ylim=(0, 1),
                 data_width=340, data_height=340)
    c.coordinate(pt.CircularCoordinate(start_deg=90, end_deg=360))
    c.sectors(pt.Sectors(names=tuple(sec_names), lengths=tuple(sec_lens),
                          gap=8), axis="x", column="sec")
    for sname in sec_names:
        xs = [x for x, s in zip(pts_x, pts_sec) if s == sname]
        ys = [y for y, s in zip(pts_y, pts_sec) if s == sname]
        ss = [sname] * len(xs)
        c.line(data={"x": xs, "y": ys, "sec": ss},
               x="x", y="y", color="#D9534F", width=1.2)
    return c


def ring_pile_titled():
    # Layout-level title on a circular overlay: the pile's `.title(...)`
    # renders as one band above the ring canvas ("a ring's title lives
    # on the layout"); per-leaf titles stay suppressed in piles.
    outer = pt.chart(xlim=(0, 1), ylim=(0, 1),
                     data_width=300, data_height=300)
    outer.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
               color="#1D9E75", width=1.5)
    inner = pt.chart(xlim=(0, 1), ylim=(0, 1),
                     data_width=300, data_height=120)
    inner.scatter(data={"x": _SCATTER_T, "y": _SCATTER_V}, x="x", y="y",
                  color="#534AB7", size=2.5, alpha=0.6)
    pile = (outer / inner).coordinate(pt.CircularCoordinate(r_inner=0.35))
    return pile.title("two rings — layout title")


def ring_inner_chords():
    # Bare-chart root with `inner=`: the central disc hosts a chord
    # panel that inherits the host's sector partition. Pins the root
    # wrap lowering — this exact shape used to render the ring but
    # silently drop the disc, while pt.grid([[...]]) wrapping worked.
    import plotlet.extensions.chord_links  # noqa: F401 — registers the artist
    sec = pt.Sectors(names=("A", "B", "C"), lengths=(100.0, 80.0, 60.0),
                     gap=6)
    ring = pt.chart(title="ring + inner chords",
                    xlim=(0, 240), ylim=(0, 6),
                    data_width=320, data_height=320)
    ring.scatter(data={"pos": [20, 55, 90, 30, 60, 20, 45],
                       "val": [2, 4, 5, 3, 5, 2, 4],
                       "sec": ["A", "A", "A", "B", "B", "C", "C"]},
                 x="pos", y="val", color="#534AB7", size=3)
    arcs = pt.chart(xlim=(0, 240), data_width=320, data_height=320)
    arcs.chord_links(
        data={"s1": ["A", "A", "B"], "x1": [30.0, 70.0, 40.0],
              "s2": ["B", "C", "C"], "x2": [40.0, 30.0, 50.0]},
        x1="x1", x2="x2", x1_sector="s1", x2_sector="s2")
    ring.coordinate(pt.CircularCoordinate(r_inner=0.5, inner=arcs))
    ring.sectors(sec, column="sec")
    return ring


# ---------------------------------------------------------------------------
# Sector × CircularCoordinate guard
# ---------------------------------------------------------------------------

def test_inner_disc_renders_from_bare_chart_root():
    """A bare Chart root must render `inner=` content — the chart-root
    path used to drop the disc silently (the panel path never read
    `coord.inner`), while the pt.grid([[...]]) form worked. The root
    wrap lowering routes both through `render_layout`; asserting equal
    chord counts, not byte equality — the forms owe the same *content*,
    not the same bytes."""
    import plotlet.extensions.chord_links  # noqa: F401

    def ring():
        c = pt.chart(xlim=(0, 200), ylim=(0, 6),
                     data_width=300, data_height=300)
        c.scatter(data={"pos": [25, 75, 25, 75], "val": [3, 6, 4, 5],
                        "sec": ["A", "A", "B", "B"]},
                  x="pos", y="val", color="#534AB7")
        return c

    def arcs():
        a = pt.chart(xlim=(0, 200), data_width=300, data_height=300)
        a.chord_links(data={"s1": ["A"], "x1": [50.0],
                            "s2": ["B"], "x2": [50.0]},
                      x1="x1", x2="x2", x1_sector="s1", x2_sector="s2")
        return a

    def n_chords(svg):
        return svg.count('stroke="#1f77b4"')  # chord_links default stroke

    sec = pt.Sectors(names=("A", "B"), lengths=(100.0, 100.0), gap=4)
    bare = ring().coordinate(
        pt.CircularCoordinate(r_inner=0.5, inner=arcs())
    ).sectors(sec, column="sec")
    grid = pt.grid([[ring()]]).coordinate(
        pt.CircularCoordinate(r_inner=0.5, inner=arcs())
    ).sectors(sec, column="sec")
    assert n_chords(bare.to_svg()) == n_chords(grid.to_svg()) == 1


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
    "ring_scatter":                ring_scatter,
    "ring_line":                   ring_line,
    "ring_line_chords":            ring_line_chords,
    "ring_line_band":              ring_line_band,
    "ring_numeric_bar":            ring_numeric_bar,
    "ring_inner_outer":            ring_inner_outer,
    "ring_references":             ring_references,
    "ring_shapes":                 ring_shapes,
    "ring_x_sectors":              ring_x_sectors,
    "ring_partial_arc":            ring_partial_arc,
    "ring_partial_arc_right_side": ring_partial_arc_right_side,
    "ring_partial_arc_sectors":    ring_partial_arc_sectors,
    "ring_pile_titled":            ring_pile_titled,
    "ring_inner_chords":           ring_inner_chords,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_circular_coordinate_baseline(name, fn, baseline_compare):
    baseline_compare("circular_coordinate", name, fn().to_svg())
