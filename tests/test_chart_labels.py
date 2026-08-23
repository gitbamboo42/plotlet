"""Baseline SVG regression tests for the labels artist/topic.

    pytest tests/test_chart_labels.py
    pytest tests/test_chart_labels.py --update
"""
from __future__ import annotations

import datetime
import math
import random

import plotlet as pt
from plotlet import aes
import pytest
from _chart_helpers import _xs


def chart_long_title():
    # Title text wider than the data region: measure-driven margin grows
    # left and right so the centered title doesn't spill off-canvas.
    # data_width=180 is small; title is ~360 px wide → ~90 px overhang each side.
    df = {"x": [1, 2, 3, 4, 5], "y": [1, 2, 4, 8, 16]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=180, data_height=140,
                 title="A very wide title that exceeds the data region width",
                 xlabel="x", ylabel="y")
    c.add_line()
    return c


def chart_long_ylabel():
    # ylabel rendered rotated -90 around the data area's vertical center;
    # text longer than data_height spills past top and bottom. Margin
    # should grow on top *and* bottom by half the overhang. Title is
    # included so we can verify the vertical overhang doesn't displace
    # the title from its natural slot above the data area.
    df = {"x": [0, 1, 2, 3], "y": [3.2, 4.1, 4.9, 5.5]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=200, data_height=120,
                 title="long ylabel + title",
                 ylabel="Signal intensity (log10 normalized units per sample)",
                 xlabel="time")
    c.add_line()
    return c


def chart_subtitle_caption():
    # Subtitle stacks under the title (smaller); caption is the
    # outermost bottom element, right-aligned.
    df = {"x": [1.8, 2.0, 2.8, 3.1, 4.2, 5.3],
          "y": [29, 31, 26, 27, 23, 20]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=340, data_height=170,
                 title="Fuel efficiency", subtitle="highway, 1999-2008",
                 caption="Source: EPA", xlabel="displ", ylabel="hwy")
    c.add_scatter()
    return c


def chart_multiline_labels():
    """`\\n` in title / xlabel / ylabel — each extra line adds one
    `line_height` to the label's block, margins grow to fit, and every
    line is anchored (centered) independently."""
    xs = _xs()
    df = {"t": xs, "sin": [math.sin(x) for x in xs]}

    c = pt.chart(df, aes(x="t", y="sin"), title="two-line title:\nsecond line",
                 xlabel="time\n(seconds)", ylabel="amplitude\n(unitless)",
                 gridlines=True)
    c.add_line()
    return c


def chart_multiline_ticks():
    """`\\n` in tick, sector, and legend labels. Unlike title / xlabel,
    these anchor off a single line's cap or baseline, so each one needs
    its own room for the extra lines: x names hang below the band, y
    names center on their tick, legend rows space to the tallest key."""
    df = {"x": [1, 2, 3, 4], "y": [2, 4, 3, 5], "z": [1, 3, 2, 4]}

    c = pt.chart(df, aes(x="x", y="y"), data_width=260, data_height=160)
    c.add_line(label="north\nregion")
    c.add_line(y="z", label="south\nregion")
    c.xticks([1, 2, 3, 4], labels=["Q1\n2023", "Q2\n2023", "Q3\n2023", "Q4\n2023"])
    c.yticks([2, 3, 4], labels=["low\n(<2)", "mid\n(2-4)", "high\n(>4)"])
    return c


PLOTS = {
    "long_title": chart_long_title,
    "long_ylabel": chart_long_ylabel,
    "subtitle_caption": chart_subtitle_caption,
    "multiline_labels": chart_multiline_labels,
    "multiline_ticks": chart_multiline_ticks,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_labels_baseline(name, fn, baseline_compare):
    baseline_compare("chart_labels", name, fn().to_svg())


def test_multiline_label_geometry():
    """`\\n` in title / xlabel / ylabel grows the figure by exactly one
    `line_height` per extra line on the matching side, and the recorded
    text-block regions are one `line_height` taller / wider."""
    from plotlet.draw import line_height, measure_text, text_block_height
    from plotlet._spec import _FONTSPEC
    from plotlet.render import natural_size

    # measure_text on multi-line = widest line; block height adds one
    # line_height per extra line on top of the bare size.
    assert measure_text("ab\nabcdef", 14) == measure_text("abcdef", 14)
    assert text_block_height("ab", 14) == 14
    assert text_block_height("ab\ncd\nef", 14) == 14 + 2 * line_height(14)

    def cell(title, xlabel, ylabel):
        df = {"x": [0, 1, 2], "y": [1, 0, 2]}

        c = pt.chart(df, aes(x="x", y="y"), title=title, xlabel=xlabel, ylabel=ylabel,
                     data_width=200, data_height=140)
        c.add_line()
        return c

    W0, H0 = natural_size(pt.to_ir(cell("t", "x", "y")))
    W1, H1 = natural_size(pt.to_ir(cell("t\nt2", "x\nx2", "y\ny2")))
    lh_title = line_height(_FONTSPEC["title_size"])
    lh_label = line_height(_FONTSPEC["label_size"])
    assert abs((H1 - H0) - (lh_title + lh_label)) <= 1   # title + xlabel lines
    assert abs((W1 - W0) - lh_label) <= 1                # ylabel line

    two = cell("t\nt2", "x\nx2", "y\ny2")
    two.to_svg()
    regs = {r["name"]: r for r in two.regions() if r["name"] in
            ("title", "xlabel", "ylabel", "panel")}
    one = cell("t", "x", "y")
    one.to_svg()
    regs1 = {r["name"]: r for r in one.regions() if r["name"] in
             ("title", "xlabel", "ylabel")}
    assert abs(regs["title"]["bbox"][3] - (regs1["title"]["bbox"][3] + lh_title)) < 0.01
    assert abs(regs["xlabel"]["bbox"][3] - (regs1["xlabel"]["bbox"][3] + lh_label)) < 0.01
    # ylabel is rotated 90° — the extra line grows its screen WIDTH.
    assert abs(regs["ylabel"]["bbox"][2] - (regs1["ylabel"]["bbox"][2] + lh_label)) < 0.01

    # No label block may bleed into the panel.
    px, py, pw, ph = regs["panel"]["bbox"]
    tx, ty, tw, th = regs["title"]["bbox"]
    assert ty + th <= py
    xx, xy, xw, xh = regs["xlabel"]["bbox"]
    assert xy >= py + ph
    yx, yy, yw, yh = regs["ylabel"]["bbox"]
    assert yx + yw <= px

def test_multiline_tick_labels_fit():
    """Tick, sector, and legend labels reserve room for their extra
    lines. Each anchors off one line (cap or baseline) rather than a
    whole block, so `text_block_height` alone doesn't cover them — the
    reservation and the anchor have to move together, on every side."""
    df = {"x": [1, 2, 3, 4], "y": [2, 4, 3, 5]}

    def clips(c):
        c.to_svg()
        return [w for w in pt.lint(c) if w.check == "edge_clip"]

    # x ticks, both sides and rotated — top-side labels are anchored on
    # their last line, so the extra lines have to lift the first one.
    for kw in ({}, {"side": "top"}, {"rotation": 45}, {"rotation": 90}):
        c = pt.chart(df, aes(x="x", y="y"), data_width=300, data_height=130)
        c.add_line()
        c.xticks([1, 2, 3, 4], labels=["one", "two\nB", "three", "four"], **kw)
        assert clips(c) == [], f"x ticks {kw}: {clips(c)}"

    for kw in ({}, {"side": "right"}):
        c = pt.chart(df, aes(x="x", y="y"), data_width=300, data_height=200)
        c.add_line()
        c.yticks([2, 3, 4, 5], labels=["a\nA\nAA", "b\nB\nBB", "c\nC\nCC", "d\nD\nDD"], **kw)
        assert clips(c) == [], f"y ticks {kw}: {clips(c)}"

    # Sector names take the same band as x tick labels.
    d = {"x": [1, 2, 3, 4], "y": [2, 4, 3, 5], "s": ["sec\nP"] * 2 + ["sec\nQ"] * 2}
    c = pt.chart(d, aes(x="x", y="y"), data_width=300, data_height=200)
    c.add_line()
    c.sectors({"sec\nP": 2, "sec\nQ": 2}, column="s")
    assert clips(c) == []

    # Legend rows space to the tallest key instead of the spec pitch,
    # so two-line entries can't overprint each other.
    d2 = {"x": [1, 2, 3], "y": [1, 2, 3], "z": [2, 3, 4]}
    c = pt.chart(d2, aes(x="x", y="y"), data_width=280, data_height=180)
    c.add_line(label="north\nregion")
    c.add_line(y="z", label="south\nregion")
    c.to_svg()
    assert [w for w in pt.lint(c) if w.check == "overlap"] == []


def test_multiline_y_tick_centers_on_its_tick():
    """A multi-line y tick label centers its whole block on the tick,
    not just its first line — otherwise the tick appears to point at
    the top line of a three-line label."""
    df = {"x": [1, 2, 3, 4], "y": [2, 4, 3, 5]}

    def block_centers(labels):
        c = pt.chart(df, aes(x="x", y="y"), data_width=300, data_height=200)
        c.add_line()
        c.yticks([2, 3, 4, 5], labels=labels)
        c.to_svg()
        panel = next(r for r in c.regions()
                     if r["kind"] == "rect" and r["name"] == "panel")
        return sorted(r["bbox"][1] + r["bbox"][3] / 2 - panel["bbox"][1]
                      for r in c.regions()
                      if r["kind"] == "text" and r["name"] == "tick-y")

    one = block_centers(["a", "b", "c", "d"])
    three = block_centers(["a\nA\nAA", "b\nB\nBB", "c\nC\nCC", "d\nD\nDD"])
    for a, b in zip(one, three):
        assert abs(a - b) < 0.01


def test_single_line_label_metrics_unchanged():
    """The multi-line terms are additive and vanish for single-line
    text — the guard that keeps every existing baseline byte-identical."""
    from plotlet.draw import (cap_height, descender, extra_line_extent,
                              line_height, tick_band_height)

    assert extra_line_extent("plain", 13) == 0.0
    assert extra_line_extent("two\nlines", 13) == line_height(13)
    assert extra_line_extent(42, 13) == 0.0            # non-str labels

    plain = ["one", "two", "three"]
    assert (tick_band_height(plain, 13, 0)
            == cap_height(13) + descender(13))
    assert (tick_band_height(["one", "two\nB"], 13, 0)
            == tick_band_height(plain, 13, 0) + line_height(13))
