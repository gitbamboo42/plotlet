"""Baseline SVG regression tests for the image_rgba artist.

    pytest tests/test_chart_image_rgba.py
    pytest tests/test_chart_image_rgba.py --update
"""
from __future__ import annotations

import numpy as np

import plotlet as pt
import pytest

from _chart_helpers import _embedded_png, _png_dims


def _flag(h=12, w=18):
    """Small three-band color flag — legible on the rect path."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, : w // 3] = [214, 40, 40]
    img[:, w // 3 : 2 * w // 3] = [244, 241, 222]
    img[:, 2 * w // 3 :] = [69, 123, 157]
    return img


def _gradient(h=120, w=160):
    """Smooth RGB gradient — exercises the PNG path with float input."""
    r = np.linspace(0.0, 1.0, w)[None, :, None]
    g = np.linspace(0.0, 1.0, h)[:, None, None]
    b = np.full((h, w, 1), 0.35)
    return np.concatenate(
        [np.broadcast_to(r, (h, w, 1)), np.broadcast_to(g, (h, w, 1)), b],
        axis=2)


def chart_image_rgba_rect():
    c = pt.chart(title="image_rgba (rect path)", xlabel="col", ylabel="row")
    c.add_image_rgba(_flag())
    return c


def chart_image_rgba_png():
    c = pt.chart(title="image_rgba (PNG path)", xlabel="col", ylabel="row")
    c.add_image_rgba(_gradient())
    return c


def chart_image_rgba_alpha():
    # RGBA on the rect path: an alpha ramp fades each column; a refspan
    # behind (background layer) shows through the transparent pixels.
    img = np.zeros((8, 16, 4), dtype=np.uint8)
    img[..., :3] = [214, 40, 40]
    img[..., 3] = np.linspace(0, 255, 16).astype(np.uint8)[None, :]
    c = pt.chart(title="image_rgba (alpha ramp)")
    c.add_axvspan(4, 12, color="#457b9d", alpha=0.5)
    c.add_image_rgba(img)
    return c


def chart_image_rgba_origin_lower():
    # origin="lower" opts into Cartesian orientation (row 0 at the
    # bottom, y-axis not inverted). The asymmetric pattern makes the
    # flip vs. the default ("upper") obvious. extent places the image
    # on real coordinates.
    img = _flag()
    img[:4, :, :] = 30           # dark stripe on rows 0..3
    c = pt.chart(title="image_rgba origin='lower'", xlabel="x", ylabel="y")
    c.add_image_rgba(img, origin="lower", extent=(0, 3.6, 0, 2.4))
    return c


PLOTS = {
    "image_rgba_rect": chart_image_rgba_rect,
    "image_rgba_png": chart_image_rgba_png,
    "image_rgba_alpha": chart_image_rgba_alpha,
    "image_rgba_origin_lower": chart_image_rgba_origin_lower,
}


@pytest.mark.parametrize("name,fn", list(PLOTS.items()), ids=list(PLOTS.keys()))
def test_chart_image_rgba_baseline(name, fn, baseline_compare):
    baseline_compare("chart_image_rgba", name, fn().to_svg())


def _dense(data_width, data_height, channels=3):
    rng = np.random.RandomState(7)
    img = rng.randint(0, 256, (150, 150, channels), dtype=np.uint8)
    if channels == 4:
        img[..., 3] = np.maximum(img[..., 3], 1)   # keep some transparency
    c = pt.chart(data_width=data_width, data_height=data_height)
    c.add_image_rgba(img)
    return c.to_svg()


def test_png_downsamples_to_display_resolution():
    svg = _dense(40, 40)
    assert 'downsampled="true"' in svg
    assert _png_dims(_embedded_png(svg)) == (80, 80)


def test_png_full_resolution_when_it_fits():
    svg = _dense(400, 400)
    assert "downsampled" not in svg
    assert _png_dims(_embedded_png(svg)) == (150, 150)


def test_rgba_png_path_stays_pixelated():
    # The RGBA-PNG emission is shared with the point-cloud raster, which
    # scales smoothly; image_rgba must opt into nearest-neighbour so
    # pixels stay crisp like every other grid artist.
    svg = _dense(40, 40, channels=4)
    assert 'image-rendering="pixelated"' in svg


def test_pool_channels_matches_scalar_reference():
    # The vectorized integer pooling must equal a plain per-bin rule
    # (round half up) — that equality is what makes the pooled bytes
    # machine-independent. RGB: plain per-channel mean. RGBA: alpha by
    # plain mean, color by alpha-weighted mean (a transparent pixel's
    # RGB is invisible and must not vote); an all-transparent bin pins
    # its color to 0. Uneven bins on purpose (37x23 -> 10x7).
    from plotlet.artists.image_rgba import _pool_channels

    rng = np.random.RandomState(3)
    out_h, out_w = 10, 7
    re = [37 * i // out_h for i in range(out_h + 1)]
    ce = [23 * j // out_w for j in range(out_w + 1)]

    rgb = rng.randint(0, 256, (37, 23, 3), dtype=np.uint8)
    got = _pool_channels(rgb, out_h, out_w)
    for i in range(out_h):
        for j in range(out_w):
            block = rgb[re[i]:re[i + 1], ce[j]:ce[j + 1]].astype(int)
            n = block.shape[0] * block.shape[1]
            want = (2 * block.sum(axis=(0, 1)) + n) // (2 * n)
            assert (got[i, j] == want).all()

    rgba = rng.randint(0, 256, (37, 23, 4), dtype=np.uint8)
    rgba[:9, :, 3] = 0            # spans whole bins → all-transparent bins
    rgba[20:, ::2, 3] = 0         # and mixed bins
    got = _pool_channels(rgba, out_h, out_w)
    for i in range(out_h):
        for j in range(out_w):
            block = rgba[re[i]:re[i + 1], ce[j]:ce[j + 1]].astype(int)
            n = block.shape[0] * block.shape[1]
            asum = block[:, :, 3].sum()
            alpha_want = (2 * block[:, :, 3].sum() + n) // (2 * n)
            if asum == 0:
                color_want = np.zeros(3, dtype=int)
            else:
                wsum = (block[:, :, :3] * block[:, :, 3:]).sum(axis=(0, 1))
                color_want = (2 * wsum + asum) // (2 * asum)
            assert got[i, j, 3] == alpha_want
            assert (got[i, j, :3] == color_want).all()


def test_pooled_transparency_does_not_bleed_color():
    # A red square on a fully-transparent black background: pooled bins
    # that mix both must stay pure red (at reduced alpha), not darken —
    # the exact masked-overlay artifact alpha weighting exists to stop.
    img = np.zeros((150, 150, 4), dtype=np.uint8)
    img[30:120, 30:120] = [255, 0, 0, 255]
    from plotlet.artists.image_rgba import _pool_channels
    pooled = _pool_channels(img, 80, 80)
    visible = pooled[:, :, 3] > 0
    assert visible.any()
    assert (pooled[visible][:, 0] == 255).all()   # red never darkens
    assert (pooled[visible][:, 1:3] == 0).all()


def test_input_forms_render_byte_identical():
    # Same pixels as uint8, float 0..1, or nested lists → same bytes.
    img = _flag()
    def render(m, **kw):
        c = pt.chart(title="t", data_width=60, data_height=60)
        c.add_image_rgba(m, **kw)
        return c.to_svg()

    ref = render(img)
    assert render(img.tolist()) == ref
    assert render(img / 255.0) == ref
    assert render(img, origin="lower") == render(img.tolist(), origin="lower")

    # fully-opaque RGBA canonicalizes to RGB — identical output, and the
    # schema reports 3 channels
    opaque = np.dstack([img, np.full(img.shape[:2], 255, dtype=np.uint8)])
    assert render(opaque) == ref
    assert 'data-plotlet-channels="3"' in render(opaque)


def test_journal_roundtrip_byte_identical():
    import json
    img = np.zeros((5, 7, 4), dtype=np.uint8)
    img[..., :3] = 120
    img[..., 3] = 200
    c = pt.chart()
    c.add_image_rgba(img, origin="lower", extent=(0, 7, 0, 5))
    blob = json.dumps(pt.to_journal(c).to_dict())
    c2 = pt.from_journal(pt.Journal.from_dict(json.loads(blob)))
    assert c.to_svg() == c2.to_svg()


def test_wrong_shape_redirects():
    with pytest.raises(TypeError, match="add_image_cmap"):
        pt.chart().add_image_rgba([[1, 2], [3, 4]]).to_svg()
    with pytest.raises(TypeError, match="add_image_rgba"):
        pt.chart().add_image_cmap(_flag()).to_svg()
    with pytest.raises(TypeError, match="add_image_rgba"):
        pt.chart().add_image_cmap(_flag().tolist()).to_svg()
    with pytest.raises(ValueError, match="H, W, 3"):
        pt.chart().add_image_rgba(np.zeros((4, 4, 2))).to_svg()
    with pytest.raises(ValueError, match="NaN"):
        bad = np.zeros((2, 2, 3))
        bad[0, 0, 0] = float("nan")
        pt.chart().add_image_rgba(bad).to_svg()
