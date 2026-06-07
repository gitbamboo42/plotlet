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
    checks = 0
    failed = 0

    def _check(cond, msg):
        nonlocal checks, failed
        checks += 1
        if not cond:
            failed += 1
            print(f"FAIL   {msg}")

    # Size lock: attached chart's perpendicular dim matches host; parallel preserved.
    host = pt.chart(data_width=200, data_height=150)
    host.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    left = pt.chart(data_width=40, data_height=999)
    left.annotate("L", xy=(0.5, 1.0))
    host.attach_left(left)
    host.to_svg()
    _check(left._data_height == 150 and left._data_width == 40,
           "left attachment height locks to host; width preserved")

    top = pt.chart(data_width=999, data_height=40)
    host2 = pt.chart(data_width=200, data_height=150)
    host2.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    top.line(data={"x": [0, 1, 2], "y": [1, 2, 1]}, x="x", y="y")
    host2.attach_above(top)
    host2.to_svg()
    _check(top._data_width == 200 and top._data_height == 40,
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

    # Warning on existing share, but host wins.
    h4 = pt.chart(); h4.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    other = pt.chart(); other.line(data={"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y")
    side = pt.chart(); side.annotate("s", xy=(0.5, 1.0))
    side._share_y = other
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        h4.attach_left(side)
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
    from plotlet._layout_engine import _build_panel_opts, _measure, _allocate
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
