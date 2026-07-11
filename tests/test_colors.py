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


def test_colorblind_palette():
    cb = palette("colorblind")
    assert cb == ["#000000", "#e69f00", "#56b4e9", "#009e73",
                  "#f0e442", "#0072b2", "#d55e00", "#cc79a7"]   # Okabe–Ito
    assert palette("colorblind_r") == cb[::-1]
    assert palette("colorblind", 3) == cb[:3]
    ten = palette("colorblind", 10)
    assert len(ten) == 10 and ten[8] == cb[0]   # wraps past the end
    assert "colorblind" in list_palettes()


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


# ---------------------------------------------------------------- register_colormap

def test_register_colormap_endpoints_and_midpoint():
    pt.register_colormap("bwr2", ["#2166ac", "#ffffff", "#b2182b"])
    cm = pt.colormap("bwr2")
    assert cm(0.0) == (0x21, 0x66, 0xac)
    assert cm(1.0) == (0xb2, 0x18, 0x2b)
    # 0.5 lands between LUT samples (0.5 * 255 = 127.5) — white to
    # within one quantization step
    assert all(ch >= 254 for ch in cm(0.5))


def test_register_colormap_reversed_variant():
    pt.register_colormap("gb_ramp", ["green", "blue"])
    names = pt.list_colormaps()
    assert "gb_ramp" in names and "gb_ramp_r" in names
    cm, cr = pt.colormap("gb_ramp"), pt.colormap("gb_ramp_r")
    assert cr(0.0) == cm(1.0) and cr(1.0) == cm(0.0)
    # the LUT itself is an exact triple-wise reversal
    from plotlet.draw import colormap_lut
    f, r = colormap_lut("gb_ramp"), colormap_lut("gb_ramp_r")
    assert all(r[3 * i:3 * i + 3] == f[3 * (255 - i):3 * (255 - i) + 3]
               for i in (0, 1, 100, 255))


def test_register_colormap_linear_interpolation():
    pt.register_colormap("kw_ramp", ["#000000", "#ffffff"])
    cm = pt.colormap("kw_ramp")
    assert cm(0.5) == (128, 128, 128)   # quantized midpoint of black→white


def test_register_colormap_stops():
    # black→white→black with the white anchor at 0.2 (= 51/255, exactly
    # on a LUT sample).
    pt.register_colormap("kwk", ["#000000", "#ffffff", "#000000"],
                         stops=[0, 0.2, 1])
    from plotlet.draw import colormap_lut
    lut = colormap_lut("kwk")
    assert len(lut) == 768
    assert lut[0:3] == b"\x00\x00\x00"
    assert lut[3 * 51:3 * 51 + 3] == b"\xff\xff\xff"
    assert lut[-3:] == b"\x00\x00\x00"


def test_register_colormap_accepts_tuples_and_names():
    pt.register_colormap("tup_ramp", [(0, 0, 0), "red", "C0"])
    cm = pt.colormap("tup_ramp")
    assert cm(0.0) == (0, 0, 0)
    assert cm(1.0) == (0x1f, 0x77, 0xb4)    # C0 == tab10 blue


def test_register_colormap_accepts_css_names():
    # the docstring example, verbatim
    pt.register_colormap("bwr_css", ["#2166ac", "white", "#b2182b"])
    assert all(ch >= 254 for ch in pt.colormap("bwr_css")(0.5))
    pt.register_colormap("navy_ramp", ["navy", "ivory"])
    cm = pt.colormap("navy_ramp")
    assert cm(0.0) == (0x00, 0x00, 0x80)
    assert cm(1.0) == (0xff, 0xff, 0xf0)
    # plotlet names still win over CSS: "red" is the tab10 red, not #ff0000
    pt.register_colormap("red_ramp", ["red", "white"])
    assert pt.colormap("red_ramp")(0.0) == (0xd6, 0x27, 0x28)


def test_register_colormap_overwrite_allowed():
    pt.register_colormap("mut_ramp", ["#000000", "#ff0000"])
    pt.register_colormap("mut_ramp", ["#000000", "#00ff00"])
    assert pt.colormap("mut_ramp")(1.0) == (0, 255, 0)


def test_register_colormap_feeds_palette():
    pt.register_colormap("pal_ramp", ["#000000", "#ffffff"])
    p = palette("pal_ramp", 3)
    assert p == ["#000000", "#808080", "#ffffff"]
    # interior _r samples can shift one quantization step; endpoints exact
    r = palette("pal_ramp_r", 3)
    assert (r[0], r[-1]) == (p[-1], p[0])


def test_register_colormap_rejects_bad_input():
    with pytest.raises(ValueError, match="built-in"):
        pt.register_colormap("viridis", ["#000000", "#ffffff"])
    with pytest.raises(ValueError, match="reserved"):
        pt.register_colormap("foo_r", ["#000000", "#ffffff"])
    with pytest.raises(ValueError, match="at least 2"):
        pt.register_colormap("solo", ["#000000"])
    with pytest.raises(ValueError, match="stops"):
        pt.register_colormap("bad", ["#000000", "#ffffff"], stops=[0, 0.5, 1])
    with pytest.raises(ValueError, match="start at 0"):
        pt.register_colormap("bad", ["#000000", "#ffffff"], stops=[0.1, 1])
    with pytest.raises(ValueError, match="increasing"):
        pt.register_colormap("bad", ["k", "w", "k"], stops=[0, 0, 1])
    with pytest.raises(ValueError, match="can't interpolate"):
        pt.register_colormap("bad", ["not-a-color", "#ffffff"])
    assert "bad" not in pt.list_colormaps()


def test_unknown_colormap_hints_register():
    with pytest.raises(ValueError, match="register_colormap"):
        pt.colormap("no_such_cmap")


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
