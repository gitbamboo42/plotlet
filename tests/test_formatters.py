"""Unit tests for named tick formatters and super/subscript helpers."""
import pytest

import plotlet as pt
from plotlet import aes
from plotlet.formatters import get_formatter, _SUPERSCRIPTS, _SUBSCRIPTS


def test_superscript():
    assert pt.superscript("5") == "⁵"
    # 1/2/3 must be the Latin-1 codepoints — U+2071-2073 are unassigned
    # in Unicode and would render as tofu.
    assert pt.superscript("123") == "¹²³"
    assert pt.superscript("-2") == "⁻²"
    assert pt.superscript("−2") == "⁻²"   # true minus too
    assert pt.superscript("(n+1)") == "⁽ⁿ⁺¹⁾"
    with pytest.raises(ValueError, match="superscript"):
        pt.superscript("z")


def test_subscript():
    assert pt.subscript("2") == "₂"
    assert "H" + pt.subscript("2") + "O" == "H₂O"
    assert pt.subscript("max") == "ₘₐₓ"
    with pytest.raises(ValueError, match="subscript"):
        pt.subscript("q")


def test_power10():
    f = get_formatter("power10")
    assert f(100000) == "10⁵"
    assert f(1) == "10⁰"
    assert f(10) == "10¹"
    assert f(0.1) == "10⁻¹"
    assert f(0.002) == "2×10⁻³"
    assert f(5e6) == "5×10⁶"
    assert f(0) == "0"
    assert f(-1000) == "-10³"


def test_power10_in_svg():
    df = {"x": [1, 10, 100, 1000], "y": [1, 2, 3, 4]}

    c = pt.chart(df, aes(x="x", y="y"))
    c.add_line()
    c.xscale("log")
    c.xticks(format="power10")
    assert ".notdef" not in c.to_svg()


def test_helper_chars_covered_by_bundled_fonts():
    # Every char the helpers can emit must have a real glyph in every
    # bundled face — a new mapping that hits a cmap gap renders as the
    # tofu box, which no exception would catch.
    from fontTools.ttLib import TTFont
    from plotlet.draw.font import _FONT_DIR
    chars = set(_SUPERSCRIPTS.values()) | set(_SUBSCRIPTS.values()) | {"×"}
    for path in sorted(_FONT_DIR.glob("*.ttf")):
        cmap = TTFont(str(path)).getBestCmap()
        missing = [c for c in chars if ord(c) not in cmap]
        assert not missing, f"{path.name} lacks glyphs for {missing}"


def test_list_formatters_has_builtins():
    names = pt.list_formatters()
    for n in ("money", "si", "percent", "scientific", "comma", "power10"):
        assert n in names
