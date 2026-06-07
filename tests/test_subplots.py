#!/usr/bin/env python3
"""Baseline SVG regression tests for the subplot composition API.

    python tests/test_subplots.py            # check vs. baselines, exit 1 on mismatch
    python tests/test_subplots.py --update   # regenerate baselines (review diff!)
    python tests/test_subplots.py --gallery  # write baseline_images/subplots/index.html

Covers: `|`, `/`, `pt.grid`, single-parent invariant, show-on-child raise,
default gap, auto-zero-gap when adjacent leaves are in the same
share-equivalence class, scale-sharing via parent-level `.share_x()` /
`.share_y()` (with `True`/`"all"`/`"col"`/`"row"`),
range union across share-class members, inner-axis collapse on joined
share-pairs, body-first leaf size-hint honoring (`pt.chart(data_width=...)`
acts as a relative width when no explicit ratios are given), and
`.fit(canvas_width=…, canvas_height=…)` for layout-aware scaling.
"""
from __future__ import annotations

import math
import sys

import plotlet as pt



def _xs():
    return [i * 0.1 for i in range(64)]


# Composition is component-first (sum-sizes), so each test below picks
# per-leaf data dimensions that — combined with the default margin — add
# up to a sensible overall figure so the gallery isn't dominated by one
# giant canvas. The exact totals depend on measure-driven margin growth
# (long labels can widen the left margin), so dimensions are illustrative
# rather than promised.

def _sin(data_width=220, data_height=320):
    xs = _xs()
    c = pt.chart(title="sin", data_width=data_width, data_height=data_height)
    c.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y")
    return c


def _cos(data_width=220, data_height=320):
    xs = _xs()
    c = pt.chart(title="cos", data_width=data_width, data_height=data_height)
    c.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y")
    return c


def _bar(label="bar", data_width=220, data_height=320):
    c = pt.chart({"x": ["a", "b", "c"], "y": [3, 1, 2]},
                 title=label, data_width=data_width, data_height=data_height)
    c.bar(x="x", y="y")
    return c


def _hist(data_width=220, data_height=320):
    c = pt.chart(title="hist", data_width=data_width, data_height=data_height)
    c.hist(data={"x": [0.1, 0.4, 0.5, 0.55, 0.7, 0.8, 0.9, 1.1, 1.3]}, x="x", bins=6)
    return c


def row_two():
    # 2 panels h, default gap 20 between them.
    return _sin() | _cos()


def col_two():
    # 2 panels v, default gap 20 between them.
    return _sin(data_width=520, data_height=120) / _cos(data_width=520, data_height=120)


def row_three_flatten():
    # `a | b | c` — left-fold flatten into a single 3-cell row, not a
    # 25/25/50 nested split.
    return _sin(data_width=120) | _cos(data_width=120) | _bar(data_width=120)


def two_by_two():
    # 4 panels in 2x2 (no shares).
    a = _sin(data_width=220, data_height=120)
    b = _cos(data_width=220, data_height=120)
    c = _bar(data_width=220, data_height=120)
    d = _hist(data_width=220, data_height=120)
    return (a | b) / (c | d)


def grid_with_spacers():
    # 3-col 2-row irregular grid with None corners.
    top  = pt.chart({"x":["a","b","c"], "y":[3,1,2]}, title="top",   data_width=120, data_height=24);  top.bar(x="x", y="y")
    left = pt.chart(title="left",  data_width=120, data_height=220); left.line(data={"x": [1,2,3], "y": [3,1,2]}, x="x", y="y")
    main = pt.chart(title="main",  data_width=120, data_height=220); main.line(data={"x": [1,2,3], "y": [1,4,9]}, x="x", y="y")
    right= pt.chart(title="right", data_width=120, data_height=220); right.line(data={"x": [1,2,3], "y": [2,2,1]}, x="x", y="y")
    return pt.grid([
        [None, top,  None ],
        [left, main, right],
    ])


def measure_driven_alignment():
    # 2x2 body-first grid demonstrating measure-driven margin + per-column
    # coordination. Cell `c` has a categorical y with long group names
    # ("measurement_alpha", …) plus an explicit ylabel — its content-
    # required left margin exceeds the 58 px spec, so left grows. The
    # coordination pre-pass then propagates the same widened left to
    # cell `a` (column 0) so the data regions stay vertically aligned
    # across rows. Cells in column 1 (`b`, `d`) keep their default
    # narrower left margin since neither has a long label requirement.
    a = pt.chart(title="a", data_width=180, data_height=140); a.line(data={"x": [1,2,3], "y": [1,2,3]}, x="x", y="y")
    b = pt.chart(title="b", data_width=180, data_height=140); b.line(data={"x": [1,2,3], "y": [3,2,1]}, x="x", y="y")
    c = pt.chart(data_width=180, data_height=140, ylabel="categories")
    c.scatter(data={"x": [1,2,3,4,5],
                    "y": ["measurement_alpha", "measurement_beta", "measurement_gamma",
                          "measurement_delta", "measurement_epsilon"]},
              x="x", y="y")
    d = pt.chart(data_width=180, data_height=140); d.line(data={"x": [1,2,3], "y": [1,2,3]}, x="x", y="y")
    return pt.grid([[a, b], [c, d]])


def body_first_unequal_columns():
    # Body-first per-cell data widths in 1:2:2 proportion (one narrow
    # column, two equal wider ones). Each leaf renders its data region at
    # exactly the requested pixel count — no ratio override needed; the
    # composition just sums them. With 0.2.0 there's no widths=/heights=
    # parameter on pt.grid: per-leaf data_width IS the way to express
    # "make this column twice as wide as that one."
    a = pt.chart(title="a", data_width=80,  data_height=300); a.line(data={"x": [1,2,3], "y": [1,4,9]}, x="x", y="y")
    b = pt.chart(title="b", data_width=160, data_height=300); b.line(data={"x": [1,2,3], "y": [3,1,2]}, x="x", y="y")
    c = pt.chart(title="c", data_width=160, data_height=300); c.line(data={"x": [1,2,3], "y": [5,2,4]}, x="x", y="y")
    return pt.grid([[a, b, c]])


def share_y_collapses_gap():
    # share_y → joined, gap 0.
    hm   = pt.chart(title="hm",   data_width=220); hm.line(data={"x": [1,2,3], "y": [1,4,9]}, x="x", y="y")
    tree = pt.chart(title="tree", data_width=220); tree.line(data={"x": [1,2,3], "y": [3,1,2]}, x="x", y="y")
    return (tree | hm).share_y()


def share_x_collapses_gap_vertical():
    # share_x → joined, gap 0.
    main = pt.chart(title="main", data_height=120); main.line(data={"x": [1, 2, 3], "y": [1, 4, 9]}, x="x", y="y")
    top  = pt.chart(title="top",  data_height=120); top.line(data={"x": [1, 2, 3], "y": [3, 1, 2]}, x="x", y="y")
    return (top / main).share_x()


def share_x_three_panels():
    # Three vertically-stacked panels all share x via parent-level .share_x().
    # Equivalent to matplotlib's subplots(3, 1, sharex=True).
    main = pt.chart(title="main", data_height=60); main.line(data={"x": [0, 5, 10], "y": [0, 1, 0]}, x="x", y="y")
    mid  = pt.chart(title="mid",  data_height=60); mid.line(data={"x": [0, 5, 10], "y": [10, 0, 10]}, x="x", y="y")
    top  = pt.chart(title="top",  data_height=60); top.line(data={"x": [0, 5, 10], "y": [5, 5, 5]}, x="x", y="y")
    return (top / mid / main).share_x()


def share_y_chain():
    # Three side-by-side panels all share y via parent-level .share_y().
    a = pt.chart(title="a", data_width=130); a.line(data={"x": [1,2,3], "y": [0, 100, 0]}, x="x", y="y")
    b = pt.chart(title="b", data_width=130); b.line(data={"x": [1,2,3], "y": [10, 50, 90]}, x="x", y="y")
    c = pt.chart(title="c", data_width=130); c.line(data={"x": [1,2,3], "y": [20, 40, 60]}, x="x", y="y")
    return (a | b | c).share_y()


def width_hint_narrow_side():
    # Narrow side panel sharing y with main. Stand-in for
    # `hm | pt.colorbar(hm)` — body-first per-leaf widths express the
    # main:side ratio directly.
    main = pt.chart(title="main", data_width=440); main.line(data={"x": [1,2,3], "y": [1,4,9]}, x="x", y="y")
    side = pt.chart(title="side", data_width=24)
    side.line(data={"x": [1, 1, 1], "y": [1, 4, 9]}, x="x", y="y")
    return (main | side).share_y()


def height_hint_short_top():
    # Short top track over a main panel.
    top  = pt.chart({"x":["a","b","c"], "y":[1,2,3]}, title="top",  data_height=24)
    top.bar(x="x", y="y")
    main = pt.chart({"x":["a","b","c"], "y":[3,1,2]}, title="main", data_height=240); main.bar(x="x", y="y")
    return (top / main).share_x()


def custom_gap_method():
    # `(a | b).gap(N)` overrides the default 20 px inter-panel gap.
    return (_sin(data_width=220) | _cos(data_width=220)).gap(4)


def custom_gap_grid_kwarg():
    # `pt.grid(..., gap=N)` — same override, declared at construction.
    a = _sin(data_width=120)
    b = _cos(data_width=120)
    c = _bar(data_width=120)
    return pt.grid([[a, b, c]], gap=8)


def complex_grid_shares():
    # Annotated-heatmap shape via grid with column/row sharing:
    # `share_x="col"` → top↔main share x (column 1); `share_y="row"` →
    # tree↔main share y (row 1).
    main = pt.chart(title="main", data_width=400, data_height=240)
    main.line(data={"x": [1,2,3,4,5], "y": [2,4,1,5,3]}, x="x", y="y")
    top  = pt.chart(title="top",  data_width=400, data_height=24)
    top.line(data={"x": [1,2,3,4,5], "y": [1,1,3,1,1]}, x="x", y="y")
    tree = pt.chart(title="tree", data_width=60,  data_height=240)
    tree.line(data={"x": [0,1,2], "y": [2,3,4]}, x="x", y="y")
    return pt.grid([
        [None, top ],
        [tree, main],
    ]).share_x("col").share_y("row")


def fit_to_canvas():
    # `.fit(canvas_width=, canvas_height=)` rescales data regions so the
    # rendered SVG fits the target canvas, layout-aware: tick labels,
    # titles, spines, margins stay at their absolute sizes. Aspect ratio
    # is preserved (min of the two ratios wins). Same composition as
    # `two_by_two` above; here we ask it to fit into 480×320.
    a = _sin(data_width=220, data_height=120)
    b = _cos(data_width=220, data_height=120)
    c = _bar(data_width=220, data_height=120)
    d = _hist(data_width=220, data_height=120)
    return ((a | b) / (c | d)).fit(canvas_width=480, canvas_height=320)


def fit_width_only():
    # Width-only fit — aspect preserved via the single ratio. The natural
    # row would be ~600 wide; .fit(canvas_width=400) shrinks all leaves
    # proportionally so it fits, without touching font sizes.
    return (_sin(data_width=220) | _cos(data_width=220)).fit(canvas_width=400)


def share_x_col_v_of_h():
    # v-of-h composition with cross-row column-wise x-sharing — the
    # canonical "stacked tracks across a genome" shape. Each row uses
    # share_y().touch() to collapse inner spines within the row; the
    # outer `share_x("col")` aligns the same column across rows (column
    # widths differ on purpose to match the genome-tracks use case).
    def row(name):
        a = pt.chart(title=f"{name}-c1", data_width=160, data_height=70)
        b = pt.chart(title=f"{name}-c2", data_width=110, data_height=70)
        c = pt.chart(title=f"{name}-c3", data_width= 70, data_height=70)
        a.line(data={"x": [0, 1, 2, 3, 4], "y": [0, 1, 2, 1, 0]}, x="x", y="y")
        b.line(data={"x": [0, 1, 2, 3], "y": [2, 1, 3, 1]}, x="x", y="y")
        c.line(data={"x": [0, 1, 2], "y": [1, 2, 1]}, x="x", y="y")
        return (a | b | c).share_y().touch()
    return (row("r1") / row("r2") / row("r3")).share_x("col")


PLOTS = {
    "row_two":             row_two,
    "col_two":             col_two,
    "row_three_flatten":   row_three_flatten,
    "two_by_two":          two_by_two,
    "grid_with_spacers":   grid_with_spacers,
    "body_first_columns":  body_first_unequal_columns,
    "measure_alignment":   measure_driven_alignment,
    "share_y_no_gap":      share_y_collapses_gap,
    "share_x_no_gap":      share_x_collapses_gap_vertical,
    "share_x_three":       share_x_three_panels,
    "share_y_chain":       share_y_chain,
    "width_hint":          width_hint_narrow_side,
    "height_hint":         height_hint_short_top,
    "complex_grid":        complex_grid_shares,
    "gap_method":          custom_gap_method,
    "gap_grid_kwarg":      custom_gap_grid_kwarg,
    "fit_to_canvas":       fit_to_canvas,
    "fit_width_only":      fit_width_only,
    "share_x_col_v_of_h":  share_x_col_v_of_h,
}


def _run_invariants():
    """Cheap unit checks that don't fit the SVG-baseline shape."""
    failures = []

    # 1. show-on-child raises with a useful message
    a = pt.chart(); a.line(data={"x": [1,2,3], "y": [1,2,3]}, x="x", y="y")
    b = pt.chart(); b.line(data={"x": [1,2,3], "y": [3,2,1]}, x="x", y="y")
    parent = a | b
    try:
        a.to_svg()
        failures.append("expected RuntimeError on parented child .to_svg()")
    except RuntimeError as e:
        if "parent" not in str(e).lower():
            failures.append(f"unexpected message: {e}")

    # 2. single-parent invariant
    c = pt.chart(); c.line(data={"x": [1,2,3], "y": [1,2,3]}, x="x", y="y")
    d = pt.chart(); d.line(data={"x": [1,2,3], "y": [3,2,1]}, x="x", y="y")
    e = pt.chart(); e.line(data={"x": [1,2,3], "y": [2,2,2]}, x="x", y="y")
    cd = c | d
    try:
        c | e
        failures.append("expected ValueError when composing a parented chart")
    except ValueError:
        pass

    # 3. flattening: a | b | c yields one parent with three children
    p = pt.chart(); p.line(data={"x": [1], "y": [1]}, x="x", y="y")
    q = pt.chart(); q.line(data={"x": [1], "y": [1]}, x="x", y="y")
    r = pt.chart(); r.line(data={"x": [1], "y": [1]}, x="x", y="y")
    row = p | q | r
    if len(row._children) != 3:
        failures.append(f"flatten: expected 3 children, got {len(row._children)}")

    # 4. cross-direction nests, doesn't flatten
    s = pt.chart(); s.line(data={"x": [1], "y": [1]}, x="x", y="y")
    t = pt.chart(); t.line(data={"x": [1], "y": [1]}, x="x", y="y")
    u = pt.chart(); u.line(data={"x": [1], "y": [1]}, x="x", y="y")
    pair = s | t
    col = pair / u
    if col._layout_kind != "v" or len(col._children) != 2:
        failures.append(
            f"nest: expected vertical parent of 2; got {col._layout_kind} with "
            f"{len(col._children)} children"
        )

    # 5. pt.grid validates row shape
    a1 = pt.chart(); a1.line(data={"x": [1], "y": [1]}, x="x", y="y")
    try:
        pt.grid([[a1, None], [a1]])
        failures.append("expected ValueError on ragged grid")
    except ValueError:
        pass

    # 6. share cycle detection
    f1 = pt.chart(); f1.line(data={"x": [1,2], "y": [1,2]}, x="x", y="y")
    f2 = pt.chart(); f2.line(data={"x": [1,2], "y": [2,1]}, x="x", y="y")
    f1._share_y = f2
    f2._share_y = f1   # cycle
    try:
        (f1 | f2).to_svg()
        failures.append("expected ValueError on share_y cycle")
    except ValueError as ex:
        if "cycle" not in str(ex).lower():
            failures.append(f"expected cycle message; got: {ex}")

    # 7. parent-level share() doesn't exist on a leaf — Chart has no such
    # method; the parent flavor lives on Layout. AttributeError is the
    # expected outcome (post Phase 3 leaf/parent type split).
    leaf = pt.chart(); leaf.line(data={"x": [1,2], "y": [1,2]}, x="x", y="y")
    try:
        leaf.share_x()
        failures.append("expected AttributeError calling share_x() on a leaf")
    except AttributeError:
        pass

    # 7b. parent-level gap() doesn't exist on a leaf, same as share().
    leaf = pt.chart(); leaf.line(data={"x": [1,2], "y": [1,2]}, x="x", y="y")
    try:
        leaf.gap(0)
        failures.append("expected AttributeError calling gap() on a leaf")
    except AttributeError:
        pass

    # 8. share scale plumbing — leaves in same share class get the same
    # descriptor, and the y range is the UNION of all leaves' data.
    src = pt.chart(); src.line(data={"x": [0, 10], "y": [0, 100]}, x="x", y="y")
    shr = pt.chart(); shr.line(data={"x": [0, 10], "y": [-5, 5]}, x="x", y="y")
    parent = (src | shr).share_y()
    from plotlet._layout_engine import _build_panel_opts
    panel_opts, _ = _build_panel_opts(parent)
    src_y = panel_opts[id(src)].y_axis
    shr_y = panel_opts[id(shr)].y_axis
    if src_y is not shr_y:
        failures.append(
            f"share_y did not produce a shared descriptor: "
            f"src=({src_y.lo},{src_y.hi}) shr=({shr_y.lo},{shr_y.hi})"
        )
    if shr_y.lo > -5 or shr_y.hi < 100:
        failures.append(
            f"share_y did not union ranges: expected to span [-5, 100], "
            f"got [{shr_y.lo}, {shr_y.hi}]"
        )

    # 9. Cross-layout share_x("col") on v-of-h with ragged rows raises
    # with a useful message — every sub-row must have the same number
    # of cells for the column mapping to be unambiguous.
    a1 = pt.chart(); a1.line(data={"x": [1], "y": [1]}, x="x", y="y")
    a2 = pt.chart(); a2.line(data={"x": [1], "y": [1]}, x="x", y="y")
    a3 = pt.chart(); a3.line(data={"x": [1], "y": [1]}, x="x", y="y")
    b1 = pt.chart(); b1.line(data={"x": [1], "y": [1]}, x="x", y="y")
    b2 = pt.chart(); b2.line(data={"x": [1], "y": [1]}, x="x", y="y")
    r_long  = a1 | a2 | a3
    r_short = b1 | b2
    try:
        (r_long / r_short).share_x("col")
        failures.append("expected ValueError on ragged v-of-h share_x('col')")
    except ValueError as ex:
        msg = str(ex).lower()
        if "same number of cells" not in msg:
            failures.append(f"expected 'same number of cells' message; got: {ex}")

    # 10. Cross-layout share_x("col") errors when a child isn't an h-layout
    # (e.g., a bare chart sneaking into the vertical stack).
    p1 = pt.chart(); p1.line(data={"x": [1], "y": [1]}, x="x", y="y")
    p2 = pt.chart(); p2.line(data={"x": [1], "y": [1]}, x="x", y="y")
    q = pt.chart(); q.line(data={"x": [1], "y": [1]}, x="x", y="y")
    r_ok = p1 | p2
    try:
        (r_ok / q).share_x("col")
        failures.append(
            "expected ValueError on share_x('col') with a bare-chart child"
        )
    except ValueError as ex:
        msg = str(ex).lower()
        if "'h' sub-layout" not in msg:
            failures.append(f"expected sub-layout message; got: {ex}")

    if failures:
        for f in failures:
            print(f"FAIL invariant: {f}")
        return 1
    print(f"OK     invariants ({12} checks)")
    return 0


import pytest

@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_subplots_baseline(name, fn, baseline_compare):
    baseline_compare("subplots", name, fn().to_svg())


def test_subplots_invariants():
    """Wraps the existing `_run_invariants` runner — see `test_attachments`
    for the same pattern."""
    failed = _run_invariants()
    assert failed == 0, f"{failed} subplot invariant(s) failed (see captured stdout)"
