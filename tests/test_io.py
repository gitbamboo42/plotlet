"""Output-method tests: save_svg / to_html / save_html / save_pdf.
PNG render baselines live in test_chart_imshow.py; the PNG output
methods (save_png / repr_mimebundle) are exercised here."""
import pytest

import plotlet as pt
from plotlet import aes
from _chart_helpers import _png_dims


def _chart():
    df = {"x": [1, 2, 3], "y": [1, 4, 9]}

    c = pt.chart(df, aes(x="x", y="y"), title="io")
    c.add_line()
    return c


def test_save_svg_roundtrip(tmp_path):
    c = _chart()
    out = tmp_path / "fig.svg"
    ret = c.save_svg(out)
    assert ret is c
    assert out.read_text() == c.to_svg()


def test_save_svg_clean_strips_metadata(tmp_path):
    c = _chart()
    out = tmp_path / "fig.svg"
    c.save_svg(out, clean=True)
    text = out.read_text()
    assert "data-plotlet-" not in text
    assert text.startswith("<svg")


def test_facetgrid_save_svg_clean(tmp_path):
    data = {"x": [1, 2, 3, 4], "y": [1, 2, 3, 4], "g": ["a", "a", "b", "b"]}
    grid = pt.facet(data, by="g")
    grid.add_line(aes(x="x", y="y"))
    out = tmp_path / "grid.svg"
    grid.save_svg(out, clean=True)
    assert "data-plotlet-" not in out.read_text()


def test_to_html_variants():
    c = _chart()
    bare = c.to_html()
    assert bare.startswith("<svg")
    page = c.to_html(full_page=True)
    assert page.startswith("<!doctype html>")
    assert bare in page


def test_save_html(tmp_path):
    c = _chart()
    out = tmp_path / "fig.html"
    ret = c.save_html(out)
    assert ret is c
    assert out.read_text() == c.to_html(full_page=True)


def test_save_pdf(tmp_path):
    pytest.importorskip("cairosvg")
    out = tmp_path / "fig.pdf"
    _chart().save_pdf(out)
    assert out.read_bytes()[:5] == b"%PDF-"


def test_repr_mimebundle_png():
    df = {"x": [1, 2, 3], "y": [1, 2, 3]}

    c = pt.chart(df, aes(x="x", y="y"), title="t")
    c.add_line()
    data, meta = c._repr_mimebundle_()
    png = data["image/png"]
    w, h = meta["image/png"]["width"], meta["image/png"]["height"]
    # metadata carries the logical (1x) size off the svg root tag
    svg = c.to_svg()
    assert f'width="{w}" height="{h}"' in svg[:200]
    # pixels are rendered at _REPR_SCALE x the logical size
    from plotlet.record.chart import _REPR_SCALE
    assert _png_dims(png) == (w * _REPR_SCALE, h * _REPR_SCALE)
    # deterministic — same journal, byte-identical PNG
    data2, _ = c._repr_mimebundle_()
    assert data2["image/png"] == png


def test_save_png_scale(tmp_path):
    df = {"x": [1, 2, 3], "y": [1, 2, 3]}

    c = pt.chart(df, aes(x="x", y="y"), title="t")
    c.add_line()
    from plotlet.record.chart import _svg_size
    w, h = _svg_size(c.to_svg())
    c.save_png(tmp_path / "one.png")
    c.save_png(tmp_path / "two.png", scale=2)
    assert _png_dims((tmp_path / "one.png").read_bytes()) == (w, h)
    assert _png_dims((tmp_path / "two.png").read_bytes()) == (2 * w, 2 * h)


def test_png_paints_figure_background():
    # The background rect must survive rasterization (the reason it is a
    # real rect, not CSS). Check the top-left pixel of an RGBA PNG by
    # decoding the first scanline with zlib — no image library needed.
    import struct, zlib

    def corner_rgba(png):
        assert png[25] == 6  # IHDR color type: RGBA
        # walk chunks to the IDAT payload
        pos, idat = 8, b""
        while pos < len(png):
            (ln,), typ = struct.unpack(">I", png[pos:pos + 4]), png[pos + 4:pos + 8]
            if typ == b"IDAT":
                idat += png[pos + 8:pos + 8 + ln]
            pos += 12 + ln
        raw = zlib.decompress(idat)
        # first pixel of the first scanline: every PNG filter type
        # reduces to the raw value (no left/up neighbours to add)
        return tuple(raw[1:5])

    df = {"x": [1, 2, 3], "y": [1, 2, 3]}

    c = pt.chart(df, aes(x="x", y="y"), title="t")
    c.add_line()
    from plotlet.record.chart import _svg_to_png
    assert corner_rgba(_svg_to_png(c.to_svg())) == (255, 255, 255, 255)

    df2 = {"x": [1, 2, 3], "y": [1, 2, 3]}

    d = pt.chart(df2, aes(x="x", y="y"), theme="dark", title="t")
    d.add_line()
    assert corner_rgba(_svg_to_png(d.to_svg())) == (31, 31, 31, 255)


def test_show_rejects_unknown_format():
    df = {"x": [1, 2], "y": [1, 2]}

    c = pt.chart(df, aes(x="x", y="y"), title="t")
    c.add_line()
    with pytest.raises(ValueError, match="png.*svg"):
        c.show(format="jpeg")


def test_category_metadata_survives_cdata_breakout():
    # A category label containing `]]>` must not terminate the CDATA
    # section early — that would leave raw markup outside it (injection)
    # and break XML parsing.
    import json
    import xml.etree.ElementTree as ET
    label = ']]><script>alert(1)</script>'
    df = {"cat": ["a", label], "v": [1, 2]}

    c = pt.chart(df, aes(x="cat", y="v"))
    c.add_bar()
    svg = c.to_svg()
    root = ET.fromstring(svg)
    assert not [el for el in root.iter() if el.tag.endswith("script")]
    # the label round-trips inside the metadata block's JSON payload
    meta = [el for el in root.iter()
            if el.tag.endswith("metadata")
            and el.get("data-plotlet-payload") == "xcategories"]
    assert len(meta) == 1
    assert json.loads(meta[0].text) == ["a", label]
    # clean=True strips the whole block despite the split CDATA sections
    cleaned = c.to_svg(clean=True)
    assert "<metadata" not in cleaned and "CDATA" not in cleaned
    assert "script" not in cleaned


def test_clean_strips_metadata_containing_close_tag():
    # A label containing a literal `</metadata>` sits legally inside CDATA;
    # clean=True must strip to the block's real terminator, not the label.
    label = "</metadata>x"
    df = {"cat": [label, "b"], "v": [1, 2]}

    c = pt.chart(df, aes(x="cat", y="v"))
    c.add_bar()
    cleaned = c.to_svg(clean=True)
    assert "metadata" not in cleaned and "CDATA" not in cleaned


def test_utils_all_names_exist():
    # `from plotlet.utils import *` must not raise — every exported
    # name has to exist (the removed `histogram` lingered here once)
    import plotlet.utils as utils
    for name in utils.__all__:
        assert hasattr(utils, name), name
