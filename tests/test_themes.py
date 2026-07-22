#!/usr/bin/env python3
"""Baseline SVG regression tests for the built-in themes.

Each demo renders one representative chart under each shipped theme
(`classic`, `dark`, `minimal`, `void`) so future theme tweaks are
diff-visible. Mixed-theme layouts are exercised under `mixed`.

    python tests/test_themes.py            # check vs. baselines
    python tests/test_themes.py --update   # regenerate baselines
    python tests/test_themes.py --gallery  # write index.html
"""
from __future__ import annotations

import math
import sys

import plotlet as pt
from plotlet import aes



def _xs():
    return [i * 0.1 for i in range(64)]


def _demo(theme: str) -> pt.Chart:
    xs = _xs()
    df = {"x": xs, "y": [math.sin(x) for x in xs]}

    c = pt.chart(theme=theme, title=f"theme: {theme}",
                 xlabel="t", ylabel="value", legend=True)
    c.add_line(df, aes(x="x", y="y"), label="sin(t)")
    df2 = {"x": xs, "y": [math.cos(x) for x in xs]}
    c.add_line(df2, aes(x="x", y="y"), label="cos(t)", linestyle="--")
    return c


def theme_classic(): return _demo("classic")
def theme_dark():    return _demo("dark")
def theme_minimal(): return _demo("minimal")
def theme_void():    return _demo("void")


def theme_mixed_layout():
    """Two leaves with different themes side-by-side. Confirms per-leaf
    `active_theme()` scoping works in the layout renderer."""
    xs = _xs()
    df = {"x": xs, "y": [math.sin(x) for x in xs]}

    left = pt.chart(df, aes(x="x", y="y"), theme="minimal", title="minimal", xlabel="t", ylabel="sin")
    left.add_line()
    df2 = {"x": xs, "y": [math.cos(x) for x in xs]}

    right = pt.chart(df2, aes(x="x", y="y"), theme="dark", title="dark", xlabel="t", ylabel="cos")
    right.add_line()
    return left | right


def theme_dark_scatter():
    """Dark theme on a different chart type — confirms theme propagates
    to non-line artists (refspans here)."""
    import random
    rng = random.Random(0)
    xs = [rng.gauss(0, 1) for _ in range(80)]
    ys = [rng.gauss(0, 1) for _ in range(80)]
    df = {"x": xs, "y": ys}

    c = pt.chart(df, aes(x="x", y="y"), theme="dark", title="dark scatter",
                 xlabel="x", ylabel="y")
    c.add_scatter()
    c.add_axhline(0)  # picks up refline_color from theme
    c.add_axvline(0)
    return c


def theme_classic_after_dark():
    """Re-rendering a classic chart after a dark one should not bleed
    state. Sanity check for the swap-and-restore mechanism."""
    df = {"x": [1, 2, 3], "y": [1, 2, 3]}
    pt.chart(df, aes(x="x", y="y"), theme="dark").add_line().to_svg()
    return pt.chart(df, aes(x="x", y="y"), title="back to classic").add_line()


PLOTS = {
    "classic":             theme_classic,
    "dark":                theme_dark,
    "minimal":             theme_minimal,
    "void":                theme_void,
    "mixed_layout":        theme_mixed_layout,
    "dark_scatter":        theme_dark_scatter,
    "classic_after_dark":  theme_classic_after_dark,
}


import pytest

@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_themes_baseline(name, fn, baseline_compare):
    baseline_compare("themes", name, fn().to_svg())
