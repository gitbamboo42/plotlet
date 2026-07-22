#!/usr/bin/env python3
"""Tests for `chart.attach_left/right/above/below`.

    python tests/test_layout_attachments.py            # check vs. baselines
    python tests/test_layout_attachments.py --update   # regenerate baselines
    python tests/test_layout_attachments.py --gallery  # write index.html

Programmatic invariants first (fail-fast), then a handful of baseline
SVGs covering the shapes that exercise different code paths.
"""
from __future__ import annotations

import sys
import warnings

import plotlet as pt
from plotlet import aes



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
    hm_df = {"col": cols}
    for name, values in zip(rows, matrix):
        hm_df[name] = values
    host.add_heatmap(data=hm_df, mapping=aes(x="col"), values=rows)

    def row_line(values):
        df = {"x": values, "y": rows}
        c = pt.chart(df, aes(x="x", y="y"), data_width=44)
        c.yscale("category", order=rows, padding=0)
        c.add_line()
        return c

    def col_line(values):
        df = {"x": cols, "y": values}
        c = pt.chart(df, aes(x="x", y="y"), data_height=34)
        c.xscale("category", order=cols, padding=0)
        c.add_line()
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
    df = {"x": [1, 2, 3, 4, 5], "y": [2, 4, 1, 3, 5]}
    host.add_line(df, aes(x="x", y="y"), label="series A")
    df2 = {"x": [1, 2, 3, 4, 5], "y": [1, 2, 3, 4, 5]}
    host.add_line(df2, aes(x="x", y="y"), label="series B")
    df3 = {"x": [1, 2, 3, 4, 5], "y": [0.2, 0.7, 0.4, 0.6, 0.3]}
    top_track = pt.chart(df3, aes(x="x", y="y"), data_height=28)
    top_track.add_line()
    host.attach_above(top_track)
    return host | pt.legend()


# ---------------------------------------------------------------------------
# Programmatic invariants — essential behavioral guarantees.
# ---------------------------------------------------------------------------

def _run_invariants() -> int:
    # These invariants poke layout-engine internals (`_resolve_panels`,
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
    # preserved. Rendering resolves a materialized copy and never mutates
    # the user's objects, so the lock is asserted on the hydrated render
    # tree after `_build_plan` (which runs the share-scaling pass that
    # stamps the locked dims), not on the user's charts.
    from plotlet.render import hydrate
    from plotlet.render._layout_engine import _build_plan
    df = {"x": [1, 2, 3], "y": [1, 2, 3]}
    host = pt.chart(df, aes(x="x", y="y"), data_width=200, data_height=150)
    host.add_line()
    left = pt.chart(data_width=40, data_height=999)
    left.add_annotate("L", xy=(0.5, 1.0))
    host.attach_left(left)
    root = hydrate(pt.to_ir(host))
    _build_plan(root)
    # the root is the lone chart's 1×1 layout wrapper; the host leaf
    # (and its attachments) is its sole child
    (r_host,) = root._children
    r_left = r_host._attached_left[0]
    _check(r_left._data_height == 150 and r_left._data_width == 40,
           "left attachment height locks to host; width preserved")
    _check(left._data_height == 999 and left._data_width == 40,
           "render never mutates the user's chart objects")

    df3 = {"x": [0, 1, 2], "y": [1, 2, 1]}
    top = pt.chart(df3, aes(x="x", y="y"), data_width=999, data_height=40)
    top.add_line()
    df2 = {"x": [1, 2, 3], "y": [1, 2, 3]}
    host2 = pt.chart(df2, aes(x="x", y="y"), data_width=200, data_height=150)
    host2.add_line()
    host2.attach_above(top)
    root2 = hydrate(pt.to_ir(host2))
    _build_plan(root2)
    (r_host2,) = root2._children
    r_top = r_host2._attached_above[0]
    _check(r_top._data_width == 200 and r_top._data_height == 40,
           "above attachment width locks to host; height preserved")

    # Validation: double-attach the same chart, attach already-parented chart.
    df4 = {"x": [1, 2, 3], "y": [1, 2, 3]}
    h3 = pt.chart(df4, aes(x="x", y="y")); h3.add_line()
    label = pt.chart(); label.add_annotate("x", xy=(0.5, 1.0))
    h3.attach_left(label)
    try:
        h3.attach_left(label)
        _check(False, "re-attaching same chart should raise")
    except ValueError:
        _check(True, "re-attaching same chart raises")

    df5 = {"x": [1, 2, 3], "y": [1, 2, 3]}
    a = pt.chart(df5, aes(x="x", y="y")); a.add_line()
    df6 = {"x": [1, 2, 3], "y": [3, 2, 1]}
    b = pt.chart(df6, aes(x="x", y="y")); b.add_line()
    _ = a | b
    c = pt.chart()
    try:
        c.attach_left(a)
        _check(False, "attaching parented chart should raise")
    except ValueError:
        _check(True, "attaching parented chart raises")

    # Warning on existing share, but host wins. The warning fires at
    # `attach_left` call time (validation); the field write is done by
    # `materialize()` on the hydrated tree, so we hydrate and run it
    # explicitly here.
    df7 = {"x": [1, 2, 3], "y": [1, 2, 3]}
    h4 = pt.chart(df7, aes(x="x", y="y")); h4.add_line()
    df8 = {"x": [1, 2, 3], "y": [1, 2, 3]}
    other = pt.chart(df8, aes(x="x", y="y")); other.add_line()
    side = pt.chart(); side.add_annotate("s", xy=(0.5, 1.0))
    side._share_y = other
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        h4.attach_left(side)
    root4 = hydrate(pt.to_ir(h4))
    materialize(root4)
    (r_h4,) = root4._children
    r_side = r_h4._attached_left[0]
    _check(any("share_y" in str(w.message) for w in caught)
           and r_side._share_y is r_h4,
           "existing share warns and host overrides")

    # Peer composition still works: host's _parent stays None until composed.
    df9 = {"x": [1, 2, 3], "y": [1, 2, 3]}
    h5 = pt.chart(df9, aes(x="x", y="y")); h5.add_line()
    side2 = pt.chart(); side2.add_annotate("s", xy=(0.5, 1.0))
    h5.attach_left(side2)
    _check(h5._parent is None, "host's _parent stays None until composed as peer")
    fig = h5 | pt.legend()
    _check(h5._parent is fig, "host gets _parent when composed")

    # Data-area alignment via positioning: host with title + attachment
    # without → each keeps its own top margin, but the attachment's
    # canvas is offset so its data area starts at the same y as the
    # host's data area.
    df10 = {"x": [1, 2, 3], "y": [1, 2, 3]}
    h6 = pt.chart(df10, aes(x="x", y="y"), data_width=200, data_height=150, title="TITLE")
    h6.add_line()
    left2 = pt.chart(data_width=40)
    left2.add_annotate("L", xy=(0.5, 2.0))
    h6.attach_left(left2)
    root6 = hydrate(pt.to_ir(h6))
    materialize(root6)
    (r_h6,) = root6._children
    r_left2 = r_h6._attached_left[0]
    from plotlet.render._layout_engine import _resolve_panels, _measure, _allocate
    panel_opts, _ = _resolve_panels(root6)
    W, H = _measure(root6)
    placements = []
    _allocate(root6, 0, 0, W, H, placements)
    rects = dict(placements)
    h6_M = panel_opts[id(r_h6)].M_eff
    left_M = panel_opts[id(r_left2)].M_eff
    h6_data_y = rects[r_h6][1] + h6_M["top"]
    left_data_y = rects[r_left2][1] + left_M["top"]
    _check(h6_data_y == left_data_y,
           f"host/left data areas align in y (host_data_y={h6_data_y}, "
           f"left_data_y={left_data_y})")

    # Sector inheritance: above-attachment picks up host's x-sectors.
    from plotlet.render._layout_engine import _resolve_panels as _rp
    df11 = {"chr": ["chr1"], "x": [50], "y": [1]}
    h7 = pt.chart(df11, aes(x="x", y="y"), data_width=240, data_height=100)
    h7.sectors({"chr1": 100, "chr2": 200}, axis="x", column="chr",
               divider=True, label=True)
    h7.add_line()
    df12 = {"chr": ["chr2"], "x": [10], "y": [1]}
    top7 = pt.chart(df12, aes(x="x", y="y"), data_height=30)
    top7.add_line()
    h7.attach_above(top7)
    root7 = hydrate(pt.to_ir(h7))
    materialize(root7)
    (r_h7,) = root7._children
    r_top7 = r_h7._attached_above[0]
    _, states7 = _rp(root7)
    st_top = states7[id(r_top7)]
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
    h8_mat = [[1, 2], [2, 3], [3, 4], [4, 5]]
    h8_df = {"col": cols7}
    for name, values in zip(rows7, h8_mat):
        h8_df[name] = values
    h8.add_heatmap(data=h8_df, mapping=aes(x="col"), values=rows7)
    df13 = {"x": [1, 2, 1, 2], "y": rows7}
    left8 = pt.chart(df13, aes(x="x", y="y"), data_width=20)
    left8.yscale("category", order=rows7, padding=0)
    left8.add_line()
    h8.attach_left(left8)
    root8 = hydrate(pt.to_ir(h8))
    materialize(root8)
    (r_h8,) = root8._children
    r_left8 = r_h8._attached_left[0]
    _, states8 = _rp(root8)
    _check(states8[id(r_left8)]["y_sectors"] is not None,
           "left attachment inherits host's y_sectors (categorical)")

    # Explicit attachment-side sectors call wins over inheritance.
    df14 = {"chr": ["chr1"], "x": [50], "y": [1]}
    h9 = pt.chart(df14, aes(x="x", y="y"), data_width=240, data_height=100)
    h9.sectors({"chr1": 100}, axis="x", column="chr", divider=True, label=True)
    h9.add_line()
    df15 = {"chr": ["chr1"], "x": [50], "y": [1]}
    top9 = pt.chart(df15, aes(x="x", y="y"), data_height=30)
    top9.sectors({"chr1": 100}, axis="x", column="chr",
                 divider=True, label=True)
    top9.add_line()
    h9.attach_above(top9)
    root9 = hydrate(pt.to_ir(h9))
    materialize(root9)
    (r_h9,) = root9._children
    r_top9 = r_h9._attached_above[0]
    _, states9 = _rp(root9)
    _check(states9[id(r_top9)]["x_sectors"] is not None
           and states9[id(r_top9)]["x_sectors"].divider is True,
           "explicit c.sectors() on attachment overrides inheritance")

    # Non-mutation: attachment sector inheritance now emits a cascade
    # entry at the call site in `_resolve_panels` instead of mutating
    # `top7._calls`. Re-running the pre-pass must not touch the leaf
    # journal (idempotence is automatic, but pin the no-mutation
    # property explicitly so a regression resurrecting an insert(0)
    # path would surface here).
    snapshot = list(r_top7._calls)
    _rp(root7)  # second pass
    _check(r_top7._calls == snapshot,
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
def test_layout_attachments_baseline(name, fn, baseline_compare):
    baseline_compare("layout_attachments", name, fn().to_svg())


def test_attachments_invariants():
    """Wraps the existing `_run_invariants` print-based runner so its
    behavioral checks (size lock, share warning, data-area alignment)
    run under pytest. A non-zero return surfaces as a single failure
    with the count of failed invariants; individual failures get
    printed to captured stdout."""
    failed = _run_invariants()
    assert failed == 0, f"{failed} attachment invariant(s) failed (see captured stdout)"


def test_attach_above_promotes_subtitle():
    def build(**chart_kw):
        df = {"x": [1, 2, 3], "y": [1, 2, 3]}

        host = pt.chart(df, aes(x="x", y="y"), **chart_kw)
        host.add_scatter()
        df2 = {"x": [1, 2, 3], "y": [1, 2, 1]}
        top = pt.chart(df2, aes(x="x", y="y"), data_height=30)
        top.add_line()
        host.attach_above(top)
        return host.regions()

    def named(regions, name):
        return [r for r in regions if r["name"] == name]

    def panels_top(regions):
        return min(r["bbox"][1] for r in named(regions, "panel"))

    # title + subtitle promote together above the attached panel
    regions = build(title="Tmain", subtitle="Ssub")
    (sub,) = named(regions, "subtitle")      # promoted, not drawn twice
    (title,) = named(regions, "title")
    assert sub["bbox"][1] < panels_top(regions)
    assert title["bbox"][1] < sub["bbox"][1]
    # a subtitle-only host promotes too
    regions = build(subtitle="Ssub")
    (sub,) = named(regions, "subtitle")
    assert sub["bbox"][1] < panels_top(regions)
