"""Record signatures are each artist's kwarg vocabulary.

Every record function declares its parameters explicitly, so Python
itself rejects unknown names at replay — no per-artist validation code.
These tests pin the behaviors that the signature style is responsible
for: typo rejection, the positional-table sugar, aes-injection
filtering, and runtime introspection.
"""
import inspect

import pytest

import plotlet as pt


def test_typo_kwarg_raises_at_render():
    c = pt.chart()
    c.add_bar(data={"x": ["a", "b"], "y": [1.0, 2.0]}, x="x", y="y", widht=0.5)
    with pytest.raises(TypeError, match="widht"):
        c.to_svg()


def test_typo_kwarg_raises_for_fanout_artist():
    c = pt.chart()
    c.add_line(data={"x": [1.0, 2.0], "y": [3.0, 4.0]}, x="x", y="y", width=1.5)
    with pytest.raises(TypeError, match="width"):
        c.to_svg()


def test_positional_table_still_hoists():
    # `c.add_bar(df, x=, y=)` sugar: replay moves the single positional
    # table into data= before the record function runs.
    c = pt.chart()
    c.add_bar({"x": ["a", "b"], "y": [1.0, 2.0]}, x="x", y="y")
    assert c.to_svg()


def test_chart_level_aes_skips_artists_without_that_parameter():
    # group= is a line/scatter aes; bar has no group parameter — the
    # recorder must skip injecting it instead of crashing bar's record.
    df = {"x": ["a", "b"], "y": [1.0, 2.0], "g": ["u", "v"]}
    c = pt.chart(df, x="x", y="y", group="g")
    c.add_bar()
    assert c.to_svg()


def test_recorder_exposes_real_signature():
    # `c.add_bar?` / help(c.add_bar) reach the record function's parameter list.
    params = inspect.signature(pt.chart().add_bar).parameters
    assert "fill" in params and "orientation" in params


def _text_svg(**style):
    c = pt.chart(xlim=(0, 2), ylim=(0, 2))
    c.add_text(data={"x": [1.0], "y": [1.0], "s": ["Ag"]}, x="x", y="y",
           label="s", **style)
    return c.to_svg()


def test_text_fontstyle_fontweight_reach_the_glyphs():
    # Regression guard: these ride in opts and must be threaded to
    # text_path (they were silently dropped before the signature sweep).
    plain = _text_svg()
    assert _text_svg(fontstyle="italic") != plain
    assert _text_svg(fontweight="bold") != plain
    assert _text_svg(decoration="underline") != plain


def test_scatter_alpha_applies_on_colormap_path():
    # A scalar alpha= was dropped when color= was a numeric column (the
    # cmap path); it must dim the points the same as on the literal path.
    df = {"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 2.0], "z": [0.1, 0.5, 0.9]}
    opaque = pt.chart(); opaque.add_scatter(data=df, x="x", y="y", color="z")
    faded = pt.chart(); faded.add_scatter(data=df, x="x", y="y", color="z", alpha=0.3)
    assert opaque.to_svg() != faded.to_svg()
