"""Raster fast-path toolkit for dense point-cloud artists.

Why splat marks into pixels instead of emitting one SVG node per point:
plotlet's only rasterizer is resvg (SVG -> PNG), and resvg refuses a
document past a node limit -- the exact wall a million-point scatter
hits. matplotlib can rasterize *any* artist generically because it owns
Agg, a primitive rasterizer; we don't. So each dense artist splats its
own marks into a pixel buffer *before* the nodes exist, then embeds one
`<image>`. The approach mirrors datashader / ggrastr: aggregate marks to
a fixed grid whose cost is set by the raster size, not the point count.

Two primitives cover every point-cloud artist plotlet ships:
  - disks             -> scatter, strip, swarm, qq
  - axis-aligned ticks -> rug

Overlapping same-color marks stack exactly as source-over compositing:
a pixel covered k times gets alpha `1 - (1 - a)**k`, matching k stacked
semi-transparent vector marks. The PNG encoder is deterministic, so the
output stays byte-identical across machines -- reproducibility holds.

Callers group marks by color and call the splatter once per color (one
`<image>` per color; the count is bounded by the number of series, not
the data size). A continuous color ramp splats once through
`splat_disks_cmap` instead: the mapped value is aggregated per pixel
and colormapped after, so overlap shows the color of the mean value.
Color must be a solid color the parser understands; anything fancier
(outlines, per-point sizes) stays on the vector path -- correctness
over speed.
"""
import math
import warnings

import numpy as np
from scipy.signal import fftconvolve

from ._png import image_png_rgba
from .._spec import _RASTERSPEC


def parse_rgb(c):
    """Solid SVG color string -> (r, g, b) ints, or None if it isn't one
    of the shapes the artists' color resolution emits ('#rgb', '#rrggbb',
    'rgb(r,g,b)'). None makes the caller fall back to vector marks."""
    if not isinstance(c, str):
        return None
    s = c.strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) == 6:
            try:
                return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            except ValueError:
                return None
    if s.startswith("rgb(") and s.endswith(")"):
        try:
            parts = [int(float(p)) for p in s[4:-1].split(",")[:3]]
            if len(parts) == 3:
                return tuple(parts)
        except ValueError:
            return None
    return None


def should_rasterize(n, rasterized_opt):
    """Vector vs raster for `n` marks. Explicit `rasterize=` wins;
    otherwise auto above `dense_threshold` — the one spec number for
    "this many marks is too many for per-mark vector output", shared
    with the line decimation in `draw/_simplify.py`."""
    if rasterized_opt is not None:
        return bool(rasterized_opt)
    return n >= _RASTERSPEC["dense_threshold"]


def raster_declined(artist, n, reason, rasterize_opt):
    """The artist decided to rasterize (explicit `rasterize=True`, or auto
    above the threshold) but can't honor it for `reason`. An explicit
    request must never be silently ignored, so it raises. In auto mode it
    warns instead: the vector fallback is exactly the giant output the
    fast-path exists to avoid, and without the warning a later resvg
    node-limit failure would be a mystery."""
    if rasterize_opt is True:
        raise ValueError(f"{artist}: rasterize=True, but {reason}.")
    warnings.warn(
        f"{artist}: {n} marks stay vector because {reason}; the SVG will "
        f"be large and save_png may hit resvg's node limit. Pass "
        f"rasterize=False to silence this warning.",
        RuntimeWarning)


def _supersample():
    return max(1, int(_RASTERSPEC["dense_supersample"]))


def _compose(cov, rgb, alpha, iw, ih, W, H):
    """Coverage counts (H, W) + one solid color -> one `<image>` string."""
    a_out = np.where(cov > 0, 1.0 - (1.0 - alpha) ** cov, 0.0)
    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rgba[..., 0] = rgb[0]
    rgba[..., 1] = rgb[1]
    rgba[..., 2] = rgb[2]
    rgba[..., 3] = (a_out * 255 + 0.5).astype(np.uint8)
    return image_png_rgba(0.0, 0.0, iw, ih, rgba.tobytes(), W, H)


def splat_disks(px, py, radius, rgb, alpha, iw, ih):
    """Splat disk markers of one color at panel-pixel centers `px`, `py`
    (arrays) -> one `<image>`. Coverage = (histogram of centers) convolved
    with a disk kernel: one bincount + one FFT convolution, so 2M points
    splat as fast as 100k."""
    ss = _supersample()
    W = max(1, int(round(iw * ss)))
    H = max(1, int(round(ih * ss)))
    px = np.asarray(px, dtype=float) * ss
    py = np.asarray(py, dtype=float) * ss
    good = np.isfinite(px) & np.isfinite(py)
    ix = np.round(px[good]).astype(np.int64)
    iy = np.round(py[good]).astype(np.int64)
    inb = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
    centers = np.bincount(iy[inb] * W + ix[inb],
                          minlength=W * H).reshape(H, W).astype(float)
    R = max(0.5, radius * ss)
    rr = int(math.ceil(R))
    dy, dx = np.ogrid[-rr:rr + 1, -rr:rr + 1]
    kernel = ((dx * dx + dy * dy) <= R * R).astype(float)
    cov = np.rint(fftconvolve(centers, kernel, mode="same")).astype(np.int64)
    cov[cov < 0] = 0
    return _compose(cov, rgb, alpha, iw, ih, W, H)


def splat_disks_cmap(px, py, idx, lut, radius, alpha, iw, ih):
    """Splat disk markers whose colors come from a colormap -> one
    `<image>` (continuous-color scatter). `idx` holds each point's LUT
    index (0-255), or -1 for a missing value (painted black); `lut` is
    the 256 * 3 byte colormap table.

    Follows datashader's rule for continuous data: aggregate the
    value, then colormap the aggregate. Three planes go through the
    same histogram + disk-kernel convolution as `splat_disks` -- total
    coverage, valid coverage, LUT-index sum -- and each pixel takes
    the color of its mean index. Every rendered color therefore sits
    on the colormap ramp and reads truthfully against the colorbar;
    averaging RGB instead would blend off-ramp colors that match no
    colorbar value. Alpha is the usual `1 - (1 - a)**k` on total
    coverage; pixels covered only by missing values paint black.
    Order-independent: shuffling the rows never changes the image, and
    a single-index cloud comes out identical to `splat_disks` on every
    covered pixel. Indices live in normalized space, so under a
    nonlinear norm (e.g. log) the mean is taken there, not on the raw
    values.

    Reproducibility: all three planes hold true integers, so rounding
    the convolutions back to integers kills the FFT float noise; the
    mean is then a division of exact integers, deterministic across
    machines like the single-color path."""
    ss = _supersample()
    W = max(1, int(round(iw * ss)))
    H = max(1, int(round(ih * ss)))
    px = np.asarray(px, dtype=float) * ss
    py = np.asarray(py, dtype=float) * ss
    idx = np.asarray(idx, dtype=np.int64)
    good = np.isfinite(px) & np.isfinite(py)
    ix = np.round(px[good]).astype(np.int64)
    iy = np.round(py[good]).astype(np.int64)
    inb = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
    flat = iy[inb] * W + ix[inb]
    idx_in = idx[good][inb]
    valid = idx_in >= 0

    def plane(pos, weights=None):
        counts = np.bincount(pos, weights=weights,
                             minlength=W * H).reshape(H, W).astype(float)
        out = np.rint(fftconvolve(counts, kernel, mode="same"))
        out[out < 0] = 0
        return out.astype(np.int64)

    R = max(0.5, radius * ss)
    rr = int(math.ceil(R))
    dy, dx = np.ogrid[-rr:rr + 1, -rr:rr + 1]
    kernel = ((dx * dx + dy * dy) <= R * R).astype(float)
    cov = plane(flat)
    n_valid = plane(flat[valid])
    idx_sum = plane(flat[valid], weights=idx_in[valid].astype(float))
    mean_idx = idx_sum / np.where(n_valid > 0, n_valid, 1)
    mi = np.clip((mean_idx + 0.5).astype(np.int64), 0, 255)
    colors = np.frombuffer(bytes(lut), dtype=np.uint8).reshape(256, 3)[mi]
    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rgba[..., :3] = np.where(n_valid[..., None] > 0, colors, 0)
    a_out = np.where(cov > 0, 1.0 - (1.0 - alpha) ** cov, 0.0)
    rgba[..., 3] = (a_out * 255 + 0.5).astype(np.uint8)
    return image_png_rgba(0.0, 0.0, iw, ih, rgba.tobytes(), W, H)


def splat_disks_by_color(marks, radius, alpha, iw, ih):
    """`marks`: iterable of (color_str, px, py). Group by color and splat
    each color once -> one `<image>` per color, in first-appearance
    (painter) order. Returns the joined string, or None if any color isn't
    a solid parseable color (the caller then falls back to vector marks).

    For the category artists (strip / swarm): dodge/jitter puts different
    groups in different slots, so cross-color overlap -- where per-color
    painter order would differ from the interleaved vector order -- is
    rare and only visible under heavy transparency."""
    order = []
    groups = {}
    for col, px, py in marks:
        g = groups.get(col)
        if g is None:
            g = ([], [])
            groups[col] = g
            order.append(col)
        g[0].append(px)
        g[1].append(py)
    out = []
    for col in order:
        rgb = parse_rgb(col)
        if rgb is None:
            return None
        xs, ys = groups[col]
        out.append(splat_disks(xs, ys, radius, rgb, alpha, iw, ih))
    return "".join(out)


def splat_ticks(pos, span_lo, span_hi, width, rgb, alpha, iw, ih,
                *, vertical):
    """Splat axis-aligned ticks of one color -> one `<image>` (rug).

    `vertical=True`: ticks are vertical bars at x-positions `pos`, each
    spanning y in [span_lo, span_hi]. `vertical=False`: horizontal bars at
    y-positions `pos` spanning x in [span_lo, span_hi]. `width` is the
    stroke width in px. Every tick shares the same span, so the coverage
    is a 1-D per-line histogram broadcast across the span rows/cols."""
    ss = _supersample()
    W = max(1, int(round(iw * ss)))
    H = max(1, int(round(ih * ss)))
    p = np.asarray(pos, dtype=float) * ss
    p = p[np.isfinite(p)]
    line = np.round(p).astype(np.int64)
    hw = max(0, int(round(width * ss / 2)))
    lo = int(round(min(span_lo, span_hi) * ss))
    hi = int(round(max(span_lo, span_hi) * ss))

    n_lines = W if vertical else H
    line_cov = np.zeros(n_lines, dtype=np.int64)
    for d in range(-hw, hw + 1):
        c = line + d
        m = (c >= 0) & (c < n_lines)
        if m.any():
            line_cov += np.bincount(c[m], minlength=n_lines)

    cov = np.zeros((H, W), dtype=np.int64)
    if vertical:
        r0 = max(0, min(lo, H)); r1 = max(0, min(hi, H))
        cov[r0:r1, :] += line_cov[None, :]
    else:
        c0 = max(0, min(lo, W)); c1 = max(0, min(hi, W))
        cov[:, c0:c1] += line_cov[:, None]
    return _compose(cov, rgb, alpha, iw, ih, W, H)
