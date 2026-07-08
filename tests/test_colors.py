"""Unit tests for color resolution and discrete palettes."""
import pytest

import plotlet as pt
from plotlet.draw import resolve_color, palette, list_palettes, TAB10
from plotlet.utils import palette_color


# ---------------------------------------------------------------- resolve_color

def test_cycle_shortcuts():
    assert resolve_color("C0") == TAB10[0]
    assert resolve_color("C9") == TAB10[9]
    assert resolve_color("C10") == TAB10[0]   # wraps, matplotlib-style
    assert resolve_color("C23") == TAB10[3]


def test_named_and_letter_codes():
    assert resolve_color("blue") == "#1f77b4"
    assert resolve_color("olive") == "#bcbd22"
    for letter, name in [("b", "blue"), ("g", "green"), ("r", "red"),
                         ("c", "cyan"), ("m", "pink"), ("y", "olive")]:
        assert resolve_color(letter) == resolve_color(name)
    assert resolve_color("k") == "#000000"
    assert resolve_color("w") == "#ffffff"


def test_grayscale_strings():
    assert resolve_color("0") == "#000000"
    assert resolve_color("1") == "#ffffff"
    assert resolve_color("0.5") == "#808080"


def test_rgb_tuples():
    assert resolve_color((1, 0, 0)) == "#ff0000"
    assert resolve_color((0.5, 0.5, 0.5)) == "#808080"
    assert resolve_color((1, 0, 0, 0.5)) == "#ff000080"
    assert resolve_color([0, 0, 1]) == "#0000ff"


def test_passthrough():
    assert resolve_color(None) is None
    assert resolve_color("#abc123") == "#abc123"
    assert resolve_color("rebeccapurple") == "rebeccapurple"   # CSS name → SVG
    assert resolve_color("rgb(1, 2, 3)") == "rgb(1, 2, 3)"
    assert resolve_color("2.5") == "2.5"                       # not a grayscale
    assert resolve_color((255, 0, 0)) == (255, 0, 0)           # not in [0, 1]


# ---------------------------------------------------------------- palette()

def test_qualitative_palettes():
    assert palette("tab10") == TAB10
    set2 = palette("Set2")
    assert len(set2) == 8
    assert set2[0] == "#66c2a5"
    assert all(c.startswith("#") and len(c) == 7 for c in set2)
    assert len(palette("Paired")) == 12
    assert len(palette("tab20")) == 20


def test_palette_reversed():
    assert palette("Set2_r") == palette("Set2")[::-1]
    assert palette("tab10_r") == TAB10[::-1]


def test_palette_n_truncates_and_cycles():
    assert palette("Set2", 3) == palette("Set2")[:3]
    ten = palette("Set2", 10)
    assert len(ten) == 10
    assert ten[8] == palette("Set2")[0]   # wraps past the end


def test_continuous_sampling():
    v = palette("viridis", 5)
    assert len(v) == 5
    assert v[0] == "#440154"    # viridis endpoints
    assert v[-1] == "#fde725"
    # _r is its own LUT; interior samples may differ by one quantization
    # step from the reversed forward list, but endpoints are exact.
    r = palette("viridis_r", 5)
    assert (r[0], r[-1]) == (v[-1], v[0])
    with pytest.raises(ValueError, match="continuous"):
        palette("viridis")


def test_palette_unknown():
    with pytest.raises(ValueError, match="unknown palette"):
        palette("nope")


def test_list_palettes():
    names = list_palettes()
    assert "Set2" in names and "tab10" in names
    assert names == sorted(names)


def test_top_level_exports():
    assert pt.palette("Set2") == palette("Set2")
    assert pt.list_palettes() == list_palettes()


def test_palette_is_plain_list_with_swatch_repr():
    import json
    from plotlet.draw import Palette
    p = palette("Set2")
    assert isinstance(p, Palette) and isinstance(p, list)
    assert json.loads(json.dumps(p)) == list(p)     # journal-serializable
    html = p._repr_html_()
    assert html.startswith("<svg") and html.count("<rect") == len(p)
    assert all(c in html for c in p)
    assert "<svg" in TAB10._repr_html_()            # pt.colors previews too


# ---------------------------------------------------------------- palette_color

def test_palette_color_accepts_name():
    assert palette_color("Set2", "a", 0) == palette("Set2")[0]
    assert palette_color("Set2", "b", 9) == palette("Set2")[1]  # wraps mod 8


def test_palette_color_dict_and_list_still_work():
    assert palette_color({"a": "C1"}, "a", 0) == TAB10[1]
    assert palette_color(["r", "g"], None, 3) == resolve_color("g")
    assert palette_color(None, "a", 0) is None


def test_named_palette_flows_to_svg():
    df = {"x": [1, 2, 1, 2], "y": [1, 2, 3, 4], "grp": ["a", "a", "b", "b"]}
    c = pt.chart()
    c.line(data=df, x="x", y="y", color="grp", palette="Set2")
    svg = c.to_svg()
    assert palette("Set2")[0] in svg
    assert palette("Set2")[1] in svg
