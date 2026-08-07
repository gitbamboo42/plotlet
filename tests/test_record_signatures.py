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
from plotlet import aes


def test_typo_kwarg_raises_at_render():
    df = {"x": ["a", "b"], "y": [1.0, 2.0]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_bar(widht=0.5)
    with pytest.raises(TypeError, match="widht"):
        c.to_svg()


def test_typo_kwarg_raises_for_fanout_artist():
    df = {"x": [1.0, 2.0], "y": [3.0, 4.0]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line(width=1.5)
    with pytest.raises(TypeError, match="width"):
        c.to_svg()


def test_positional_table_still_hoists():
    # `c.add_bar(df, x=, y=)` sugar: replay moves the single positional
    # table into data= before the record function runs.
    df = {"x": ["a", "b"], "y": [1.0, 2.0]}

    c = pt.chart()
    c.add_bar(df, aes(x="x", y="y"))
    assert c.to_svg()


def test_data_input_declarations_match_signatures():
    # `ArtistSpec.data_input` states what data the artist reads; the
    # record signature is the ground truth. Table readers must have a
    # `data` parameter; "none" artists must not — a mismatch means the
    # declaration lies about the artist. ("matrix" is unchecked: the
    # bare matrix binds to whatever the record fn names its first
    # parameter — image_cmap's `matrix`, dendrogram's `data`.)
    from plotlet.registry import _REGISTRY
    for name, spec in _REGISTRY.items():
        if spec.record.__kwarg_names__ is None:
            continue    # **kw record (step, demo artists) — unknowable here
        has_data = "data" in spec.record.__kwarg_names__
        if spec.data_input == "table":
            assert has_data, f"{name}: data_input={spec.data_input!r} " \
                             f"but record() has no data parameter"
        elif spec.data_input == "none":
            assert not has_data, f"{name}: data_input={spec.data_input!r} " \
                                 f"but record() takes data="


def test_chart_level_aes_skips_artists_without_that_parameter():
    # group= is a line/scatter aes; bar has no group parameter — the
    # recorder must skip injecting it instead of crashing bar's record.
    df = {"x": ["a", "b"], "y": [1.0, 2.0], "g": ["u", "v"]}

    c = pt.chart(df, aes(x="x", y="y", group="g"))
    c.add_bar()
    assert c.to_svg()


def _cat(add):
    df = {"x": ["a", "a", "b", "b"], "y": [1.0, 2.0, 3.0, 4.0]}
    c = pt.chart(df, aes(x="x", y="y"))
    add(c)
    return c


def _num(add):
    df = {"v": [1.0, 2.0, 2.0, 3.0]}
    c = pt.chart(df, aes(x="v"))
    add(c)
    return c


def _xy(add):
    df = {"x": [1.0, 10.0, 100.0], "y": [1.0, 2.0, 3.0]}
    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line()
    add(c)
    return c


# Every enum-valued kwarg with a fixed vocabulary: a wrong value must
# raise loudly (via `utils.check_option`), never silently behave like
# the default.
ENUM_CASES = [
    ("bar-orientation",
     lambda v: _cat(lambda c: c.add_bar(orientation=v)), "horizontal", "h"),
    ("hist-orientation",
     lambda v: _num(lambda c: c.add_hist(orientation=v)), "horizontal", "h"),
    ("boxplot-orientation",
     lambda v: _cat(lambda c: c.add_boxplot(orientation=v)), "horizontal", "h"),
    ("violin-orientation",
     lambda v: _cat(lambda c: c.add_violin(orientation=v)), "horizontal", "h"),
    ("strip-orientation",
     lambda v: _cat(lambda c: c.add_strip(orientation=v)), "horizontal", "h"),
    ("swarm-orientation",
     lambda v: _cat(lambda c: c.add_swarm(orientation=v)), "horizontal", "h"),
    ("rug-orientation",
     lambda v: _num(lambda c: c.add_rug(orientation=v)), "horizontal", "y"),
    ("violin-inner",
     lambda v: _cat(lambda c: c.add_violin(inner=v)), "quartiles", "quartile"),
    ("pointplot-estimator",
     lambda v: _cat(lambda c: c.add_pointplot(estimator=v)), "avg", "median"),
    ("image_cmap-origin",
     lambda v: _bare(lambda c: c.add_image_cmap([[1.0, 2.0], [3.0, 4.0]],
                                                origin=v)), "top", "upper"),
    ("image_rgba-origin",
     lambda v: _bare(lambda c: c.add_image_rgba([[[0, 0, 0], [255, 0, 0]]],
                                                origin=v)), "top", "lower"),
    ("text-ha",
     lambda v: _bare(lambda c: c.add_text(
         data={"x": [1.0], "y": [1.0], "s": ["A"]},
         mapping=aes(x="x", y="y", label="s"), ha=v)), "middle", "center"),
    ("annotate-va",
     lambda v: _bare(lambda c: c.add_annotate("hi", xy=(1, 1), va=v)),
     "middle", "center"),
    ("qq-dist",
     lambda v: _bare(lambda c: c.add_qq(
         data={"v": [1.0, 2.0, 3.0]}, mapping=aes(sample="v"), dist=v)),
     "gaussian", "normal"),
    ("xscale-kind",
     lambda v: _xy(lambda c: c.xscale(v)), "logarithmic", "log"),
    ("xticks-direction",
     lambda v: _xy(lambda c: c.xticks(direction=v)), "outside", "out"),
    # linestyle's vocabulary is open (raw dasharrays pass), but a value
    # that is neither a registered code nor number-shaped must still
    # raise — browsers ignore a bad stroke-dasharray, silently
    # rendering solid.
    ("line-linestyle",
     lambda v: _bare(lambda c: c.add_line(
         data={"x": [0.5, 1.5], "y": [0.5, 1.5]},
         mapping=aes(x="x", y="y"), linestyle=v)), "dahsed", "dashed"),
]


def _bare(add):
    c = pt.chart(xlim=(0, 2), ylim=(0, 2))
    add(c)
    return c


@pytest.mark.parametrize("name,build,bad,good", ENUM_CASES,
                         ids=[c[0] for c in ENUM_CASES])
def test_enum_kwargs_reject_unknown_values(name, build, bad, good):
    with pytest.raises(ValueError, match=repr(bad)):
        build(bad).to_svg()
    assert build(good).to_svg()


def test_chart_aes_column_in_fixed_value_kwarg_raises():
    # In aes(), a value is a column name. hist can't vary color= by a
    # column (it groups via fill=), so a chart-level aes(color=) used
    # to slip through as the bare column name (stroke="status" in the
    # SVG) with no error.
    df = {"v": [1.0, 2.0, 2.0, 3.0], "status": ["a", "a", "b", "b"]}

    c = pt.chart(df, aes(x="v", color="status"))
    c.add_hist()
    with pytest.raises(ValueError, match="aes\\(color='status'\\)"):
        c.to_svg()


def test_call_aes_column_in_fixed_value_kwarg_raises():
    df = {"v": [1.0, 2.0, 2.0, 3.0], "status": ["a", "a", "b", "b"]}

    c = pt.chart(df)
    c.add_hist(aes(x="v", color="status"))
    with pytest.raises(ValueError, match="aes\\(color='status'\\)"):
        c.to_svg()


def test_aes_column_where_artist_supports_it_still_works():
    # The check must not break the supported routes: hist groups via
    # fill=, scatter and line color by column.
    df = {"v": [1.0, 2.0, 2.0, 3.0], "status": ["a", "a", "b", "b"]}

    c = pt.chart(df, aes(x="v", fill="status"))
    c.add_hist()
    assert c.to_svg()

    df2 = {"x": [1.0, 2.0], "y": [3.0, 4.0], "g": ["u", "v"]}
    c = pt.chart(df2, aes(x="x", y="y", color="g"))
    c.add_scatter()
    c.add_line()
    assert c.to_svg()


def test_recorder_exposes_real_signature():
    # `c.add_bar?` / help(c.add_bar) reach the record function's parameter list.
    params = inspect.signature(pt.chart().add_bar).parameters
    assert "fill" in params and "orientation" in params


def _text_svg(**style):
    df = {"x": [1.0], "y": [1.0], "s": ["Ag"]}

    c = pt.chart(xlim=(0, 2), ylim=(0, 2))
    c.add_text(data=df, mapping=aes(x="x", y="y", label="s"), **style)
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

    opaque = pt.chart(df, aes(x="x", y="y", color="z")); opaque.add_scatter()
    faded = pt.chart(df, aes(x="x", y="y", color="z")); faded.add_scatter(alpha=0.3)
    assert opaque.to_svg() != faded.to_svg()


# ---------------------------------------------------------------------------
# Ragged tables — rejected at the recording boundary, before anything
# zip-truncates rows or the SVG data attrs misreport the row count.
# ---------------------------------------------------------------------------


def test_linestyle_raw_dasharray_and_hint():
    def line(ls):
        return _bare(lambda c: c.add_line(
            data={"x": [0.5, 1.5], "y": [0.5, 1.5]},
            mapping=aes(x="x", y="y"), linestyle=ls))
    # Raw SVG dasharrays stay accepted — the vocabulary is open.
    assert 'stroke-dasharray="6,3,1,3"' in line("6,3,1,3").to_svg()
    # A near-miss typo gets a did-you-mean hint.
    with pytest.raises(ValueError, match="Did you mean 'dashed'"):
        line("dahsed").to_svg()


def test_ragged_chart_data_raises_at_chart():
    with pytest.raises(ValueError, match="x has 3, y has 2"):
        pt.chart({"x": [1, 2, 3], "y": [2.0, 3.0]}, aes(x="x", y="y"))


def test_ragged_artist_data_raises_at_call():
    c = pt.chart()
    with pytest.raises(ValueError, match=r"add_line\(data=\)"):
        c.add_line(data={"x": [1, 2], "y": [1.0]}, mapping=aes(x="x", y="y"))


def test_ragged_positional_table_raises_at_call():
    c = pt.chart()
    with pytest.raises(ValueError, match="same number of values"):
        c.add_scatter({"x": [1, 2], "y": [1.0]}, aes(x="x", y="y"))


def test_ragged_facet_data_raises_at_facet():
    with pytest.raises(ValueError, match=r"pt\.facet\(data=\)"):
        pt.facet({"x": [1, 2], "g": ["a"]}, by="g")
