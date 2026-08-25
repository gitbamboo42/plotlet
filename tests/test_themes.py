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

    c = pt.chart(title=f"theme: {theme}",
                 xlabel="t", ylabel="value", legend=True)
    c.theme(theme)
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

    left = pt.chart(df, aes(x="x", y="y"), title="minimal", xlabel="t", ylabel="sin")
    left.theme("minimal")
    left.add_line()
    df2 = {"x": xs, "y": [math.cos(x) for x in xs]}

    right = pt.chart(df2, aes(x="x", y="y"), title="dark", xlabel="t", ylabel="cos")
    right.theme("dark")
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

    c = pt.chart(df, aes(x="x", y="y"), title="dark scatter",
                 xlabel="x", ylabel="y")
    c.theme("dark")
    c.add_scatter()
    c.add_axhline(0)  # picks up refline_color from theme
    c.add_axvline(0)
    return c


def theme_inline_overrides():
    """`c.spec(...)` on top of a `c.theme(...)` preset — per-chart spec
    overrides, no registration. Bigger title, custom grid."""
    xs = _xs()
    df = {"x": xs, "y": [math.sin(x) for x in xs]}

    c = pt.chart(df, aes(x="x", y="y"), title="dark + overrides",
                 xlabel="t", ylabel="value")
    c.theme("dark")
    c.spec(font=dict(title_size=20), grid=dict(color="#556677", default_on=True))
    c.add_line()
    return c


def theme_layout_broadcast():
    """`layout.theme(...)` — figure-level default: un-themed leaves and
    the outer canvas (background, figure title) go dark; the leaf with
    its own theme keeps it."""
    xs = _xs()
    df = {"x": xs, "y": [math.sin(x) for x in xs]}
    df2 = {"x": xs, "y": [math.cos(x) for x in xs]}

    a = pt.chart(df, aes(x="x", y="y"), title="inherits dark",
                 xlabel="t", ylabel="sin")
    a.add_line()
    b = pt.chart(df2, aes(x="x", y="y"), title="own minimal",
                 xlabel="t", ylabel="cos")
    b.theme("minimal")
    b.add_line()

    fig = a | b
    fig.theme("dark")
    fig.title("layout.theme('dark')")
    return fig


def theme_classic_after_dark():
    """Re-rendering a classic chart after a dark one should not bleed
    state. Sanity check for the swap-and-restore mechanism."""
    df = {"x": [1, 2, 3], "y": [1, 2, 3]}

    d = pt.chart(df, aes(x="x", y="y"))
    d.theme("dark")
    d.add_line()
    d.to_svg()

    c = pt.chart(df, aes(x="x", y="y"), title="back to classic")
    c.add_line()
    return c


PLOTS = {
    "classic":             theme_classic,
    "dark":                theme_dark,
    "minimal":             theme_minimal,
    "void":                theme_void,
    "mixed_layout":        theme_mixed_layout,
    "dark_scatter":        theme_dark_scatter,
    "inline_overrides":    theme_inline_overrides,
    "layout_broadcast":    theme_layout_broadcast,
    "classic_after_dark":  theme_classic_after_dark,
}


import pytest

@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_themes_baseline(name, fn, baseline_compare):
    baseline_compare("themes", name, fn().to_svg())


# ---------------------------------------------------------------------------
# spec() overrides — record-time validation and pipeline round-trips.
# ---------------------------------------------------------------------------

def _override_chart():
    df = {"x": [1, 2, 3], "y": [2, 4, 3]}
    c = pt.chart(df, aes(x="x", y="y"), title="t")
    c.theme("dark")
    c.spec(font=dict(title_size=24), grid=dict(color="#888888"))
    c.add_line()
    return c


def test_spec_change_output():
    df = {"x": [1, 2, 3], "y": [2, 4, 3]}
    plain = pt.chart(df, aes(x="x", y="y"), title="t")
    plain.theme("dark")
    plain.add_line()
    assert _override_chart().to_svg() != plain.to_svg()


def test_spec_without_theme_applies_over_classic():
    df = {"x": [1, 2, 3], "y": [2, 4, 3]}
    c = pt.chart(df, aes(x="x", y="y"), title="t")
    c.spec(figure=dict(background="#fafafa"))
    c.add_line()
    assert "#fafafa" in c.to_svg()


def test_spec_rejects_unknown_key():
    c = pt.chart()
    with pytest.raises(ValueError, match="title_size"):   # did-you-mean hint
        c.spec(font=dict(titlesize=15))
    with pytest.raises(ValueError, match="'font'"):
        c.spec(fonts=dict(title_size=15))
    with pytest.raises(TypeError, match="dict"):
        c.spec(font=15)
    with pytest.raises(TypeError, match="c.spec"):
        c.theme("dark", font=dict(title_size=15))
    with pytest.raises(TypeError, match="c.theme"):
        c.spec("dark")


def test_spec_round_trip_journal_and_ir():
    c = _override_chart()
    svg = c.to_svg()
    assert pt.from_journal(pt.to_journal(c)).to_svg() == svg
    resolved = pt.to_ir(c).resolve()
    assert resolved.to_svg() == svg
    panel = resolved.to_dict()["root"]["children"][0]
    assert panel["spec"] == {"font": {"title_size": 24},
                                       "grid": {"color": "#888888"}}


def test_spec_scope_per_leaf():
    """Sibling leaves keep their own overrides; nothing bleeds."""
    df = {"x": [1, 2, 3], "y": [2, 4, 3]}
    a = pt.chart(df, aes(x="x", y="y"), title="a")
    a.theme("minimal")
    a.spec(grid=dict(color="#ff0000", default_on=True))
    a.add_line()
    b = pt.chart(df, aes(x="x", y="y"), title="b")
    b.theme("minimal")
    b.add_line()
    fig = a | b
    joined = fig.to_svg()
    assert "#ff0000" in joined
    assert fig.to_svg() == joined  # deterministic re-render


# ---------------------------------------------------------------------------
# Layout-level theme — broadcast default, leaf wins, canvas chrome.
# ---------------------------------------------------------------------------

def _leaf(title, theme=None):
    df = {"x": [1, 2, 3], "y": [2, 4, 3]}
    c = pt.chart(df, aes(x="x", y="y"), title=title)
    if theme:
        c.theme(theme)
    c.add_line()
    return c


def test_layout_theme_broadcasts_to_untouched_leaves():
    fig = _leaf("a") | _leaf("b")
    fig.theme("dark")
    root = pt.to_ir(fig).resolve().to_dict()["root"]
    assert root["theme"] == "dark"
    assert [p["theme"] for p in root["children"]] == ["dark", "dark"]
    # canvas background follows the layout theme
    assert "#1f1f1f" in fig.to_svg()


def test_layout_theme_leaf_own_theme_wins():
    fig = _leaf("a") | _leaf("b", theme="minimal")
    fig.theme("dark")
    root = pt.to_ir(fig).resolve().to_dict()["root"]
    assert [p["theme"] for p in root["children"]] == ["dark", "minimal"]


def test_layout_theme_nested_nearest_ancestor_wins():
    inner = _leaf("c") | _leaf("d")
    inner.theme("minimal")
    outer = _leaf("a") / inner
    outer.theme("dark")
    root = pt.to_ir(outer).resolve().to_dict()["root"]
    a, inner_ir = root["children"]
    assert a["theme"] == "dark"
    assert [p["theme"] for p in inner_ir["children"]] == ["minimal", "minimal"]


def test_layout_spec():
    fig = _leaf("a") | _leaf("b")
    fig.theme("dark")
    fig.spec(figure=dict(background="#101020"))
    assert "#101020" in fig.to_svg()
    bad = _leaf("x") | _leaf("y")
    with pytest.raises(ValueError, match="'font'"):
        bad.spec(fonts=dict(title_size=1))


def test_layout_theme_round_trips():
    fig = _leaf("a") | _leaf("b", theme="minimal")
    fig.theme("dark")
    fig.title("f")
    svg = fig.to_svg()
    assert pt.from_journal(pt.to_journal(fig)).to_svg() == svg
    assert pt.to_ir(fig).resolve().to_svg() == svg


def test_theme_and_spec_are_order_independent():
    a = _leaf("t")
    a.theme("dark")
    a.spec(font=dict(title_size=24))
    b = _leaf("t")
    b.spec(font=dict(title_size=24))
    b.theme("dark")
    assert a.to_svg() == b.to_svg()


def test_spec_calls_accumulate():
    a = _leaf("t")
    a.spec(font=dict(title_size=24))
    a.spec(grid=dict(color="#888888", default_on=True))
    b = _leaf("t")
    b.spec(font=dict(title_size=24), grid=dict(color="#888888", default_on=True))
    assert a.to_svg() == b.to_svg()


def test_layout_preset_and_leaf_spec_compose():
    """A leaf that only tweaks spec values still inherits the layout
    preset — the channels cascade independently."""
    a = _leaf("a")
    a.spec(font=dict(title_size=24))
    fig = a | _leaf("b")
    fig.theme("dark")
    root = pt.to_ir(fig).resolve().to_dict()["root"]
    assert root["children"][0]["theme"] == "dark"
    assert root["children"][0]["spec"] == {"font": {"title_size": 24}}


def test_layout_and_leaf_spec_merge_leaf_wins():
    a = _leaf("a")
    a.spec(font=dict(title_size=24))
    fig = a | _leaf("b")
    fig.spec(font=dict(title_size=10), grid=dict(color="#ff0000", default_on=True))
    root = pt.to_ir(fig).resolve().to_dict()["root"]
    ov = root["children"][0]["spec"]
    assert ov["font"]["title_size"] == 24        # leaf wins per key
    assert ov["grid"]["color"] == "#ff0000"      # layout default fills in
