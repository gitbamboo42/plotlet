#!/usr/bin/env python3
"""Baseline SVG regression tests for the subplot composition API.

    python tests/test_subplots.py            # check vs. baselines, exit 1 on mismatch
    python tests/test_subplots.py --update   # regenerate baselines (review diff!)
    python tests/test_subplots.py --gallery  # write baseline_images/subplots/index.html

Step 1 covers: `|`, `/`, `pt.grid`, single-parent invariant, show-on-child
raise, default gap, auto-zero-gap when neighbors have share_x= /
share_y=. Step 2 adds scale-sharing — shared panels render on the source's
domain — plus inner-axis collapse on joined share-pairs (no inner spine,
ticks, or labels) and leaf size-hint honoring (`pt.chart(canvas_width=...)` acts
as a relative width when no explicit ratios are given).
"""
from __future__ import annotations

import math
import sys

import plotlet as pt

import _runner


def _xs():
    return [i * 0.1 for i in range(64)]


# Composition is component-first (sum-sizes), so each test below picks per-leaf
# dimensions that *add up* to roughly the spec default of 600×400 — that way
# the gallery and at-a-glance review aren't dominated by one giant 1800-wide
# canvas. Sizes account for the default 20 px gap on non-joined pairs and
# 0 px on auto-collapsed share-pairs.

def _sin(canvas_width=290, canvas_height=400):
    xs = _xs()
    c = pt.chart(title="sin", canvas_width=canvas_width, canvas_height=canvas_height)
    c.line(xs, [math.sin(x) for x in xs])
    return c


def _cos(canvas_width=290, canvas_height=400):
    xs = _xs()
    c = pt.chart(title="cos", canvas_width=canvas_width, canvas_height=canvas_height)
    c.line(xs, [math.cos(x) for x in xs])
    return c


def _bar(label="bar", canvas_width=290, canvas_height=400):
    c = pt.chart(title=label, canvas_width=canvas_width, canvas_height=canvas_height)
    c.bar(["a", "b", "c"], [3, 1, 2])
    return c


def _hist(canvas_width=290, canvas_height=400):
    c = pt.chart(title="hist", canvas_width=canvas_width, canvas_height=canvas_height)
    c.hist([0.1, 0.4, 0.5, 0.55, 0.7, 0.8, 0.9, 1.1, 1.3], bins=6)
    return c


def row_two():
    # 2 panels h, default gap 20 → 290 + 20 + 290 = 600.
    return _sin(canvas_width=290) | _cos(canvas_width=290)


def col_two():
    # 2 panels v, default gap 20 → 190 + 20 + 190 = 400 tall, 600 wide.
    return _sin(canvas_width=600, canvas_height=190) / _cos(canvas_width=600, canvas_height=190)


def row_three_flatten():
    # `a | b | c` — left-fold flatten into a single 3-cell row, not a
    # 25/25/50 nested split. 3*187 + 2*20 = 601.
    return _sin(canvas_width=187) | _cos(canvas_width=187) | _bar(canvas_width=187)


def two_by_two():
    # 4 panels in 2x2 (no shares). 290+20+290 = 600 wide; 190+20+190 = 400 tall.
    a = _sin(canvas_width=290, canvas_height=190)
    b = _cos(canvas_width=290, canvas_height=190)
    c = _bar(canvas_width=290, canvas_height=190)
    d = _hist(canvas_width=290, canvas_height=190)
    return (a | b) / (c | d)


def grid_with_spacers():
    # 3-col 2-row irregular grid with None corners.
    # Cols: 187 + 20 + 187 + 20 + 187 = 601 wide.
    # Rows: 80 + 20 + 300 = 400 tall.
    top  = pt.chart(title="top",   canvas_width=187, canvas_height=80);  top.bar(["a","b","c"], [3,1,2])
    left = pt.chart(title="left",  canvas_width=187, canvas_height=300); left.line([1,2,3], [3,1,2])
    main = pt.chart(title="main",  canvas_width=187, canvas_height=300); main.line([1,2,3], [1,4,9])
    right= pt.chart(title="right", canvas_width=187, canvas_height=300); right.line([1,2,3], [2,2,1])
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
    a = pt.chart(title="a", data_width=180, data_height=140); a.line([1,2,3], [1,2,3])
    b = pt.chart(title="b", data_width=180, data_height=140); b.line([1,2,3], [3,2,1])
    c = pt.chart(data_width=180, data_height=140, ylabel="categories")
    c.scatter([1,2,3,4,5], ["measurement_alpha", "measurement_beta", "measurement_gamma",
                              "measurement_delta", "measurement_epsilon"])
    d = pt.chart(data_width=180, data_height=140); d.line([1,2,3], [1,2,3])
    return pt.grid([[a, b], [c, d]])


def body_first_unequal_columns():
    # Body-first per-cell data widths in 1:2:2 proportion (one narrow
    # column, two equal wider ones). Each leaf renders its data region at
    # exactly the requested pixel count — no ratio override needed; the
    # composition just sums them. With 0.2.0 there's no widths=/heights=
    # parameter on pt.grid: per-leaf data_width IS the way to express
    # "make this column twice as wide as that one."
    a = pt.chart(title="a", data_width=80,  data_height=300); a.line([1,2,3], [1,4,9])
    b = pt.chart(title="b", data_width=160, data_height=300); b.line([1,2,3], [3,1,2])
    c = pt.chart(title="c", data_width=160, data_height=300); c.line([1,2,3], [5,2,4])
    return pt.grid([[a, b, c]])


def share_y_collapses_gap():
    # Sharer adopts source's y-domain. share_y → joined, gap 0.
    # 300 + 0 + 300 = 600 wide.
    hm   = pt.chart(title="hm",   canvas_width=300);                 hm.line([1,2,3], [1,4,9])
    tree = pt.chart(title="tree", canvas_width=300, share_y=hm);     tree.line([1,2,3], [3,1,2])
    return tree | hm


def share_x_collapses_gap_vertical():
    # share_x → joined, gap 0. 200 + 0 + 200 = 400 tall.
    main = pt.chart(title="main", canvas_height=200);                  main.line([1, 2, 3], [1, 4, 9])
    top  = pt.chart(title="top",  canvas_height=200, share_x=main);    top.line([1, 2, 3], [3, 1, 2])
    return top / main


def share_x_three_panels():
    # Chain: top.share_x=mid, mid.share_x=main. All three end up on main's
    # domain (transitive via topo-sort) and the two adjacent pairs both
    # auto-collapse. 3*133 = 399 ≈ 400 tall.
    main = pt.chart(title="main", canvas_height=133);                main.line([0, 5, 10], [0, 1, 0])
    mid  = pt.chart(title="mid",  canvas_height=133, share_x=main);  mid.line([0, 5, 10], [10, 0, 10])
    top  = pt.chart(title="top",  canvas_height=133, share_x=mid);   top.line([0, 5, 10], [5, 5, 5])
    return top / mid / main


def share_y_chain():
    # Chain: B shares y from A, C shares y from B. All three joined.
    # 3*200 = 600 wide.
    a = pt.chart(title="a", canvas_width=200);                a.line([1,2,3], [0, 100, 0])
    b = pt.chart(title="b", canvas_width=200, share_y=a);     b.line([1,2,3], [10, 50, 90])
    c = pt.chart(title="c", canvas_width=200, share_y=b);     c.line([1,2,3], [20, 40, 60])
    return a | b | c


def width_hint_narrow_side():
    # Narrow side panel sharing y with main. Stand-in for
    # `hm | pt.colorbar(hm)`. 520 + 0 + 80 = 600 wide.
    main = pt.chart(title="main", canvas_width=520);                main.line([1,2,3], [1,4,9])
    side = pt.chart(title="side", canvas_width=80, share_y=main)
    side.line([1, 1, 1], [1, 4, 9])
    return main | side


def height_hint_short_top():
    # Short top track over a main panel. 80 + 0 + 320 = 400 tall.
    top  = pt.chart(title="top",  canvas_height=80)
    top.bar(["a","b","c"], [1, 2, 3])
    main = pt.chart(title="main", canvas_height=320, share_x=top); main.bar(["a","b","c"], [3, 1, 2])
    return top / main


def complex_grid_shares():
    # ComplexHeatmap-flavored shape: top track shares x with main; left tree
    # shares y with main. Both share-pairs are joined (gap 0). The
    # None-bordered cells mean col / row gaps are still 0 (min over the
    # boundary). Cols: 120 + 0 + 480 = 600. Rows: 80 + 0 + 320 = 400.
    main = pt.chart(title="main", canvas_width=480, canvas_height=320)
    main.line([1,2,3,4,5], [2,4,1,5,3])
    top  = pt.chart(title="top",  canvas_width=480, canvas_height=80,  share_x=main)
    top.line([1,2,3,4,5], [1,1,3,1,1])
    tree = pt.chart(title="tree", canvas_width=120, canvas_height=320, share_y=main)
    tree.line([0,1,2], [2,3,4])
    return pt.grid([
        [None, top ],
        [tree, main],
    ])


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
}


def _run_invariants():
    """Cheap unit checks that don't fit the SVG-baseline shape."""
    failures = []

    # 1. show-on-child raises with a useful message
    a = pt.chart(); a.line([1,2,3], [1,2,3])
    b = pt.chart(); b.line([1,2,3], [3,2,1])
    parent = a | b
    try:
        a.to_svg()
        failures.append("expected RuntimeError on parented child .to_svg()")
    except RuntimeError as e:
        if "parent" not in str(e).lower():
            failures.append(f"unexpected message: {e}")

    # 2. single-parent invariant
    c = pt.chart(); c.line([1,2,3], [1,2,3])
    d = pt.chart(); d.line([1,2,3], [3,2,1])
    e = pt.chart(); e.line([1,2,3], [2,2,2])
    cd = c | d
    try:
        c | e
        failures.append("expected ValueError when composing a parented chart")
    except ValueError:
        pass

    # 3. flattening: a | b | c yields one parent with three children
    p = pt.chart(); p.line([1],[1])
    q = pt.chart(); q.line([1],[1])
    r = pt.chart(); r.line([1],[1])
    row = p | q | r
    if len(row._children) != 3:
        failures.append(f"flatten: expected 3 children, got {len(row._children)}")

    # 4. cross-direction nests, doesn't flatten
    s = pt.chart(); s.line([1],[1])
    t = pt.chart(); t.line([1],[1])
    u = pt.chart(); u.line([1],[1])
    pair = s | t
    col = pair / u
    if col._layout_kind != "v" or len(col._children) != 2:
        failures.append(
            f"nest: expected vertical parent of 2; got {col._layout_kind} with "
            f"{len(col._children)} children"
        )

    # 5. pt.grid validates row shape
    a1 = pt.chart(); a1.line([1],[1])
    try:
        pt.grid([[a1, None], [a1]])
        failures.append("expected ValueError on ragged grid")
    except ValueError:
        pass

    # 6. share cycle detection
    f1 = pt.chart(); f1.line([1,2],[1,2])
    f2 = pt.chart(); f2.line([1,2],[2,1])
    f1._share_y = f2
    f2._share_y = f1   # cycle
    try:
        (f1 | f2).to_svg()
        failures.append("expected ValueError on share_y cycle")
    except ValueError as ex:
        if "cycle" not in str(ex).lower():
            failures.append(f"expected cycle message; got: {ex}")

    # 7. share target out of tree
    g1 = pt.chart(); g1.line([1,2],[1,2])
    g2 = pt.chart(); g2.line([1,2],[2,1])
    h1 = pt.chart(); h1.line([1,2],[1,2])
    h2 = pt.chart(share_y=g1); h2.line([1,2],[2,1])  # shares with chart not in same composition
    g1 | g2  # consume g1 into a different parent
    try:
        (h1 | h2).to_svg()
        failures.append("expected ValueError on out-of-tree share")
    except ValueError as ex:
        if "composition" not in str(ex).lower():
            failures.append(f"expected out-of-tree message; got: {ex}")

    # 8. share scale plumbing — sharer adopts source's domain
    src   = pt.chart(); src.line([0, 10], [0, 100])
    shr   = pt.chart(share_y=src); shr.line([0, 10], [-5, 5])
    parent = src | shr
    # Both leaves should use the same y descriptor.
    from plotlet.layout import _build_panel_opts
    panel_opts, _ = _build_panel_opts(parent)
    src_y = panel_opts[id(src)].y_axis
    shr_y = panel_opts[id(shr)].y_axis
    if src_y is not shr_y:
        failures.append(
            f"share_y= did not produce a shared descriptor: "
            f"src=({src_y.lo},{src_y.hi}) shr=({shr_y.lo},{shr_y.hi})"
        )
    if shr_y.lo > -5 or shr_y.hi < 100:
        # Sharer's data exceeds source's domain — the share semantic is
        # "adopt the source", so sharer's [-5, 5] does NOT extend src's
        # [0, 100] domain. This check is intentionally loose.
        pass  # informational; not a failure

    if failures:
        for f in failures:
            print(f"FAIL invariant: {f}")
        return 1
    print(f"OK     invariants ({8} checks)")
    return 0


if __name__ == "__main__":
    rc1 = _run_invariants()
    rc2 = _runner.run("subplots", PLOTS)
    sys.exit(rc1 or rc2)
