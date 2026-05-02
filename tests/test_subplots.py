#!/usr/bin/env python3
"""Baseline SVG regression tests for the subplot composition API.

    python tests/test_subplots.py            # check vs. baselines, exit 1 on mismatch
    python tests/test_subplots.py --update   # regenerate baselines (review diff!)
    python tests/test_subplots.py --gallery  # write baseline_images/subplots/index.html

Step 1 covers: `|`, `/`, `pt.grid`, single-parent invariant, show-on-child
raise, default gutter, auto-zero-gutter when neighbors have share_x= /
share_y=. Scale sharing is step 2 — the share_y= here only collapses the
gutter; each panel still builds its own independent y-scale.
"""
from __future__ import annotations

import math
import sys

import plotlet as pt

import _runner


def _xs():
    return [i * 0.1 for i in range(64)]


def _sin():
    xs = _xs()
    c = pt.chart(title="sin")
    c.line(xs, [math.sin(x) for x in xs])
    return c


def _cos():
    xs = _xs()
    c = pt.chart(title="cos")
    c.line(xs, [math.cos(x) for x in xs])
    return c


def _bar(label="bar"):
    c = pt.chart(title=label)
    c.bar(["a", "b", "c"], [3, 1, 2])
    return c


def _hist():
    c = pt.chart(title="hist")
    c.hist([0.1, 0.4, 0.5, 0.55, 0.7, 0.8, 0.9, 1.1, 1.3], bins=6)
    return c


def row_two():
    return _sin() | _cos()


def col_two():
    return _sin() / _cos()


def row_three_flatten():
    # `_sin() | _cos() | _bar()` — left-fold flatten so all three are
    # equal-width children of one parent, not a 25/25/50 nested split.
    return _sin() | _cos() | _bar()


def two_by_two():
    return (_sin() | _cos()) / (_bar() | _hist())


def grid_with_spacers():
    top  = pt.chart(title="top");    top.bar(["a","b","c"], [3,1,2])
    left = pt.chart(title="left");   left.line([1,2,3], [3,1,2])
    main = pt.chart(title="main");   main.line([1,2,3], [1,4,9])
    right= pt.chart(title="right");  right.line([1,2,3], [2,2,1])
    return pt.grid([
        [None, top,  None ],
        [left, main, right],
    ])


def grid_with_widths():
    a = pt.chart(title="a"); a.line([1,2,3], [1,4,9])
    b = pt.chart(title="b"); b.line([1,2,3], [3,1,2])
    c = pt.chart(title="c"); c.line([1,2,3], [5,2,4])
    return pt.grid([[a, b, c]], widths=[0.4, 1, 1])


def share_y_collapses_gutter():
    # Step 1: share_y= is recorded as a layout hint; it only collapses the
    # h-gutter between the two panels. Scale-sharing comes in step 2.
    hm   = pt.chart(title="hm");   hm.line([1,2,3], [1,4,9])
    tree = pt.chart(title="tree", share_y=hm); tree.line([1,2,3], [3,1,2])
    return tree | hm


def share_x_collapses_gutter_vertical():
    main = pt.chart(title="main"); main.line([1,2,3], [1,4,9])
    top  = pt.chart(title="top",  share_x=main); top.bar(["a","b","c"], [3,1,2])
    return top / main


PLOTS = {
    "row_two":             row_two,
    "col_two":             col_two,
    "row_three_flatten":   row_three_flatten,
    "two_by_two":          two_by_two,
    "grid_with_spacers":   grid_with_spacers,
    "grid_with_widths":    grid_with_widths,
    "share_y_no_gutter":   share_y_collapses_gutter,
    "share_x_no_gutter":   share_x_collapses_gutter_vertical,
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

    if failures:
        for f in failures:
            print(f"FAIL invariant: {f}")
        return 1
    print("OK     invariants (5 checks)")
    return 0


if __name__ == "__main__":
    rc1 = _run_invariants()
    rc2 = _runner.run("subplots", PLOTS)
    sys.exit(rc1 or rc2)
