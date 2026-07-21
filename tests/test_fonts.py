#!/usr/bin/env python3
"""Font selection tests — `Font` loading + per-font metrics, the bundled
registry and aliases, the `.ttf`/`.otf` path escape hatch, spec scoping
(no cross-chart leaks), and baseline renders under Arimo.

Also documents, with measured numbers, why DejaVu Sans stays the default
(`test_scientific_symbol_coverage`): Arimo covers Greek and super/
subscripts but almost none of Mathematical Operators or Arrows.

    python -m pytest tests/test_fonts.py            # check vs. baselines
    python -m pytest tests/test_fonts.py --update   # regenerate baselines
"""
from __future__ import annotations

import math
import re
import unicodedata

import pytest

import plotlet as pt
from plotlet import aes
from plotlet._spec import _FONTSPEC, active_font
from plotlet.draw.font import (_FONT_DIR, _load_font, _resolve_face,
                               _resolve_font)


DEJAVU = str(_FONT_DIR / "DejaVuSans.ttf")
ARIMO = str(_FONT_DIR / "Arimo-Regular.ttf")


def _df():
    return {"x": [1, 2, 3], "y": [2, 1, 3]}


# ---------------------------------------------------------------------------
# Font object + registry
# ---------------------------------------------------------------------------

def test_load_font_cached_identity():
    assert _load_font(DEJAVU) is _load_font(DEJAVU)
    # Aliases resolve to the same file → the same cached object.
    assert _resolve_font("Arimo") is _resolve_font("helvetica")
    assert _resolve_font("Arimo") is _resolve_font("Arial")
    assert _resolve_font("sans") is _resolve_font("DejaVu Sans")


def test_dejavu_metrics_match_historical_constants():
    # These exact values were hardcoded before fonts became pluggable
    # (cap height 1493/2048 measured from the 'H' glyph, descender
    # 483/2048 from hhea). Per-font measurement must reproduce them
    # bit-for-bit or every existing baseline drifts.
    f = _load_font(DEJAVU)
    assert f.cap_ratio == 1493 / 2048
    assert f.descender_ratio == 483 / 2048


def test_metrics_differ_per_font():
    dj, ar = _load_font(DEJAVU), _load_font(ARIMO)
    assert dj.cap_ratio != ar.cap_ratio
    assert dj.descender_ratio != ar.descender_ratio
    # Arimo is metrically narrower than DejaVu for typical labels.
    from plotlet._spec import active_font
    from plotlet.draw.font import measure_text
    w_dejavu = measure_text("Hello 123", 13)
    with active_font("Arimo"):
        w_arimo = measure_text("Hello 123", 13)
    assert w_arimo != w_dejavu


def test_path_escape_hatch():
    # Any TTF on disk loads by path — including files that are bundled
    # but deliberately absent from the registry, like the Bold face.
    bold = str(_FONT_DIR / "DejaVuSans-Bold.ttf")
    f = _resolve_font(bold)
    assert f is _load_font(bold)
    assert f.family == "DejaVu Sans"       # name table, not the path
    assert f.cap_ratio > 0 and f.descender_ratio > 0


def test_unknown_font_is_loud():
    with pytest.raises(ValueError, match="unknown font"):
        _resolve_font("Comic Sans")
    with pytest.raises(ValueError, match="unknown font"):
        pt.chart(_df(), aes(x="x", y="y"), font="Comic Sans").add_line().to_svg()


def test_names_are_case_insensitive():
    assert _resolve_font("ARIMO") is _resolve_font("arimo")
    assert _resolve_font("DEJAVU SANS") is _resolve_font("DejaVu Sans")


# ---------------------------------------------------------------------------
# Variant faces — fontstyle / fontweight → real Bold/Italic files
# ---------------------------------------------------------------------------

def test_resolve_face_variants_are_distinct_files():
    for family in ("DejaVu Sans", "Arimo"):
        with active_font(family):
            faces = {key: _resolve_face(*key)[0] for key in
                     [("normal", "normal"), ("italic", "normal"),
                      ("normal", "bold"), ("italic", "bold")]}
        assert len({f.path for f in faces.values()}) == 4
        # Bundled families always resolve to a real drawn face — never
        # the synthetic skew.
        with active_font(family):
            for style in ("normal", "italic"):
                for weight in ("normal", "bold"):
                    assert _resolve_face(style, weight)[1] is False


def test_path_font_italic_is_synthetic_and_bold_is_loud():
    p = str(_FONT_DIR / "Arimo-Regular.ttf")
    with active_font(p):
        f, synthetic = _resolve_face("italic", "normal")
        assert synthetic is True
        assert f.path == p          # same file, skewed at render time
        with pytest.raises(ValueError, match="bold"):
            _resolve_face("normal", "bold")


def test_variant_values_are_validated():
    with pytest.raises(ValueError, match="fontweight"):
        _resolve_face("normal", "heavy")
    with pytest.raises(ValueError, match="fontstyle"):
        _resolve_face("oblique", "normal")


def test_bold_measures_wider():
    from plotlet.draw.font import measure_text
    s = "Hello 123"
    assert measure_text(s, 13, "normal", "bold") > measure_text(s, 13)
    with active_font("Arimo"):
        assert measure_text(s, 13, "normal", "bold") > measure_text(s, 13)


def test_bold_ticks_change_output():
    df = {"x": ["alpha", "beta"], "y": [1, 2]}
    plain = pt.chart(df, aes(x="x", y="y")).add_bar()
    bold = pt.chart(df, aes(x="x", y="y")).add_bar()
    bold.xticks(fontweight="bold")
    assert plain.to_svg() != bold.to_svg()


# ---------------------------------------------------------------------------
# Chart API + scoping
# ---------------------------------------------------------------------------

def test_font_kwarg_equals_method():
    a = pt.chart(_df(), aes(x="x", y="y"), font="Arimo").add_line().to_svg()
    c = pt.chart(_df(), aes(x="x", y="y"))
    c.font("Arimo")
    assert c.add_line().to_svg() == a


def test_alias_renders_same_glyphs():
    # "Helvetica" maps to the Arimo file: identical output except the
    # root font-family attr, which carries the user's name verbatim.
    strip = lambda s: re.sub(r'font-family="[^"]*"', "", s)
    a = pt.chart(_df(), aes(x="x", y="y"), font="Arimo").add_line().to_svg()
    h = pt.chart(_df(), aes(x="x", y="y"), font="Helvetica").add_line().to_svg()
    assert strip(a) == strip(h)
    assert 'font-family="Helvetica"' in h


def test_font_changes_output_and_is_deterministic():
    base = pt.chart(_df(), aes(x="x", y="y"), title="T").add_line().to_svg()
    ar1 = pt.chart(_df(), aes(x="x", y="y"), title="T", font="Arimo").add_line().to_svg()
    ar2 = pt.chart(_df(), aes(x="x", y="y"), title="T", font="Arimo").add_line().to_svg()
    assert ar1 != base
    assert ar1 == ar2


def test_no_spec_leak_across_renders():
    before = _FONTSPEC["family"]
    pt.chart(_df(), aes(x="x", y="y"), font="Arimo").add_line().to_svg()
    assert _FONTSPEC["family"] == before
    # A font chart rendered earlier must not restyle a later default chart.
    d1 = pt.chart(_df(), aes(x="x", y="y")).add_line().to_svg()
    pt.chart(_df(), aes(x="x", y="y"), font="Arimo").add_line().to_svg()
    d2 = pt.chart(_df(), aes(x="x", y="y")).add_line().to_svg()
    assert d1 == d2


def test_path_selector_never_leaks_into_svg():
    bold = str(_FONT_DIR / "Arimo-Bold.ttf")
    svg = pt.chart(_df(), aes(x="x", y="y"), font=bold).add_line().to_svg()
    assert ".ttf" not in svg
    assert "fonts/" not in svg
    assert 'font-family="Arimo"' in svg    # name table stands in


# ---------------------------------------------------------------------------
# Why DejaVu stays the default — measured coverage
# ---------------------------------------------------------------------------

def _assigned(cps):
    return [c for c in cps if unicodedata.name(chr(c), None) is not None]


# Assigned codepoints per block; Greek skips the reserved U+03A2.
_SYMBOL_BLOCKS = {
    "greek": _assigned(c for c in range(0x0391, 0x03CA) if c != 0x03A2),
    "math_operators": _assigned(range(0x2200, 0x2300)),
    "arrows": _assigned(range(0x2190, 0x2200)),
    "superscripts_subscripts": _assigned(range(0x2070, 0x209D)),
}


def test_scientific_symbol_coverage():
    dj = _load_font(DEJAVU)
    ar = _load_font(ARIMO)
    coverage = {
        name: (sum(1 for c in cps if c in dj.cmap),
               sum(1 for c in cps if c in ar.cmap),
               len(cps))
        for name, cps in _SYMBOL_BLOCKS.items()
    }
    # DejaVu covers the full scientific repertoire — the reason it stays
    # the default.
    for name, (dj_n, _, total) in coverage.items():
        assert dj_n == total, f"DejaVu lost coverage of {name}: {dj_n}/{total}"
    # Arimo's measured gaps (as of Arimo v1.33): full Greek and super/
    # subscripts, but math operators 17/256 and arrows 7/112. If a font
    # update closes these, this documentation should be revisited.
    assert coverage["greek"][1] == coverage["greek"][2]
    assert (coverage["superscripts_subscripts"][1]
            == coverage["superscripts_subscripts"][2])
    assert coverage["math_operators"][1] < 30
    assert coverage["arrows"][1] < 20


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def _demo(font: str | None, title: str, theme: str | None = None) -> pt.Chart:
    xs = [i * 0.1 for i in range(64)]
    kw = {"font": font} if font else {}
    if theme:
        kw["theme"] = theme
    c = pt.chart(title=title, xlabel="t", ylabel="value", legend=True, **kw)
    df = {"x": xs, "y": [math.sin(x) for x in xs]}
    c.add_line(data=df, mapping=aes(x="x", y="y"), label="sin(t)")
    df2 = {"x": xs, "y": [math.cos(x) for x in xs]}
    c.add_line(data=df2, mapping=aes(x="x", y="y"), label="cos(t)", linestyle="--")
    return c


def font_arimo():
    return _demo("Arimo", "font: Arimo")


def font_arimo_dark():
    # font=/theme= compose — the point of decoupling them.
    return _demo("Arimo", "font: Arimo + theme: dark", theme="dark")


def font_path_escape_hatch():
    # Tier 3: load a face by file path (a bundled file the registry
    # doesn't expose). Output must stay self-contained — no path in the
    # SVG — and byte-identical across machines.
    return _demo(str(_FONT_DIR / "Arimo-Bold.ttf"), "font: by file path")


def _variant_demo(font: str | None, title: str) -> pt.Chart:
    # Bold x-ticks, bold-italic y-ticks: exercises the real variant
    # faces AND the style-aware margin measurement (bold advances are
    # wider, so the reservation must match the render).
    df = {"label": ["alpha", "beta", "gamma", "delta"],
          "rate": [0.42, 0.35, 0.28, 0.21]}
    kw = {"font": font} if font else {}
    c = pt.chart(data_width=320, data_height=200, title=title,
                 ylabel="rate", **kw)
    c.add_bar(data=df, mapping=aes(x="label", y="rate"), fill="#5599aa")
    c.xticks(fontweight="bold")
    c.yticks(fontstyle="italic", fontweight="bold")
    return c


def font_variants_dejavu():
    return _variant_demo(None, "DejaVu: bold x, bold-italic y")


def font_variants_arimo():
    return _variant_demo("Arimo", "Arimo: bold x, bold-italic y")


def font_mixed_layout():
    """DejaVu and Arimo leaves side-by-side. Confirms per-leaf
    `_node_style()` scoping keeps each panel's measurement and render
    on its own face."""
    xs = [i * 0.1 for i in range(64)]
    left = pt.chart(title="DejaVu Sans", xlabel="t", ylabel="sin")
    df = {"x": xs, "y": [math.sin(x) for x in xs]}
    left.add_line(data=df, mapping=aes(x="x", y="y"))
    right = pt.chart(title="Arimo", xlabel="t", ylabel="cos", font="Arimo")
    df2 = {"x": xs, "y": [math.cos(x) for x in xs]}
    right.add_line(data=df2, mapping=aes(x="x", y="y"))
    return left | right


PLOTS = {
    "arimo": font_arimo,
    "arimo_dark": font_arimo_dark,
    "path_escape_hatch": font_path_escape_hatch,
    "mixed_layout": font_mixed_layout,
    "variants_dejavu": font_variants_dejavu,
    "variants_arimo": font_variants_arimo,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_fonts_baseline(name, fn, baseline_compare):
    baseline_compare("fonts", name, fn().to_svg())
