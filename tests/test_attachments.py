#!/usr/bin/env python3
"""Tests for `chart.attach_left/right/above/below`.

    python tests/test_attachments.py            # check vs. baselines
    python tests/test_attachments.py --update   # regenerate baselines
    python tests/test_attachments.py --gallery  # write index.html

Programmatic invariants first (fail-fast), then a handful of baseline
SVGs covering the shapes that exercise different code paths.
"""
from __future__ import annotations

import sys
import warnings

import plotlet as pt



# ---------------------------------------------------------------------------
# Plot builders — realistic annotated-heatmap-style content so attached
# charts inherit the host's axis range meaningfully (data coords on the
# attachment line up with the host's rows/columns).
# ---------------------------------------------------------------------------

def attach_four_sides_chained():
    # Heatmap with TWO chained attachments on every side. Exercises:
    #   - innermost-flush placement (each first attachment touches the host)
    #   - chained-flush placement (each second attachment touches the first)
    #   - independence between perpendicular sides
    rows = ["g1", "g2", "g3", "g4"]
    cols = ["s1", "s2", "s3", "s4", "s5"]
    matrix = [[i + j for j in range(5)] for i in range(4)]

    host = pt.chart(data_width=200, data_height=140, title="four sides")
    host.heatmap(matrix, xticklabels=cols, yticklabels=rows)

    def row_line(values):
        c = pt.chart(data_width=44)
        c.yscale("category", order=rows, padding=0)
        c.line(data={"x": values, "y": rows}, x="x", y="y")
        return c

    def col_line(values):
        c = pt.chart(data_height=34)
        c.xscale("category", order=cols, padding=0)
        c.line(data={"x": cols, "y": values}, x="x", y="y")
        return c

    host.attach_left(row_line([2, 4, 1, 3]), row_line([3, 1, 4, 2]))
    host.attach_right(row_line([1, 2, 4, 3]), row_line([4, 3, 2, 1]))
    host.attach_above(col_line([1, 3, 2, 4, 2]), col_line([4, 2, 3, 1, 5]))
    host.attach_below(col_line([2, 1, 3, 5, 4]), col_line([5, 4, 2, 1, 3]))
    return host


def attach_with_peer_legend():
    # Attachment composed with a layout-level legend as a peer — the
    # host-with-attachments is a single block from the outside.
    host = pt.chart(data_width=180, data_height=120)
    host.line(data={"x": [1, 2, 3, 4, 5], "y": [2, 4, 1, 3, 5]}, x="x", y="y", label="series A")
    host.line(data={"x": [1, 2, 3, 4, 5], "y": [1, 2, 3, 4, 5]}, x="x", y="y", label="series B")
    top_track = pt.chart(data_height=28)
    top_track.line(data={"x": [1, 2, 3, 4, 5], "y": [0.2, 0.7, 0.4, 0.6, 0.3]}, x="x", y="y")
    host.attach_above(top_track)
    return host | pt.legend()


# ---------------------------------------------------------------------------
# Programmatic invariants — essential behavioral guarantees.
# ---------------------------------------------------------------------------

def _run_invariants() -> int:
    # These invariants poke layout-engine internals (`_build_panel_opts`,
    # `_measure`, …) directly. Those expect a materialized tree —
    # render entry points (`to_svg`) materialize automatically, but
    # internal pokes must materialize themselves. The derive pass is
    # duck-typed, so it works on recorder trees here just like on the
    # hydrated render trees the engine normally sees.
    from plotlet.render import materialize
    checks = 0
    failed = 0

    def _check(cond, msg):
        nonlocal checks, failed
        checks += 1
        if not cond:
            failed += 1
            print(f"FAIL   {msg}")

    # Size lock: attached chart's perpendicular dim matches host; parallel
    # preserved. `to_svg()` renders a materialized copy and never mutates
    # the user's objects, so the lock is asserted on the render tree
    # (`_render_root()` + engine pass), not on the user's charts.
    host = pt.chart(data_width=200, data_height=150)
    host.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    left = pt.chart(data_width=40, data_height=999)
    left.annotate("L", xy=(0.5, 1.0))
    host.attach_left(left)
    root = host._render_root()
    root._to_svg_unchecked()
    # the root is the lone chart's 1×1 layout wrapper; the host leaf
    # (and its attachments) is its sole child
    (r_host,) = root._children
    r_left = r_host._attached_left[0]
    _check(r_left._data_height == 150 and r_left._data_width == 40,
           "left attachment height locks to host; width preserved")
    _check(left._data_height == 999 and left._data_width == 40,
           "render never mutates the user's chart objects")

    top = pt.chart(data_width=999, data_height=40)
    host2 = pt.chart(data_width=200, data_height=150)
    host2.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    top.line(data={"x": [0, 1, 2], "y": [1, 2, 1]}, x="x", y="y")
    host2.attach_above(top)
    root2 = host2._render_root()
    root2._to_svg_unchecked()
    (r_host2,) = root2._children
    r_top = r_host2._attached_above[0]
    _check(r_top._data_width == 200 and r_top._data_height == 40,
           "above attachment width locks to host; height preserved")

    # Validation: double-attach the same chart, attach already-parented chart.
    h3 = pt.chart(); h3.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    label = pt.chart(); label.annotate("x", xy=(0.5, 1.0))
    h3.attach_left(label)
    try:
        h3.attach_left(label)
        _check(False, "re-attaching same chart should raise")
    except ValueError:
        _check(True, "re-attaching same chart raises")

    a = pt.chart(); a.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    b = pt.chart(); b.line(data={"x": [1, 2, 3], "y": [3, 2, 1]}, x="x", y="y")
    _ = a | b
    c = pt.chart()
    try:
        c.attach_left(a)
        _check(False, "attaching parented chart should raise")
    except ValueError:
        _check(True, "attaching parented chart raises")

    # Warning on existing share, but host wins. The warning fires at
    # `attach_left` call time (validation); the field write is done by
    # `materialize()` at render, so we trigger it explicitly here.
    h4 = pt.chart(); h4.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    other = pt.chart(); other.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    side = pt.chart(); side.annotate("s", xy=(0.5, 1.0))
    side._share_y = other
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        h4.attach_left(side)
    materialize(h4)
    _check(any("share_y" in str(w.message) for w in caught)
           and side._share_y is h4,
           "existing share warns and host overrides")

    # Peer composition still works: host's _parent stays None until composed.
    h5 = pt.chart(); h5.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    side2 = pt.chart(); side2.annotate("s", xy=(0.5, 1.0))
    h5.attach_left(side2)
    _check(h5._parent is None, "host's _parent stays None until composed as peer")
    fig = h5 | pt.legend()
    _check(h5._parent is fig, "host gets _parent when composed")

    # Data-area alignment via positioning: host with title + attachment
    # without → each keeps its own top margin, but the attachment's
    # canvas is offset so its data area starts at the same y as the
    # host's data area.
    h6 = pt.chart(data_width=200, data_height=150, title="TITLE")
    h6.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    left2 = pt.chart(data_width=40)
    left2.annotate("L", xy=(0.5, 2.0))
    h6.attach_left(left2)
    materialize(h6)
    from plotlet.render._layout_engine import _build_panel_opts, _measure, _allocate
    po, _ = _build_panel_opts(h6)
    W, H = _measure(h6)
    placements = []
    _allocate(h6, 0, 0, W, H, placements)
    rects = dict(placements)
    h6_M = po[id(h6)].M_eff
    left_M = po[id(left2)].M_eff
    h6_data_y = rects[h6][1] + h6_M["top"]
    left_data_y = rects[left2][1] + left_M["top"]
    _check(h6_data_y == left_data_y,
           f"host/left data areas align in y (host_data_y={h6_data_y}, "
           f"left_data_y={left_data_y})")

    # Sector inheritance: above-attachment picks up host's x-sectors.
    from plotlet.render._layout_engine import _build_panel_opts as _bpo
    h7 = pt.chart(data_width=240, data_height=100)
    h7.sectors({"chr1": 100, "chr2": 200}, axis="x", column="chr",
               divider=True, label=True)
    h7.line(data={"chr": ["chr1"], "x": [50], "y": [1]}, x="x", y="y")
    top7 = pt.chart(data_height=30)
    top7.line(data={"chr": ["chr2"], "x": [10], "y": [1]}, x="x", y="y")
    h7.attach_above(top7)
    materialize(h7)
    _, states7 = _bpo(h7)
    st_top = states7[id(top7)]
    _check(st_top["x_sectors"] is not None,
           "above attachment inherits host's x_sectors")
    _check(st_top["x_sectors"] is not None
           and st_top["x_sectors"].divider is False
           and st_top["x_sectors"].label is False,
           "inherited sectors force divider=False, label=False on attachment")
    _check(st_top["x_sector_column"] == "chr",
           "inherited sector column carried through for data remap")

    # Sector inheritance: left-attachment picks up host's y-sectors (categorical).
    rows7 = ["g1", "g2", "g3", "g4"]
    cols7 = ["s1", "s2"]
    h8 = pt.chart(data_width=120, data_height=140)
    h8.sectors({"A": ["g1", "g2"], "B": ["g3", "g4"]}, axis="y",
               divider=False, label=False)
    h8.heatmap([[1, 2], [2, 3], [3, 4], [4, 5]],
               xticklabels=cols7, yticklabels=rows7)
    left8 = pt.chart(data_width=20)
    left8.yscale("category", order=rows7, padding=0)
    left8.line(data={"x": [1, 2, 1, 2], "y": rows7}, x="x", y="y")
    h8.attach_left(left8)
    materialize(h8)
    _, states8 = _bpo(h8)
    _check(states8[id(left8)]["y_sectors"] is not None,
           "left attachment inherits host's y_sectors (categorical)")

    # Explicit attachment-side sectors call wins over inheritance.
    h9 = pt.chart(data_width=240, data_height=100)
    h9.sectors({"chr1": 100}, axis="x", column="chr", divider=True, label=True)
    h9.line(data={"chr": ["chr1"], "x": [50], "y": [1]}, x="x", y="y")
    top9 = pt.chart(data_height=30)
    top9.sectors({"chr1": 100}, axis="x", column="chr",
                 divider=True, label=True)
    top9.line(data={"chr": ["chr1"], "x": [50], "y": [1]}, x="x", y="y")
    h9.attach_above(top9)
    materialize(h9)
    _, states9 = _bpo(h9)
    _check(states9[id(top9)]["x_sectors"] is not None
           and states9[id(top9)]["x_sectors"].divider is True,
           "explicit c.sectors() on attachment overrides inheritance")

    # Non-mutation: attachment sector inheritance now emits a cascade
    # entry at the call site in `_build_panel_opts` instead of mutating
    # `top7._calls`. Re-running the pre-pass must not touch the leaf
    # journal (idempotence is automatic, but pin the no-mutation
    # property explicitly so a regression resurrecting an insert(0)
    # path would surface here).
    snapshot = list(top7._calls)
    _bpo(h7)  # second pass
    _check(top7._calls == snapshot,
           "attachment sector inheritance does not mutate attached leaf _calls")

    if failed:
        print(f"\n{failed} of {checks} attachment invariants FAILED")
    else:
        print(f"OK     invariants ({checks} checks)")
    return failed


PLOTS = {
    "attach_four_sides_chained": attach_four_sides_chained,
    "attach_with_peer_legend":   attach_with_peer_legend,
}


import pytest

@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_attachments_baseline(name, fn, baseline_compare):
    baseline_compare("attachments", name, fn().to_svg())


def test_attachments_invariants():
    """Wraps the existing `_run_invariants` print-based runner so its
    behavioral checks (size lock, share warning, data-area alignment)
    run under pytest. A non-zero return surfaces as a single failure
    with the count of failed invariants; individual failures get
    printed to captured stdout."""
    failed = _run_invariants()
    assert failed == 0, f"{failed} attachment invariant(s) failed (see captured stdout)"
