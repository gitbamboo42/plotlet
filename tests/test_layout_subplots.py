#!/usr/bin/env python3
"""Baseline SVG regression tests for the subplot composition API.

    python tests/test_layout_subplots.py            # check vs. baselines, exit 1 on mismatch
    python tests/test_layout_subplots.py --update   # regenerate baselines (review diff!)
    python tests/test_layout_subplots.py --gallery  # write baseline_images/layout_subplots/index.html

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
from plotlet import aes



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
    df = {"x": xs, "y": [math.sin(x) for x in xs]}

    c = pt.chart(df, aes(x="x", y="y"), title="sin", data_width=data_width, data_height=data_height)
    c.add_line()
    return c


def _cos(data_width=220, data_height=320):
    xs = _xs()
    df = {"x": xs, "y": [math.cos(x) for x in xs]}

    c = pt.chart(df, aes(x="x", y="y"), title="cos", data_width=data_width, data_height=data_height)
    c.add_line()
    return c


def _bar(label="bar", data_width=220, data_height=320):
    df = {"x": ["a", "b", "c"], "y": [3, 1, 2]}

    c = pt.chart(df, aes(x="x", y="y"), title=label, data_width=data_width, data_height=data_height)
    c.add_bar()
    return c


def _hist(data_width=220, data_height=320):
    df = {"x": [0.1, 0.4, 0.5, 0.55, 0.7, 0.8, 0.9, 1.1, 1.3]}

    c = pt.chart(df, aes(x="x"), title="hist", data_width=data_width, data_height=data_height)
    c.add_hist(bins=6)
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
    df = {"x":["a","b","c"], "y":[3,1,2]}
    top  = pt.chart(df, aes(x="x", y="y"), title="top",   data_width=120, data_height=24);  top.add_bar()
    df2 = {"x": [1,2,3], "y": [3,1,2]}
    left = pt.chart(df2, aes(x="x", y="y"), title="left",  data_width=120, data_height=220); left.add_line()
    df3 = {"x": [1,2,3], "y": [1,4,9]}
    main = pt.chart(df3, aes(x="x", y="y"), title="main",  data_width=120, data_height=220); main.add_line()
    df4 = {"x": [1,2,3], "y": [2,2,1]}
    right= pt.chart(df4, aes(x="x", y="y"), title="right", data_width=120, data_height=220); right.add_line()
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
    df = {"x": [1,2,3], "y": [1,2,3]}
    a = pt.chart(df, aes(x="x", y="y"), title="a", data_width=180, data_height=140); a.add_line()
    df2 = {"x": [1,2,3], "y": [3,2,1]}
    b = pt.chart(df2, aes(x="x", y="y"), title="b", data_width=180, data_height=140); b.add_line()
    df3 = {"x": [1,2,3,4,5],
       "y": ["measurement_alpha", "measurement_beta", "measurement_gamma",
             "measurement_delta", "measurement_epsilon"]}
    c = pt.chart(df3, aes(x="x", y="y"), data_width=180, data_height=140, ylabel="categories")
    c.add_scatter()
    df4 = {"x": [1,2,3], "y": [1,2,3]}
    d = pt.chart(df4, aes(x="x", y="y"), data_width=180, data_height=140); d.add_line()
    return pt.grid([[a, b], [c, d]])


def body_first_unequal_columns():
    # Body-first per-cell data widths in 1:2:2 proportion (one narrow
    # column, two equal wider ones). Each leaf renders its data region at
    # exactly the requested pixel count — no ratio override needed; the
    # composition just sums them. With 0.2.0 there's no widths=/heights=
    # parameter on pt.grid: per-leaf data_width IS the way to express
    # "make this column twice as wide as that one."
    df = {"x": [1,2,3], "y": [1,4,9]}
    a = pt.chart(df, aes(x="x", y="y"), title="a", data_width=80,  data_height=300); a.add_line()
    df2 = {"x": [1,2,3], "y": [3,1,2]}
    b = pt.chart(df2, aes(x="x", y="y"), title="b", data_width=160, data_height=300); b.add_line()
    df3 = {"x": [1,2,3], "y": [5,2,4]}
    c = pt.chart(df3, aes(x="x", y="y"), title="c", data_width=160, data_height=300); c.add_line()
    return pt.grid([[a, b, c]])


def share_y_collapses_gap():
    # share_y → joined, gap 0.
    df = {"x": [1,2,3], "y": [1,4,9]}
    hm   = pt.chart(df, aes(x="x", y="y"), title="hm",   data_width=220); hm.add_line()
    df2 = {"x": [1,2,3], "y": [3,1,2]}
    tree = pt.chart(df2, aes(x="x", y="y"), title="tree", data_width=220); tree.add_line()
    return (tree | hm).share_y()


def share_x_collapses_gap_vertical():
    # share_x → joined, gap 0.
    df = {"x": [1, 2, 3], "y": [1, 4, 9]}
    main = pt.chart(df, aes(x="x", y="y"), title="main", data_height=120); main.add_line()
    df2 = {"x": [1, 2, 3], "y": [3, 1, 2]}
    top  = pt.chart(df2, aes(x="x", y="y"), title="top",  data_height=120); top.add_line()
    return (top / main).share_x()


def share_x_three_panels():
    # Three vertically-stacked panels all share x via parent-level .share_x().
    df = {"x": [0, 5, 10], "y": [0, 1, 0]}
    main = pt.chart(df, aes(x="x", y="y"), title="main", data_height=60); main.add_line()
    df2 = {"x": [0, 5, 10], "y": [10, 0, 10]}
    mid  = pt.chart(df2, aes(x="x", y="y"), title="mid",  data_height=60); mid.add_line()
    df3 = {"x": [0, 5, 10], "y": [5, 5, 5]}
    top  = pt.chart(df3, aes(x="x", y="y"), title="top",  data_height=60); top.add_line()
    return (top / mid / main).share_x()


def share_y_chain():
    # Three side-by-side panels all share y via parent-level .share_y().
    df = {"x": [1,2,3], "y": [0, 100, 0]}
    a = pt.chart(df, aes(x="x", y="y"), title="a", data_width=130); a.add_line()
    df2 = {"x": [1,2,3], "y": [10, 50, 90]}
    b = pt.chart(df2, aes(x="x", y="y"), title="b", data_width=130); b.add_line()
    df3 = {"x": [1,2,3], "y": [20, 40, 60]}
    c = pt.chart(df3, aes(x="x", y="y"), title="c", data_width=130); c.add_line()
    return (a | b | c).share_y()


def width_hint_narrow_side():
    # Narrow side panel sharing y with main. Stand-in for
    # `hm | pt.colorbar(hm)` — body-first per-leaf widths express the
    # main:side ratio directly.
    df = {"x": [1,2,3], "y": [1,4,9]}
    main = pt.chart(df, aes(x="x", y="y"), title="main", data_width=440); main.add_line()
    df2 = {"x": [1, 1, 1], "y": [1, 4, 9]}
    side = pt.chart(df2, aes(x="x", y="y"), title="side", data_width=24)
    side.add_line()
    return (main | side).share_y()


def height_hint_short_top():
    # Short top track over a main panel.
    df = {"x":["a","b","c"], "y":[1,2,3]}
    top  = pt.chart(df, aes(x="x", y="y"), title="top",  data_height=24)
    top.add_bar()
    df2 = {"x":["a","b","c"], "y":[3,1,2]}
    main = pt.chart(df2, aes(x="x", y="y"), title="main", data_height=240); main.add_bar()
    return (top / main).share_x()


def share_x_mismatched_groups():
    # Both panels declare categorical `groups=` on their own xscale, but
    # the mappings (and split_gap) CONFLICT. The anchor — first leaf of
    # the share class — wins for the whole class: one 14px gap after "c"
    # in both panels; the bottom panel's a|bcdef grouping and 30px gap
    # are ignored. Pins the anchor-wins policy of `_axis_descriptor`.
    cats = list("abcdef")
    df = {"cat": cats, "val": [3, 5, 2, 6, 4, 7]}
    top = pt.chart(df, aes(x="cat", y="val"), title="anchor: abc|def, gap 14", data_height=100)
    top.xscale("category",
               groups={"a": 1, "b": 1, "c": 1, "d": 2, "e": 2, "f": 2},
               split_gap=14)
    top.add_bar()
    df2 = {"cat": cats, "val": [2, 4, 6, 1, 3, 5]}
    main = pt.chart(df2, aes(x="cat", y="val"), title="ignored: a|bcdef, gap 30", data_height=100)
    main.xscale("category",
                groups={"a": 1, "b": 2, "c": 2, "d": 2, "e": 2, "f": 2},
                split_gap=30)
    main.add_bar()
    return (top / main).share_x()


def custom_gap_method():
    # `(a | b).gap(N)` overrides the default 20 px inter-panel gap.
    return (_sin(data_width=220) | _cos(data_width=220)).gap(4)


def custom_gap_grid_kwarg():
    # `.gap(N)` chained after `pt.grid([[...]])` — same override path
    # as for `|` / `/` layouts.
    a = _sin(data_width=120)
    b = _cos(data_width=120)
    c = _bar(data_width=120)
    return pt.grid([[a, b, c]]).gap(8)


def complex_grid_shares():
    # Annotated-heatmap shape via grid with column/row sharing:
    # `share_x="col"` → top↔main share x (column 1); `share_y="row"` →
    # tree↔main share y (row 1).
    df = {"x": [1,2,3,4,5], "y": [2,4,1,5,3]}
    main = pt.chart(df, aes(x="x", y="y"), title="main", data_width=400, data_height=240)
    main.add_line()
    df2 = {"x": [1,2,3,4,5], "y": [1,1,3,1,1]}
    top  = pt.chart(df2, aes(x="x", y="y"), title="top",  data_width=400, data_height=24)
    top.add_line()
    df3 = {"x": [0,1,2], "y": [2,3,4]}
    tree = pt.chart(df3, aes(x="x", y="y"), title="tree", data_width=60,  data_height=240)
    tree.add_line()
    return pt.grid([
        [None, top ],
        [tree, main],
    ]).share_x("col").share_y("row")


def share_x_scatter_heatmap():
    # Continuous scatter aligned over a continuous-x heatmap track via
    # share_x — the case categorical heatmaps can't do (numeric vs
    # categorical share classes are incompatible). The scatter is sampled
    # on the column grid so points sit on cell centers, and both leaves
    # pin `xlim` to the heatmap extent so the shared frame hugs the strip
    # (otherwise the scatter's auto domain-padding insets the cells).
    import math
    cols = [float(c) for c in range(12)]
    df2 = {"x": cols,
       "y": [math.sin(0.6 * c) + 0.2 * c for c in cols]}
    sc = pt.chart(df2, aes(x="x", y="y"), title="signal", data_height=110)
    sc.add_scatter()
    sc.xlim(-0.5, 11.5)
    tracks = ["t1", "t2", "t3"]
    df = {"x": cols}
    for row, name in enumerate(tracks):
        df[name] = [math.sin(0.5 * c + row) for c in cols]
    hm = pt.chart(title="tracks", data_height=90)
    hm.add_heatmap(data=df, mapping=aes(x="x"), values=tracks, cmap="viridis")
    hm.xlim(-0.5, 11.5)
    return (sc / hm).share_x(True)


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


def grid_suptitle():
    # Layout-level titles: the outer 2×1 composition carries a
    # figure-level title band, and the nested titled row gets its own
    # band above its sub-rect. Leaf panel titles render inside their
    # panels as usual — three title levels in one figure.
    a = _sin(data_width=200, data_height=120)
    b = _cos(data_width=200, data_height=120)
    row = (a | b).title("nested row title")
    c = _bar(data_width=420, data_height=110)
    return (row / c).title("Figure-level suptitle")


def share_x_col_v_of_h():
    # v-of-h composition with cross-row column-wise x-sharing — the
    # canonical "stacked tracks across a domain" shape. Each row uses
    # share_y().gap(0) to collapse inner spines within the row; the
    # outer `share_x("col")` aligns the same column across rows (column
    # widths differ on purpose to match the multi-track use case).
    def row(name):
        df = {"x": [0, 1, 2, 3, 4], "y": [0, 1, 2, 1, 0]}
        a = pt.chart(df, aes(x="x", y="y"), title=f"{name}-c1", data_width=160, data_height=70)
        a.add_line()
        df2 = {"x": [0, 1, 2, 3], "y": [2, 1, 3, 1]}
        b = pt.chart(df2, aes(x="x", y="y"), title=f"{name}-c2", data_width=110, data_height=70)
        b.add_line()
        df3 = {"x": [0, 1, 2], "y": [1, 2, 1]}
        c = pt.chart(df3, aes(x="x", y="y"), title=f"{name}-c3", data_width= 70, data_height=70)
        c.add_line()
        return (a | b | c).share_y().gap(0)
    return (row("r1") / row("r2") / row("r3")).share_x("col")


def chart_inset_zoom():
    # Long-tail bar distribution: the first two categories dwarf the rest,
    # making the tail unreadable in the parent. The inset shows only the
    # tail (C through J) at a zoomed y-range so those bars become legible.
    labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    counts = [950, 320, 80, 45, 28, 18, 12, 8, 5, 3]
    df = {"category": labels, "count": counts}
    df_tail = {"category": labels[2:], "count": counts[2:]}
    c = pt.chart(df, aes(x="category", y="count"), data_width=440, data_height=240,
                 title="long-tail distribution",
                 xlabel="category", ylabel="count")
    c.add_bar()
    inset = c.inset(rect=(0.4, 0.45, 0.55, 0.45),
                    ylim=(0, 100))
    inset.add_bar(df_tail, aes(x="category", y="count"))
    return c


PLOTS = {
    "inset_zoom": chart_inset_zoom,
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
    "share_x_scatter_heatmap": share_x_scatter_heatmap,
    "share_x_mismatched_groups": share_x_mismatched_groups,
    "gap_method":          custom_gap_method,
    "gap_grid_kwarg":      custom_gap_grid_kwarg,
    "fit_to_canvas":       fit_to_canvas,
    "fit_width_only":      fit_width_only,
    "share_x_col_v_of_h":  share_x_col_v_of_h,
    "grid_suptitle":       grid_suptitle,
}


def _run_invariants():
    """Cheap unit checks that don't fit the SVG-baseline shape."""
    failures = []

    # 1. show-on-child raises with a useful message
    df = {"x": [1,2,3], "y": [1,2,3]}
    a = pt.chart(df, aes(x="x", y="y")); a.add_line()
    df2 = {"x": [1,2,3], "y": [3,2,1]}
    b = pt.chart(df2, aes(x="x", y="y")); b.add_line()
    parent = a | b
    try:
        a.to_svg()
        failures.append("expected RuntimeError on parented child .to_svg()")
    except RuntimeError as e:
        if "parent" not in str(e).lower():
            failures.append(f"unexpected message: {e}")

    # 2. single-parent invariant
    df3 = {"x": [1,2,3], "y": [1,2,3]}
    c = pt.chart(df3, aes(x="x", y="y")); c.add_line()
    df4 = {"x": [1,2,3], "y": [3,2,1]}
    d = pt.chart(df4, aes(x="x", y="y")); d.add_line()
    df5 = {"x": [1,2,3], "y": [2,2,2]}
    e = pt.chart(df5, aes(x="x", y="y")); e.add_line()
    cd = c | d
    try:
        c | e
        failures.append("expected ValueError when composing a parented chart")
    except ValueError:
        pass

    # 3. flattening: `a | b | c` records as `(a|b) | c` (the AST Python
    # parses), preserving append-only journal semantics; the engine's
    # flat 3-cell view comes from `_effective_children()` at render time.
    df6 = {"x": [1], "y": [1]}
    p = pt.chart(df6, aes(x="x", y="y")); p.add_line()
    df7 = {"x": [1], "y": [1]}
    q = pt.chart(df7, aes(x="x", y="y")); q.add_line()
    df8 = {"x": [1], "y": [1]}
    r = pt.chart(df8, aes(x="x", y="y")); r.add_line()
    row = p | q | r
    flat = row._effective_children()
    if flat != [p, q, r]:
        failures.append(f"flatten: expected [p, q, r] effective children, got {flat}")

    # 4. cross-direction nests, doesn't flatten
    df9 = {"x": [1], "y": [1]}
    s = pt.chart(df9, aes(x="x", y="y")); s.add_line()
    df10 = {"x": [1], "y": [1]}
    t = pt.chart(df10, aes(x="x", y="y")); t.add_line()
    df11 = {"x": [1], "y": [1]}
    u = pt.chart(df11, aes(x="x", y="y")); u.add_line()
    pair = s | t
    col = pair / u
    if col._layout_kind != "v" or len(col._children) != 2:
        failures.append(
            f"nest: expected vertical parent of 2; got {col._layout_kind} with "
            f"{len(col._children)} children"
        )

    # 5. pt.grid validates row shape
    df12 = {"x": [1], "y": [1]}
    a1 = pt.chart(df12, aes(x="x", y="y")); a1.add_line()
    try:
        pt.grid([[a1, None], [a1]])
        failures.append("expected ValueError on ragged grid")
    except ValueError:
        pass

    # 6. share cycle detection — verify the engine validator directly.
    # The public Layout.share_x/y API can't construct a cycle (charts
    # in one share class point at a single anchor), and the journal
    # materializer resets `_share_x`/`_share_y` from recorded entries,
    # so direct field-poking before to_svg() no longer survives into
    # render. Drive `_topo_order` with hand-built leaves to confirm
    # the cycle guard still raises.
    from plotlet.render._layout_engine import _topo_order
    df13 = {"x": [1,2], "y": [1,2]}
    f1 = pt.chart(df13, aes(x="x", y="y")); f1.add_line()
    df14 = {"x": [1,2], "y": [2,1]}
    f2 = pt.chart(df14, aes(x="x", y="y")); f2.add_line()
    f1._share_y = f2
    f2._share_y = f1
    try:
        _topo_order([f1, f2])
        failures.append("expected ValueError on share_y cycle")
    except ValueError as ex:
        if "cycle" not in str(ex).lower():
            failures.append(f"expected cycle message; got: {ex}")

    # 7. parent-level share() doesn't exist on a leaf — Chart has no such
    # method; the parent flavor lives on Layout. AttributeError is the
    # expected outcome (post Phase 3 leaf/parent type split).
    df15 = {"x": [1,2], "y": [1,2]}
    leaf = pt.chart(df15, aes(x="x", y="y")); leaf.add_line()
    try:
        leaf.share_x()
        failures.append("expected AttributeError calling share_x() on a leaf")
    except AttributeError:
        pass

    # 7b. parent-level gap() doesn't exist on a leaf, same as share().
    df16 = {"x": [1,2], "y": [1,2]}
    leaf = pt.chart(df16, aes(x="x", y="y")); leaf.add_line()
    try:
        leaf.gap(0)
        failures.append("expected AttributeError calling gap() on a leaf")
    except AttributeError:
        pass

    # 8. share scale plumbing — leaves in same share class get the same
    # descriptor, and the y range is the UNION of all leaves' data.
    df17 = {"x": [0, 10], "y": [0, 100]}
    src = pt.chart(df17, aes(x="x", y="y")); src.add_line()
    df18 = {"x": [0, 10], "y": [-5, 5]}
    shr = pt.chart(df18, aes(x="x", y="y")); shr.add_line()
    parent = (src | shr).share_y()
    from plotlet.render._layout_engine import _resolve_panels
    from plotlet.render import hydrate, materialize
    root = hydrate(pt.to_ir(parent))
    materialize(root)
    panel_opts, _ = _resolve_panels(root)
    r_src, r_shr = root._iter_leaves()
    src_y = panel_opts[id(r_src)].y_axis
    shr_y = panel_opts[id(r_shr)].y_axis
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
    df19 = {"x": [1], "y": [1]}
    a1 = pt.chart(df19, aes(x="x", y="y")); a1.add_line()
    df20 = {"x": [1], "y": [1]}
    a2 = pt.chart(df20, aes(x="x", y="y")); a2.add_line()
    df21 = {"x": [1], "y": [1]}
    a3 = pt.chart(df21, aes(x="x", y="y")); a3.add_line()
    df22 = {"x": [1], "y": [1]}
    b1 = pt.chart(df22, aes(x="x", y="y")); b1.add_line()
    df23 = {"x": [1], "y": [1]}
    b2 = pt.chart(df23, aes(x="x", y="y")); b2.add_line()
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
    df24 = {"x": [1], "y": [1]}
    p1 = pt.chart(df24, aes(x="x", y="y")); p1.add_line()
    df25 = {"x": [1], "y": [1]}
    p2 = pt.chart(df25, aes(x="x", y="y")); p2.add_line()
    df26 = {"x": [1], "y": [1]}
    q = pt.chart(df26, aes(x="x", y="y")); q.add_line()
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
def test_layout_subplots_baseline(name, fn, baseline_compare):
    baseline_compare("layout_subplots", name, fn().to_svg())


def test_subplots_invariants():
    """Wraps the existing `_run_invariants` runner — see `test_layout_attachments`
    for the same pattern."""
    failed = _run_invariants()
    assert failed == 0, f"{failed} subplot invariant(s) failed (see captured stdout)"


def test_data_total_size_reflects_share_scaling():
    """The seam's `data_total_size` must report share-*coordinated* data
    dims, not the raw recorded ones — it runs the natural-size
    measurement pre-pass first, and that call is load-bearing even
    though its return value is discarded. `Chart.fit()` solves
    `target = s * data_total + overhead` from this number; a
    share-unaware value changes its convergence arithmetic.

    Here `share_y()` forces b (100×200) to the anchor's height (100)
    and rescales its width to preserve aspect (→ 50×100), so the h-row
    total is (200+50, max(100, 100)) — not the raw (300, 200)."""
    from plotlet.render import data_total_size

    df = {"x": [1, 2, 3], "y": [1, 2, 3]}
    a = pt.chart(df, aes(x="x", y="y"), data_width=200, data_height=100)
    a.add_scatter()
    df2 = {"x": [1, 2, 3], "y": [3, 2, 1]}
    b = pt.chart(df2, aes(x="x", y="y"), data_width=100, data_height=200)
    b.add_scatter()

    assert data_total_size(pt.to_ir(a | b)) == (300.0, 200.0)   # unshared control

    df3 = {"x": [1, 2, 3], "y": [1, 2, 3]}
    a2 = pt.chart(df3, aes(x="x", y="y"), data_width=200, data_height=100)
    a2.add_scatter()
    df4 = {"x": [1, 2, 3], "y": [3, 2, 1]}
    b2 = pt.chart(df4, aes(x="x", y="y"), data_width=100, data_height=200)
    b2.add_scatter()

    assert data_total_size(pt.to_ir((a2 | b2).share_y())) == (250.0, 100.0)


def test_layout_title_band():
    """`Layout.title` adds one centered band above the layout's rect:
    the figure grows by exactly the panel-title block (pad.title +
    title_size), the band text lands in regions as a `title` above
    every panel, and `fit()` treats the band as overhead."""
    from plotlet._spec import _FONTSPEC, _OUTER_MARGIN, _PADSPEC
    from plotlet.render import natural_size

    def cell(t):
        df = {"x": [1, 2, 3], "y": [3, 1, 2]}
        c = pt.chart(df, aes(x="x", y="y"), title=t, data_width=160, data_height=110)
        c.add_scatter()
        return c

    band = _PADSPEC["title"] + _FONTSPEC["title_size"]

    plain = pt.grid([[cell("a"), cell("b")]])
    titled = pt.grid([[cell("a"), cell("b")]]).title("Figure title")
    W0, H0 = natural_size(pt.to_ir(plain))
    W1, H1 = natural_size(pt.to_ir(titled))
    assert (W1, H1) == (W0, H0 + band)

    regs = [r for r in titled.regions() if r["name"] == "title"]
    texts = {r["meta"].get("text") for r in regs}
    assert "Figure title" in texts and {"a", "b"} <= texts
    fig_r = next(r for r in regs if r["meta"].get("text") == "Figure title")
    assert fig_r["bbox"][1] < band, "band title must sit inside the top band"
    assert all(fig_r["bbox"][1] < r["bbox"][1]
               for r in regs if r is not fig_r), "band sits above panel titles"

    fitted = titled.fit(canvas_width=250)
    Wf, _ = natural_size(pt.to_ir(fitted))
    trim = _OUTER_MARGIN["left"] + _OUTER_MARGIN["right"]
    assert abs(Wf + trim - 250) <= 1, "rendered SVG (natural + outer trim) fits the canvas"


def test_fit_scales_insets():
    # Insets are placed by an axes-fraction rect but sized absolutely —
    # fit() must scale them with the host or they overflow their
    # declared fraction of the shrunken panel.
    df = {"x": [1, 2, 3], "y": [1, 4, 9]}
    c = pt.chart(df, aes(x="x", y="y"),
                 data_width=400, data_height=300)
    c.add_line()
    ins = c.inset((0.6, 0.6, 0.35, 0.35))
    df2 = {"x": [1, 2], "y": [2, 1]}
    ins.add_line(df2, aes(x="x", y="y"))

    fitted = c.fit(canvas_width=250)
    host_ratio = fitted._data_width / c._data_width
    inset_ratio = fitted._insets[0][1]._data_width / ins._data_width
    assert abs(host_ratio - inset_ratio) < 0.05
