"""Output-method tests: save_svg / to_html / write_html / save_pdf.
PNG output has its own coverage in test_chart.py."""
import pytest

import plotlet as pt


def _chart():
    c = pt.chart({"x": [1, 2, 3], "y": [1, 4, 9]}, title="io")
    c.line(x="x", y="y")
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
    grid.line(x="x", y="y")
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


def test_write_html(tmp_path):
    c = _chart()
    out = tmp_path / "fig.html"
    ret = c.write_html(out)
    assert ret is c
    assert out.read_text() == c.to_html(full_page=True)


def test_save_pdf(tmp_path):
    pytest.importorskip("cairosvg")
    out = tmp_path / "fig.pdf"
    _chart().save_pdf(out)
    assert out.read_bytes()[:5] == b"%PDF-"
