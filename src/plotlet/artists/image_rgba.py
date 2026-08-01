"""(H, W, 3|4) pixel array → image. Each cell already IS a color.

The counterpart of `add_image_cmap`: no colormap, no vmin/vmax/norm, no
colorbar — the array carries final RGB(A) values. For a 2-D matrix of
scalars that needs a colormap, use `add_image_cmap` instead.

Input is a decoded pixel array, not a file path — decode with PIL /
imageio yourself (`np.asarray(Image.open(p))`). Channel convention
follows matplotlib: float values are 0..1, integer values 0..255; both
are clipped and stored as 8-bit channels. A fully-opaque RGBA array
canonicalizes to RGB at record time (same pixels, smaller PNG).

`origin` defaults to `"upper"` — row 0 at the TOP, so a photo displays
as-seen — and the panel auto-inverts the y-axis to match (this is the
opposite default from `add_image_cmap`, whose matrices are Cartesian by
default). Pass `origin="lower"` for row 0 at the bottom.

Rendering branches like image_cmap: one <rect> per pixel below
`image_max_rects` (sharp at any zoom), one base64 PNG above. An image
denser than `raster_oversample` pixels per display pixel is mean-pooled
per channel to that cap first — integer arithmetic end-to-end, so the
byte-identical-SVG guarantee holds.
"""
import numpy as np

from ..registry import ArtistSpec, add_artist
from ..utils import pack_opts
from .._spec import _D
from ..draw import rect
from ..draw import image_png, image_png_rgba
from ._shared import pool_target


def _to_pixels(image):
    """Ingest → canonical uint8 (H, W, 3|4) array. Floats are 0..1,
    integers 0..255 (matplotlib's convention), both clipped; a
    fully-opaque alpha channel is dropped. Raises with a pointer to
    add_image_cmap on 2-D input."""
    a = np.asarray(image)
    if a.ndim == 2:
        raise TypeError(
            "image_rgba takes (H, W, 3|4) RGB(A) pixel data; for a 2-D "
            "value matrix rendered through a colormap use add_image_cmap."
        )
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError(
            f"image_rgba: expected an (H, W, 3|4) array, got shape "
            f"{a.shape if a.ndim else '()'}"
        )
    if a.dtype == object:
        a = a.astype(np.float64)
    if a.dtype.kind == "f":
        if np.isnan(a).any():
            raise ValueError("image_rgba: NaN in pixel data")
        # Same rounding as image_cmap's cell lookup: floor(v * 255 + 0.5).
        a = (np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    elif a.dtype.kind == "b":
        a = a.astype(np.uint8) * 255
    elif a.dtype.kind in "iu":
        a = np.clip(a, 0, 255).astype(np.uint8)
    else:
        raise ValueError(
            f"image_rgba: unsupported dtype {a.dtype} — pass float (0..1) "
            f"or integer (0..255) channels"
        )
    if a.shape[2] == 4 and bool((a[:, :, 3] == 255).all()):
        a = np.ascontiguousarray(a[:, :, :3])
    return a


def _image_rgba_record(image, origin=None, extent=None):
    d = _to_pixels(image)
    opts = pack_opts(origin=origin, extent=extent)
    return {"type": "image_rgba", "_data": d,
            "_nrows": int(d.shape[0]), "_ncols": int(d.shape[1]),
            "_channels": int(d.shape[2]), "opts": opts}


def _box_sums(arr, re, ce):
    """Per-bin sums of an int64 (H, W, C) array over the bin grid whose
    edges are `re`/`ce` — 2-D prefix sums plus inclusion–exclusion.
    Integer arithmetic is exact, so the result can't depend on summation
    order (unlike float sums, whose pairwise order is a numpy
    implementation detail)."""
    h, w, ch = arr.shape
    cs = np.zeros((h + 1, w + 1, ch), dtype=np.int64)
    cs[1:, 1:] = arr
    np.cumsum(cs, axis=0, out=cs)
    np.cumsum(cs, axis=1, out=cs)
    return (cs[re[1:], :][:, ce[1:]] - cs[re[:-1], :][:, ce[1:]]
            - cs[re[1:], :][:, ce[:-1]] + cs[re[:-1], :][:, ce[:-1]])


def _pool_channels(a, out_h, out_w):
    """Box-pool a uint8 (H, W, C) image to (out_h, out_w, C), rounding
    half up. Bin edges by integer rounding, same as `pool_grid`. Integer
    arithmetic end-to-end — exact, so bytes can't drift across machines
    or numpy versions.

    RGB pools by plain per-channel mean. RGBA pools alpha by plain mean
    but color by *alpha-weighted* mean: a transparent pixel's stored RGB
    is invisible, so letting it vote in the bin's color would bleed
    fringe colors into downsampled edges (masked overlays store
    "alpha 0, RGB 0" — the naive mean darkens every boundary bin). An
    all-transparent bin has no color to speak of; its RGB pins to 0."""
    h, w, ch = a.shape
    re = np.array([h * i // out_h for i in range(out_h + 1)])
    ce = np.array([w * j // out_w for j in range(out_w + 1)])
    counts = (np.diff(re)[:, None] * np.diff(ce)[None, :])[:, :, None]
    if ch == 3:
        sums = _box_sums(a.astype(np.int64), re, ce)
        return ((2 * sums + counts) // (2 * counts)).astype(np.uint8)
    alpha = a[:, :, 3:].astype(np.int64)
    asum = _box_sums(alpha, re, ce)
    alpha_out = (2 * asum + counts) // (2 * counts)
    wsum = _box_sums(a[:, :, :3] * alpha, re, ce)   # max 255*255*bin — int64-safe
    denom = np.maximum(asum, 1)
    color = np.where(asum > 0, (2 * wsum + denom) // (2 * denom), 0)
    return np.concatenate([color, alpha_out], axis=2).astype(np.uint8)


def _artist_image_rgba(a, xs_, ys_):
    nrows = a["_nrows"]; ncols = a["_ncols"]
    if nrows == 0 or ncols == 0:
        return ""
    data = a["_data"]
    opts = a["opts"]
    origin = opts.get("origin", "upper")

    extent = opts.get("extent")
    if extent is None:
        x_left, x_right, y_bot, y_top = 0.0, float(ncols), 0.0, float(nrows)
    else:
        x_left, x_right, y_bot, y_top = extent

    sxa = xs_(x_left); sxb = xs_(x_right)
    sya = ys_(y_bot);  syb = ys_(y_top)
    sx_l = min(sxa, sxb); sx_r = max(sxa, sxb)
    sy_t = min(sya, syb); sy_b = max(sya, syb)
    pw = sx_r - sx_l; ph = sy_b - sy_t
    if pw <= 0 or ph <= 0:
        return ""

    # Render order = pixel rows walked top to bottom. Default
    # origin="upper": row 0 at the top — natural data order.
    # origin="lower": row 0 at the bottom — iterate reversed (a stride
    # view, no copy).
    pixels = data if origin == "upper" else data[::-1]

    if nrows * ncols <= _D["image_max_rects"]:
        return "".join(_rects_pass(pixels, a["_channels"],
                                   sx_l, sy_t, pw / ncols, ph / nrows))
    out, a["_downsampled"] = _png_pass(pixels, a["_channels"],
                                       sx_l, sy_t, pw, ph, ncols, nrows)
    return out


def _rects_pass(pixels, channels, sx_l, sy_t, cw, ch):
    """One <rect> per pixel — sharp at any zoom. An alpha channel maps
    to whole-rect opacity."""
    out = []
    for r, row in enumerate(pixels):
        y = sy_t + r * ch
        for c, px in enumerate(row):
            fill = f"rgb({px[0]},{px[1]},{px[2]})"
            alpha = px[3] / 255 if channels == 4 else 1
            out.append(rect(sx_l + c * cw, y, cw, ch,
                            fill=fill, alpha=alpha))
    return out


def _png_pass(pixels, channels, sx_l, sy_t, pw, ph, ncols, nrows):
    """Whole image as one base64 PNG — bounded SVG size for big arrays.
    Pools to display resolution first when denser than
    `raster_oversample` pixels per display pixel (see `_pool_channels`).
    Returns `(element, downsampled)`."""
    out_w = pool_target(ncols, pw)
    out_h = pool_target(nrows, ph)
    downsampled = (out_w, out_h) != (ncols, nrows)
    if downsampled:
        pixels = _pool_channels(pixels, out_h, out_w)
    buf = np.ascontiguousarray(pixels).tobytes()
    if channels == 4:
        el = image_png_rgba(sx_l, sy_t, pw, ph, buf, out_w, out_h,
                            pixelated=True)
    else:
        el = image_png(sx_l, sy_t, pw, ph, buf, out_w, out_h)
    return el, downsampled


def _image_rgba_data_attrs(a):
    out = {
        "rows": a["_nrows"],
        "cols": a["_ncols"],
        "channels": a["_channels"],
        "data-encoding": "png-embedded" if (a["_nrows"] * a["_ncols"]
                                              > _D["image_max_rects"]) else "rects",
    }
    if a.get("_downsampled"):
        out["downsampled"] = "true"
    extent = a["opts"].get("extent")
    if extent is not None:
        out["extent"] = ",".join(repr(float(v)) for v in extent)
    origin = a["opts"].get("origin", "upper")
    if origin != "upper":
        out["origin"] = origin
    return out


def _image_rgba_xdomain(a):
    ext = a["opts"].get("extent")
    if ext is None:
        return [0, a["_ncols"]]
    return [ext[0], ext[1]]


def _image_rgba_ydomain(a):
    ext = a["opts"].get("extent")
    if ext is None:
        return [0, a["_nrows"]]
    return [ext[2], ext[3]]


add_artist(ArtistSpec(
    name="image_rgba",
    data_input="matrix",
    record=_image_rgba_record,
    xdomain=_image_rgba_xdomain,
    ydomain=_image_rgba_ydomain,
    draw=lambda a, ctx: _artist_image_rgba(a, ctx.x_scale, ctx.y_scale),
    uses_color_cycle=False,
    data_attrs=_image_rgba_data_attrs,
    flips_y_axis=lambda a: a["opts"].get("origin", "upper") == "upper",
    tight_domain=True,
))
