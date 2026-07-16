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
import pytest


# ---------------------------------------------------------------------------
# Shared deterministic data
# ---------------------------------------------------------------------------

# No value clamping: the charts below autoscale, so the axis fits whatever
# range the data has (the default 5% expand keeps extremes off the rim) —
# exactly like a cartesian chart. Data is only kept in [0, 1] where a test
# deliberately forces that frame (references / shapes / sectors / arcs).
_RNG = random.Random(11)

_N_LINE = 12
_LINE_TS = [i / _N_LINE for i in range(_N_LINE + 1)]
_LINE_V  = [0.5 + 0.35 * math.sin(2 * math.pi * t) for t in _LINE_TS]
_BAND_LO = [v - 0.08 for v in _LINE_V]
_BAND_HI = [v + 0.08 for v in _LINE_V]

_SCATTER_T = [_RNG.random() for _ in range(60)]
_SCATTER_V = [0.5 + 0.4 * math.sin(2 * math.pi * t) + _RNG.gauss(0, 0.06)
              for t in _SCATTER_T]

_N_BAR = 24
_BAR_T = [(i + 0.5) / _N_BAR for i in range(_N_BAR)]
_BAR_V = [0.3 + 0.5 * abs(math.sin(2 * math.pi * t)) for t in _BAR_T]

# Grouped categorical sample (strip / swarm / boxplot / violin / pointplot):
# each category is a small distribution centered at a walking mean.
_CAT_NAMES = [f"c{i}" for i in range(6)]
_CAT_DATA = {"cat": [], "val": []}
for _ci, _cn in enumerate(_CAT_NAMES):
    _mu = 0.35 + 0.4 * abs(math.sin(0.9 * _ci))
    for _k in range(30):
        _CAT_DATA["cat"].append(_cn)
        _CAT_DATA["val"].append(_mu + _RNG.gauss(0, 0.10))

# A single 1-D distribution (qq / rug / ecdf / freqpoly / density_1d).
_DIST = [0.5 + 0.16 * _RNG.gauss(0, 1) for _ in range(150)]


# ---------------------------------------------------------------------------
# Single-artist rings
# ---------------------------------------------------------------------------

def ring_scatter():
    c = pt.chart(title="scatter — ring")
    c.coordinate(pt.CircularCoordinate())
    c.scatter(data={"x": _SCATTER_T, "y": _SCATTER_V}, x="x", y="y",
              color="#534AB7", size=3, alpha=0.55)
    return c


def ring_line():
    c = pt.chart(title="line — ring")
    c.coordinate(pt.CircularCoordinate())
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#1D9E75", linewidth=1.5)
    return c


def ring_line_chords():
    # `arc=False` — endpoints still warp to the right angle/ring, but
    # connecting segments are literal Cartesian chords (no per-edge
    # subdivision). Same data as `ring_line` so the two baselines are a
    # direct visual pair: same sample points, arc on vs off.
    c = pt.chart(title="line — chords (arc=False)")
    c.coordinate(pt.CircularCoordinate())
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#1D9E75", linewidth=1.5, arc=False)
    return c


def ring_line_band():
    c = pt.chart(title="line + band — ring")
    c.coordinate(pt.CircularCoordinate())
    c.fill_between(data={"x": _LINE_TS, "lo": _BAND_LO, "hi": _BAND_HI},
                   x="x", y1="lo", y2="hi", fill="#1D9E75", alpha=0.25)
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#1D9E75", linewidth=1.5)
    return c


def ring_numeric_bar():
    c = pt.chart(title="numeric_bar — ring")
    c.coordinate(pt.CircularCoordinate())
    c.numeric_bar(data={"x": _BAR_T, "y": _BAR_V}, x="x", y="y",
                  width=0.025, color="#D9534F", alpha=0.85)
    return c


def ring_bar():
    # Core `bar` under Circular — a categorical x-scale wraps around the
    # ring (coxcomb / polar-bar look); each bar rect warps into an annular
    # wedge via project=ctx.warp.
    cats = [f"c{i}" for i in range(_N_BAR)]
    c = pt.chart(title="bar — ring")
    c.coordinate(pt.CircularCoordinate())
    c.bar(data={"cat": cats, "val": _BAR_V}, x="cat", y="val",
          fill="#D9534F", alpha=0.85)
    return c


def ring_errorbar():
    # Core `errorbar` under Circular — radial stems + arc caps warp per
    # sub-segment; markers keep their glyph shape and just re-anchor.
    yerr = [0.05 + 0.02 * abs(math.cos(3 * t)) for t in _BAR_T]
    c = pt.chart(title="errorbar — ring")
    c.coordinate(pt.CircularCoordinate())
    c.errorbar(data={"x": _BAR_T, "y": _BAR_V, "e": yerr},
               x="x", y="y", yerr="e", color="#534AB7", size=3)
    return c


# --- statistical / distribution artists on a categorical or numeric ring ---

def ring_strip():
    c = pt.chart(title="strip — ring")
    c.coordinate(pt.CircularCoordinate())
    c.strip(data=_CAT_DATA, x="cat", y="val", fill="cat", palette="Set2")
    return c


def ring_swarm():
    c = pt.chart(title="swarm — ring")
    c.coordinate(pt.CircularCoordinate())
    c.swarm(data=_CAT_DATA, x="cat", y="val", fill="cat", palette="Set2")
    return c


def ring_boxplot():
    # Box → annular wedge, whiskers radial, median arc, fliers repositioned.
    c = pt.chart(title="boxplot — ring")
    c.coordinate(pt.CircularCoordinate())
    c.boxplot(data=_CAT_DATA, x="cat", y="val", fill="cat", palette="Set2")
    return c


def ring_violin():
    # KDE lobe warps into a mirrored annular blob (polygon project path).
    c = pt.chart(title="violin — ring")
    c.coordinate(pt.CircularCoordinate())
    c.violin(data=_CAT_DATA, x="cat", y="val", fill="cat", palette="Set2")
    return c


def ring_pointplot():
    c = pt.chart(title="pointplot — ring")
    c.coordinate(pt.CircularCoordinate())
    c.pointplot(data=_CAT_DATA, x="cat", y="val", color="#1D9E75")
    return c


def ring_qq():
    # Theoretical quantiles run negative→positive on x, sample values on y.
    c = pt.chart(title="qq — ring")
    c.coordinate(pt.CircularCoordinate())
    c.qq(data={"s": _DIST}, sample="s", dist="normal",
         color="#534AB7", size=2.5)
    return c


def ring_rug():
    c = pt.chart(title="rug — ring")
    c.coordinate(pt.CircularCoordinate())
    c.rug(data={"x": _DIST}, x="x", color="#444444")
    return c


def ring_ecdf():
    c = pt.chart(title="ecdf — ring")
    c.coordinate(pt.CircularCoordinate())
    c.ecdf(data={"x": _DIST}, x="x", color="#534AB7")
    return c


def ring_freqpoly():
    c = pt.chart(title="freqpoly — ring")
    c.coordinate(pt.CircularCoordinate())
    c.freqpoly(data={"x": _DIST}, x="x", bins=20, color="#1D9E75")
    return c


def ring_density_1d():
    # Filled density closes to the baseline ring via a warped polygon.
    c = pt.chart(title="density_1d — ring")
    c.coordinate(pt.CircularCoordinate())
    c.density_1d(data={"x": _DIST}, x="x", fill=True, color="#534AB7")
    return c


def ring_regression():
    xs = [i / 40 for i in range(41)]
    ys = [0.4 + 0.4 * x + 0.05 * math.sin(9 * x) for x in xs]
    # The CI band extends past the fit line — autoscale for breathing room.
    c = pt.chart(title="regression — ring")
    c.coordinate(pt.CircularCoordinate())
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y", size=2, alpha=0.5)
    c.regression(data={"x": xs, "y": ys}, x="x", y="y", color="#D9534F")
    return c


def _tree_data(seed=0):
    # 16 leaves in 3 latent groups so the tree has real structure.
    rng = random.Random(seed)
    profiles = [[2.0, 1.5, 0.0, -1.0, 0.5, 1.0],
                [-1.0, 0.0, 2.0, 0.5, -1.5, 0.0],
                [0.5, -1.5, -1.0, 2.0, 1.5, -0.5]]
    labels, matrix = [], []
    for i in range(16):
        labels.append(f"L{i:02d}")
        matrix.append([p + rng.gauss(0, 0.6) for p in profiles[i % 3]])
    return labels, matrix


def ring_dendrogram():
    # Radial tree: leaf axis wraps the ring (t), merge height is radial (r).
    # `orientation="bottom"` roots the tree at the inner edge so leaves fan
    # out. Each U-shape warps — the connector bar becomes a constant-radius
    # arc, the legs become radial spokes.
    labels, matrix = _tree_data()
    c = pt.chart(title="dendrogram — ring", xlim=(0, 1))
    c.dendrogram(data=matrix, labels=labels, method="ward",
                 orientation="bottom", color="#3B3B4F")
    c.coordinate(pt.CircularCoordinate(r_inner=0.10, wrap_gap_deg=4))
    return c


def ring_dendrogram_heatmap():
    # Radial tree (inner band) + heatmap ring (outer band) sharing one leaf
    # axis: column i sits at leaf i's angle because both rings carry the
    # same category order. The annotated-heatmap shape, wrapped onto a ring.
    # Read the leaf order from a local tree (never handed to a chart, so the
    # journal stays JSON-serializable); the tree ring re-clusters the same
    # data/method and lands on the same order.
    from plotlet.cluster import layout_tree
    labels, matrix = _tree_data()
    _, _, leaf_order = layout_tree(pt.linkage(matrix, labels=labels,
                                              method="ward"))
    row_by_label = dict(zip(labels, matrix))
    data = {"leaf": leaf_order}
    for j in range(len(matrix[0])):
        data[f"f{j}"] = [row_by_label[l][j] for l in leaf_order]

    tree_ring = pt.chart(xlim=(0, 1))
    tree_ring.dendrogram(data=matrix, labels=labels, method="ward",
                         orientation="bottom", color="#3B3B4F")
    hm_ring = pt.chart(xlim=(0, 1), ylim=(0, 1))
    hm_ring.heatmap(data=data, x="leaf",
                    values=[f"f{j}" for j in range(len(matrix[0]))],
                    cmap="RdBu_r", center=0)
    pile = (hm_ring / tree_ring).coordinate(
        pt.CircularCoordinate(r_inner=0.08, wrap_gap_deg=4))
    pile.heights([1.0, 2.2])
    return pile.title("tree + heatmap — ring")


def ring_dendrogram_palette():
    # `palette=` on a ring: each group's branches take its color while the
    # between-cluster trunk (parent=True) stays neutral — the same demo as
    # the Cartesian `dendrogram_palette`, warped. A sector per group carves
    # the blocks into separate wedges. This confirms per-group color and
    # the neutral parent survive the warp (color is assigned at record
    # time; the warp only bends geometry).
    labels, matrix = _tree_data()
    groups = ["ABC"[i % 3] for i in range(len(labels))]
    palette = {"A": "#1D9E75", "B": "#E6842A", "C": "#534AB7"}
    by_group = {}
    for lbl, g in zip(labels, groups):
        by_group.setdefault(g, []).append(lbl)
    c = pt.chart(title="dendrogram palette — ring", xlim=(0, 1))
    c.sectors(by_group, axis="x", divider=False, label=False)
    c.dendrogram(data=matrix, labels=labels, clusters=groups, method="ward",
                 palette=palette, parent=True, orientation="bottom")
    c.coordinate(pt.CircularCoordinate(r_inner=0.10, wrap_gap_deg=4))
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
            pts_y.append(0.5 + 0.35 * math.sin(4 * math.pi * t_in))
            pts_sec.append(sname)

    c = pt.chart(title="ring — x-sectors",
                 xlim=(0, 1), ylim=(0, 1))
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
               x="x", y="y", color="#1D9E75", linewidth=1.2)
    # Scatter has no connections — single call is fine.
    c.scatter(data={"x": pts_x, "y": pts_y, "sec": pts_sec},
              x="x", y="y", color="#534AB7", size=2.5, alpha=0.7)
    return c


def ring_cat_sectors():
    # Categorical x-sectors on a ring: bars group into named wedges and
    # the y rings break at the gaps (bounded per-sector arcs, matching
    # the walls) instead of bleeding through the whitespace.
    cats = list("abcdefgh")
    vals = [3, 5, 2, 6, 4, 7, 3, 5]
    c = pt.chart(title="categorical sectors — ring")
    c.coordinate(pt.CircularCoordinate())
    c.sectors({"G1": ["a", "b", "c"], "G2": ["d", "e"], "G3": ["f", "g", "h"]},
              axis="x")
    c.bar(data={"cat": cats, "val": vals}, x="cat", y="val",
          fill="cat", palette="Set2")
    return c


def ring_inner_outer():
    # Custom inner radius — exercises the r_inner=0.55 path so the
    # geometry helper isn't accidentally collapsed to defaults.
    c = pt.chart(title="ring — r_inner=0.55", xlim=(0, 1), ylim=(0, 1))
    c.coordinate(pt.CircularCoordinate(r_inner=0.55))
    c.xticks([0.0, 0.5])
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#534AB7", linewidth=1.5)
    return c


def ring_references():
    # Reference primitives under Circular: axhline → concentric ring,
    # axvline → radial spoke, hlines/vlines → bounded arc / spoke
    # segments, axhspan → ring band, axvspan → angular wedge.
    c = pt.chart(title="references — ring", xlim=(0, 1), ylim=(0, 1))
    c.coordinate(pt.CircularCoordinate())
    c.xticks([0.0, 0.25, 0.5, 0.75])
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
    c = pt.chart(title="shapes — ring", xlim=(0, 1), ylim=(0, 1))
    c.coordinate(pt.CircularCoordinate())
    c.xticks([0.0, 0.25, 0.5, 0.75])
    c.rect(0.10, 0.20, 0.25, 0.40, fill="#A0C4E2", alpha=0.5)
    poly_x = [0.55, 0.75, 0.85, 0.70, 0.55]
    poly_y = [0.30, 0.30, 0.55, 0.70, 0.55]
    c.polygon(poly_x, poly_y, fill="#F2C57C", alpha=0.6)
    line_x = [0.05, 0.20, 0.40, 0.60, 0.80, 0.95]
    line_y = [0.90, 0.70, 0.85, 0.65, 0.80, 0.60]
    c.polyline(line_x, line_y, color="#534AB7", linewidth=1.5)
    return c


def ring_text_annotate():
    # `text` / `annotate` under Circular: only the anchor points warp —
    # glyphs stay upright, the annotate arrow is a straight screen-space
    # connector, and dx/dy stay screen-space nudges.
    pts_t = [0.05, 0.20, 0.40, 0.60, 0.80]
    pts_v = [0.75, 0.45, 0.85, 0.35, 0.65]
    names = ["a", "b", "c", "d", "e"]
    c = pt.chart(title="text + annotate — ring", xlim=(0, 1), ylim=(0, 1))
    c.coordinate(pt.CircularCoordinate())
    c.scatter(data={"x": pts_t, "y": pts_v}, x="x", y="y",
              color="#534AB7", size=3)
    c.text(data={"x": pts_t, "y": pts_v, "name": names},
           x="x", y="y", label="name", fontsize=8, ha="center", dy=-6)
    c.annotate("peak", xy=(0.40, 0.85), xytext=(0.55, 0.15),
               fontsize=8, ha="center", bbox=True)
    return c


def ring_heatmap():
    # Continuous-x heatmap under Circular → each cell rect warps into an
    # annular sector. Numeric `x` column wraps around the ring; the track
    # rows stack as concentric bands. imshow can't do this (no warp).
    tracks = ["a", "b", "c"]
    df = {"pos": [float(i) for i in range(24)]}
    for row, name in enumerate(tracks):
        df[name] = [math.sin(0.4 * i + row) for i in range(24)]
    c = pt.chart(title="heatmap — ring")
    c.coordinate(pt.CircularCoordinate(r_inner=0.35))
    c.heatmap(data=df, x="pos", values=tracks, cmap="viridis")
    return c


def ring_heatmap_sectors():
    # Two concentric sectored rings sharing one angular x — a scatter ring
    # outside, a continuous-x heatmap ring inside — with real gaps between
    # sector groups (the wrap gap + two inter-sector gaps). Each ring keeps
    # its OWN radial y, so heatmap tracks and scatter values don't collide
    # on one axis. The `grp` column tags every column/point's sector: the
    # heatmap groups its cell edges per sector (gaps fall between groups)
    # and the scatter routes through the same `column="grp"` tag.
    # Layout-level `.coordinate(...)` + `.sectors(...)` fan out to both.
    sec_names = ["A", "B", "C"]
    sec_lens = [0.45, 0.30, 0.25]
    grp, xh, t1, t2 = [], [], [], []
    sx, sy, sg = [], [], []
    for name, slen in zip(sec_names, sec_lens):
        for i in range(8):
            p = (i + 0.5) / 8 * slen
            grp.append(name); xh.append(p)
            t1.append(math.sin(10 * p)); t2.append(math.cos(8 * p))
        for i in range(12):
            p = (i + 0.5) / 12 * slen
            sx.append(p); sg.append(name)
            sy.append(0.5 + 0.4 * math.sin(6 * math.pi * p / slen))

    sc = pt.chart(xlim=(0, 1), ylim=(0, 1))
    sc.scatter(data={"x": sx, "y": sy, "grp": sg}, x="x", y="y",
               color="#534AB7", size=2.5, alpha=0.8)
    hm = pt.chart(xlim=(0, 1), ylim=(0, 1))
    hm.heatmap(data={"grp": grp, "x": xh, "t1": t1, "t2": t2},
               x="x", sector="grp", values=["t1", "t2"], cmap="viridis")

    pile = (sc / hm).coordinate(
        pt.CircularCoordinate(r_inner=0.30, wrap_gap_deg=8))
    pile.heights([1, 2])   # thin scatter ring outside, thick heatmap inside
    pile.sectors(pt.Sectors(names=tuple(sec_names), lengths=tuple(sec_lens),
                            gap=8), axis="x", column="grp")
    return pile.title("ring — sectored heatmap + scatter")


def ring_partial_arc():
    # Partial arc — `start_deg=90, end_deg=360` sweeps 270° clockwise
    # from 3 o'clock around through 6 / 9 / 12. Exercises the open-arc
    # spine path (no sectors) and y-tick placement along start_rad
    # (3 o'clock, the t=0 open edge).
    c = pt.chart(title="partial arc — 90°→360°", xlim=(0, 1), ylim=(0, 1))
    c.coordinate(pt.CircularCoordinate(start_deg=90, end_deg=360))
    c.xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    c.yticks([0.0, 0.5, 1.0])
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#1D9E75", linewidth=1.5)
    return c


def ring_partial_arc_right_side():
    # Same partial arc with `yticks(side="right")` — labels move to
    # `end_rad` (the t=1 open edge) instead of `start_rad`.
    c = pt.chart(title="partial arc — side=right", xlim=(0, 1), ylim=(0, 1))
    c.coordinate(pt.CircularCoordinate(start_deg=90, end_deg=360))
    c.xticks([0.0, 0.5, 1.0])
    c.yticks([0.0, 0.5, 1.0], side="right")
    c.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
           color="#534AB7", linewidth=1.5)
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
            pts_y.append(0.5 + 0.30 * math.sin(3 * math.pi * t_in))
            pts_sec.append(sname)
    c = pt.chart(title="partial arc — A/B/C sectors",
                 xlim=(0, 1), ylim=(0, 1))
    c.coordinate(pt.CircularCoordinate(start_deg=90, end_deg=360))
    c.sectors(pt.Sectors(names=tuple(sec_names), lengths=tuple(sec_lens),
                          gap=8), axis="x", column="sec")
    for sname in sec_names:
        xs = [x for x, s in zip(pts_x, pts_sec) if s == sname]
        ys = [y for y, s in zip(pts_y, pts_sec) if s == sname]
        ss = [sname] * len(xs)
        c.line(data={"x": xs, "y": ys, "sec": ss},
               x="x", y="y", color="#D9534F", linewidth=1.2)
    return c


def ring_pile_titled():
    # Layout-level title on a circular overlay: the pile's `.title(...)`
    # renders as one band above the ring canvas ("a ring's title lives
    # on the layout"); per-leaf titles stay suppressed in piles.
    outer = pt.chart(xlim=(0, 1), ylim=(0, 1))
    outer.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
               color="#1D9E75", linewidth=1.5)
    inner = pt.chart(xlim=(0, 1), ylim=(0, 1))
    inner.scatter(data={"x": _SCATTER_T, "y": _SCATTER_V}, x="x", y="y",
                  color="#534AB7", size=2.5, alpha=0.6)
    pile = (outer / inner).coordinate(pt.CircularCoordinate(r_inner=0.35))
    pile.heights([2.5, 1])   # thin scatter ring nests inside the line ring
    return pile.title("two rings — layout title")


def ring_inner_step_ticks():
    # Inner rings default to tick suppression (outermost-only labels),
    # but a content-deciding xticks call — step= here, likewise ticks=/
    # count=/format= — opts the ring back in. Pins TICK_CONTENT_KW
    # against `resolve_layout`'s style-only classification, which would
    # otherwise wipe the inner ring's requested ticks.
    outer = pt.chart(xlim=(0, 1), ylim=(0, 1))
    outer.line(data={"x": _LINE_TS, "y": _LINE_V}, x="x", y="y",
               color="#1D9E75", linewidth=1.5)
    inner = pt.chart(xlim=(0, 1), ylim=(0, 1))
    inner.scatter(data={"x": _SCATTER_T, "y": _SCATTER_V}, x="x", y="y",
                  color="#534AB7", size=2.5, alpha=0.6)
    inner.xticks(step=0.25)
    return (outer / inner).coordinate(pt.CircularCoordinate())


def ring_inner_chords():
    # Bare-chart root with `inner=`: the central disc hosts a chord
    # panel that inherits the host's sector partition. Pins the root
    # wrap lowering — this exact shape used to render the ring but
    # silently drop the disc, while pt.grid([[...]]) wrapping worked.
    sec = pt.Sectors(names=("A", "B", "C"), lengths=(100.0, 80.0, 60.0),
                     gap=6)
    ring = pt.chart(title="ring + inner chords",
                    xlim=(0, 240), ylim=(0, 6))
    ring.scatter(data={"pos": [20, 55, 90, 30, 60, 20, 45],
                       "val": [2, 4, 5, 3, 5, 2, 4],
                       "sec": ["A", "A", "A", "B", "B", "C", "C"]},
                 x="pos", y="val", color="#534AB7", size=3)
    arcs = pt.chart(xlim=(0, 240))
    arcs.chord_links(
        data={"s1": ["A", "A", "B"], "x1": [30.0, 70.0, 40.0],
              "s2": ["B", "C", "C"], "x2": [40.0, 30.0, 50.0]},
        x1="x1", x2="x2", x1_sector="s1", x2_sector="s2")
    ring.coordinate(pt.CircularCoordinate(r_inner=0.5, inner=arcs))
    ring.sectors(sec, column="sec")
    return ring


def ring_chord_ribbon():
    # Matrix-chord ribbons in the inner disc — three sectors, three
    # ribbons of varying width. Pins the chord_ribbon circular draw path
    # (cubic edges toward center + boundary-arc caps) and the sector
    # remap of both endpoints.
    sectors = pt.Sectors(names=["A", "B", "C"], lengths=[30, 25, 20], gap=4)
    XL = (0, sectors.total())
    df = {
        "src":  ["A", "A", "B"],
        "dst":  ["B", "C", "C"],
        "x1a":  [0,  18,  0],
        "x1b":  [10, 28, 15],
        "x2a":  [0,  0,  0],
        "x2b":  [10, 8, 12],
    }
    arcs = pt.chart(df, xlim=XL, data_width=400, data_height=400)
    arcs.sectors(sectors, column="src", label=False)
    arcs.chord_ribbon(x1_start="x1a", x1_end="x1b",
                      x2_start="x2a", x2_end="x2b",
                      x1_sector="src", x2_sector="dst",
                      color="src", alpha=0.6)

    ring = pt.chart(xlim=XL, ylim=(0, 1), data_width=400, data_height=400)
    ring.sectors(sectors, column="x")
    return pt.grid([[ring]]).coordinate(
        pt.CircularCoordinate(r_inner=0.85, inner=arcs)
    )


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

    def ring():
        c = pt.chart(xlim=(0, 200), ylim=(0, 6))
        c.scatter(data={"pos": [25, 75, 25, 75], "val": [3, 6, 4, 5],
                        "sec": ["A", "A", "B", "B"]},
                  x="pos", y="val", color="#534AB7")
        return c

    def arcs():
        a = pt.chart(xlim=(0, 200))
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
    c = pt.chart(xlim=(0, 1), ylim=(0, 1))
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
    "ring_bar":                    ring_bar,
    "ring_errorbar":               ring_errorbar,
    "ring_strip":                  ring_strip,
    "ring_swarm":                  ring_swarm,
    "ring_boxplot":                ring_boxplot,
    "ring_violin":                 ring_violin,
    "ring_pointplot":              ring_pointplot,
    "ring_qq":                     ring_qq,
    "ring_rug":                    ring_rug,
    "ring_ecdf":                   ring_ecdf,
    "ring_freqpoly":               ring_freqpoly,
    "ring_density_1d":             ring_density_1d,
    "ring_regression":             ring_regression,
    "ring_dendrogram":             ring_dendrogram,
    "ring_dendrogram_heatmap":     ring_dendrogram_heatmap,
    "ring_dendrogram_palette":     ring_dendrogram_palette,
    "ring_cat_sectors":            ring_cat_sectors,
    "ring_inner_outer":            ring_inner_outer,
    "ring_references":             ring_references,
    "ring_shapes":                 ring_shapes,
    "ring_text_annotate":          ring_text_annotate,
    "ring_heatmap":                ring_heatmap,
    "ring_heatmap_sectors":        ring_heatmap_sectors,
    "ring_x_sectors":              ring_x_sectors,
    "ring_partial_arc":            ring_partial_arc,
    "ring_partial_arc_right_side": ring_partial_arc_right_side,
    "ring_partial_arc_sectors":    ring_partial_arc_sectors,
    "ring_pile_titled":            ring_pile_titled,
    "ring_inner_step_ticks":       ring_inner_step_ticks,
    "ring_inner_chords":           ring_inner_chords,
    "ring_chord_ribbon":           ring_chord_ribbon,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_circular_coordinate_baseline(name, fn, baseline_compare):
    baseline_compare("circular_coordinate", name, fn().to_svg())
