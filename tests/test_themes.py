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



def _xs():
    return [i * 0.1 for i in range(64)]


def _demo(theme: str) -> pt.Chart:
    xs = _xs()
    c = pt.chart(theme=theme, title=f"theme: {theme}",
                 xlabel="t", ylabel="value", legend=True)
    c.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y", label="sin(t)")
    c.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y", label="cos(t)", linestyle="--")
    return c


def theme_classic(): return _demo("classic")
def theme_dark():    return _demo("dark")
def theme_minimal(): return _demo("minimal")
def theme_void():    return _demo("void")


def theme_mixed_layout():
    """Two leaves with different themes side-by-side. Confirms per-leaf
    `active_theme()` scoping works in the layout renderer."""
    xs = _xs()
    left = pt.chart(theme="minimal", title="minimal", xlabel="t", ylabel="sin")
    left.line(data={"x": xs, "y": [math.sin(x) for x in xs]}, x="x", y="y")
    right = pt.chart(theme="dark", title="dark", xlabel="t", ylabel="cos")
    right.line(data={"x": xs, "y": [math.cos(x) for x in xs]}, x="x", y="y")
    return left | right


def theme_dark_scatter():
    """Dark theme on a different chart type — confirms theme propagates
    to non-line artists (refspans here)."""
    import random
    rng = random.Random(0)
    xs = [rng.gauss(0, 1) for _ in range(80)]
    ys = [rng.gauss(0, 1) for _ in range(80)]
    c = pt.chart(theme="dark", title="dark scatter",
                 xlabel="x", ylabel="y")
    c.scatter(data={"x": xs, "y": ys}, x="x", y="y")
    c.axhline(0)  # picks up refline_color from theme
    c.axvline(0)
    return c


def theme_classic_after_dark():
    """Re-rendering a classic chart after a dark one should not bleed
    state. Sanity check for the swap-and-restore mechanism."""
    df = {"x": [1, 2, 3], "y": [1, 2, 3]}
    pt.chart(theme="dark").line(data=df, x="x", y="y").to_svg()
    return pt.chart(title="back to classic").line(data=df, x="x", y="y")


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
