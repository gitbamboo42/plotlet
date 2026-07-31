"""Helpers shared across 2+ per-artist files.

Each built-in artist registers one of the `*_legend_entries` functions so
the legend dispatch in `_render_inner` can stay generic — no type-string matching.
Paint logic is a nested closure; there are no shared swatch helpers.

The `pool_*` / `rgb_buffer` helpers back the PNG-embedded raster paths of
imshow and heatmap: a grid denser than the display can show is box-pooled
down before encoding. All pooling rules are deterministic (fixed bin
edges, fixed iteration order, first-seen tie-breaks), so the
byte-identical-SVG guarantee holds.
"""
import math

import numpy as np

from .._spec import _LEGSPEC, _D
from ..draw import marker, segment, rect
from ..draw import TAB10
from ..utils import to_list, resolve_aes, palette_color


def pool_target(n_cells, px):
    """Output-pixel count along one raster axis: full data resolution
    until cells outnumber `raster_oversample` per display pixel, then
    capped at that. The oversample headroom keeps hi-dpi rendering and
    moderate zoom sharp; past it the viewer can't show the extra cells
    anyway, and its nearest-neighbour downscale would *subsample* them
    (drop cells) where pooling summarizes them."""
    cap = max(1, math.ceil(px * _D["raster_oversample"]))
    return n_cells if n_cells <= cap else cap


def pool_mean(values):
    """NaN/None-ignoring mean of one pooling bin; an all-absent bin → NaN
    (renders as the artist's absent color, like a NaN cell)."""
    fin = [v for v in values if v is not None and v == v]
    if not fin:
        return float("nan")
    return sum(fin) / len(fin)


def pool_mode(values):
    """Most frequent value in one pooling bin, for categorical cells
    (a mean of category labels is meaningless). NaN folds into None —
    both render as absent. Ties break to the first-seen value."""
    counts = {}
    for v in values:
        if isinstance(v, float) and v != v:
            v = None
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def pool_grid(matrix, out_h, out_w, pool):
    """Box-pool a `[row][col]` grid down to `out_h × out_w`. Bin edges by
    integer rounding; every bin is non-empty because `out_* <= n_*`."""
    nrows = len(matrix)
    ncols = len(matrix[0])
    re = [nrows * i // out_h for i in range(out_h + 1)]
    ce = [ncols * j // out_w for j in range(out_w + 1)]
    return [[pool([matrix[r][c]
                   for r in range(re[i], re[i + 1])
                   for c in range(ce[j], ce[j + 1])])
             for j in range(out_w)]
            for i in range(out_h)]


def rgb_buffer(grid, rgb_of):
    """Flatten a `[row][col]` value grid into a packed RGB byte buffer
    via `rgb_of(value) -> (r, g, b)` — the input `image_png` expects."""
    buf = bytearray()
    for row in grid:
        for v in row:
            r, g, b = rgb_of(v)
            buf.append(r); buf.append(g); buf.append(b)
    return buf


def minmax_grid(d, lo, hi):
    """NaN/None-ignoring min/max over a 2-D cell grid, for autoscale.
    Fills only the unset bounds; returns `(lo, hi, found)` where `found`
    says whether any finite cell existed (callers keep their empty-grid
    defaults). Vectorized — min/max are comparisons, not arithmetic, so
    the result is exact; a ±0.0 tie canonicalizes to +0.0 (`x + 0.0`)
    so it can't depend on scan order. Non-numeric cells fall back to
    the scalar scan."""
    try:
        a = np.asarray(d, dtype=np.float64)     # None cells → NaN
    except (TypeError, ValueError):
        flat = [v for row in d for v in row if v is not None and v == v]
        if flat:
            if lo is None: lo = min(flat)
            if hi is None: hi = max(flat)
        return lo, hi, bool(flat)
    if bool(np.isnan(a).all()):
        return lo, hi, False
    if lo is None: lo = float(np.nanmin(a)) + 0.0
    if hi is None: hi = float(np.nanmax(a)) + 0.0
    return lo, hi, True


def _pool_mean_np(a, out_h, out_w):
    """`pool_grid(..., pool_mean)` vectorized: box-pool a 2-D float
    array to `out_h × out_w` by NaN-ignoring mean.

    Bit-identical to the scalar path by construction: cells are added
    in the same row-major order (vectorized *across* bins, sequential
    *within* each bin via the offset loop), NaN adds 0.0 — exact, since
    `x + 0.0 == x` — and one final division mirrors `sum(fin)/len(fin)`.
    Only elementwise ops: `np.sum`/`np.mean` pairwise summation is a
    numpy implementation detail that may change across versions, which
    would break byte-identical SVG across machines."""
    nrows, ncols = a.shape
    re = np.array([nrows * i // out_h for i in range(out_h + 1)])
    ce = np.array([ncols * j // out_w for j in range(out_w + 1)])
    r0, rl = re[:-1], np.diff(re)
    c0, cl = ce[:-1], np.diff(ce)
    valid = ~np.isnan(a)
    vals = np.where(valid, a, 0.0)
    acc = np.zeros((out_h, out_w))
    cnt = np.zeros((out_h, out_w), dtype=np.int64)
    for dr in range(int(rl.max())):
        ri = np.nonzero(dr < rl)[0]
        row_v = vals[r0[ri] + dr]       # gather rows once per offset
        row_m = valid[r0[ri] + dr]
        for dc in range(int(cl.max())):
            ci = np.nonzero(dc < cl)[0]
            dst = np.ix_(ri, ci)
            acc[dst] += row_v[:, c0[ci] + dc]
            cnt[dst] += row_m[:, c0[ci] + dc]
    return np.divide(acc, cnt, out=np.full((out_h, out_w), np.nan),
                     where=cnt > 0)


def png_value_cells(rows, out_h, out_w, norm, lut, absent_rgb):
    """Vectorized pool + colormap for a numeric cell grid → `(rgb_bytes,
    downsampled)`, or None when the norm only has a scalar form (log) —
    the caller then falls back to `pool_grid` + `rgb_buffer`. `rows` is
    a nested list (None/NaN cells → absent color) or a 2-D ndarray."""
    if norm.kind == "log":
        return None
    a = np.asarray(rows, dtype=np.float64)      # None cells → NaN
    downsampled = (out_h, out_w) != a.shape
    if downsampled:
        a = _pool_mean_np(a, out_h, out_w)
    u = norm.to_unit_array(a)
    nan_mask = np.isnan(u)
    # Same rounding as the scalar `int(u * 255 + 0.5)`: values are
    # >= 0 after clipping, so trunc-toward-zero == floor.
    idx = (np.where(nan_mask, 0.0, u) * 255.0 + 0.5).astype(np.int64)
    rgb = np.frombuffer(bytes(lut), dtype=np.uint8).reshape(256, 3)[idx]
    if nan_mask.any():
        rgb[nan_mask] = absent_rgb
    return rgb.tobytes(), downsampled


# Used by long-form expansion for `linestyle=` and `alpha=` column splits.
LINESTYLE_CYCLE = (None, "--", ":", "-.")
DEFAULT_ALPHA_RANGE = (0.3, 1.0)


def band_rect(band_lo, band_size, p0, p1, *, horizontal):
    """One positioned rect in (band, value) pixel space → `(x, y, w, h)`
    for `draw.rect`. `band_lo`/`band_size` span the categorical/bin axis;
    `p0`/`p1` are the value-axis pixel pair in either order (stack run,
    base→value). `horizontal` swaps which screen axis is which. Shared by
    bar's and hist's stack/fill/dodge loops so their rect geometry can't
    drift apart."""
    lo, hi = (p0, p1) if p0 <= p1 else (p1, p0)
    if horizontal:
        return lo, band_lo, hi - lo, band_size
    return band_lo, lo, band_size, hi - lo


def _alpha_for_level(idx, n_levels, alphas):
    """Map a discrete level index to an alpha within `alphas` (a `(lo, hi)`
    tuple). One level → high end; otherwise linearly spaced."""
    lo, hi = alphas
    if n_levels <= 1:
        return hi
    return lo + (hi - lo) * idx / (n_levels - 1)


def expand_xy_long_form(kind, data, x_col, y_col,
                        color, group, linestyle, alpha,
                        palette, alphas, base_opts):
    """Long-form xy table → list of artist record dicts split by
    `(color, group, linestyle, alpha)` tuples. One record per unique tuple,
    each carrying its own `color`/`linestyle`/`alpha`/`label`. Shared by
    artists that draw one series per record (line, scatter).

    Returns a list of dicts shaped `{"type": kind, "xs": [...], "ys": [...],
    "opts": {...}}`. Single-record fast path when all four aesthetics are
    literal (or absent). `base_opts` is the leftover kwargs after popping
    the long-form aesthetic keys."""
    color_kind, color_value = resolve_aes(data, color)
    group_kind, group_value = resolve_aes(data, group)
    ls_kind,    ls_value    = resolve_aes(data, linestyle)
    alpha_kind, alpha_value = resolve_aes(data, alpha)
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    n = len(xs_all)

    if (color_kind == "literal" and group_kind == "literal"
            and ls_kind == "literal" and alpha_kind == "literal"):
        opts = dict(base_opts)
        if color_value is not None: opts["color"] = color_value
        if ls_value is not None: opts["linestyle"] = ls_value
        if alpha_value is not None: opts["alpha"] = alpha_value
        return [{"type": kind, "xs": xs_all, "ys": ys_all, "opts": opts}]

    color_vec = color_value if color_kind == "column" else [None] * n
    group_vec = group_value if group_kind == "column" else [None] * n
    ls_vec    = ls_value    if ls_kind    == "column" else [None] * n
    alpha_vec = alpha_value if alpha_kind == "column" else [None] * n
    color_levels = list(dict.fromkeys(color_vec))
    ls_levels    = list(dict.fromkeys(ls_vec))
    alpha_levels = list(dict.fromkeys(alpha_vec))
    quads = list(dict.fromkeys(zip(color_vec, group_vec, ls_vec, alpha_vec)))

    base_opts.pop("label", None)  # column-driven grouping overrides any user label
    records = []
    labeled: set = set()
    for ck, gk, lk, ak in quads:
        idxs = [j for j in range(n)
                if color_vec[j] == ck and group_vec[j] == gk
                and ls_vec[j] == lk and alpha_vec[j] == ak]
        xs_g = [xs_all[j] for j in idxs]
        ys_g = [ys_all[j] for j in idxs]
        opts = dict(base_opts)
        if color_kind == "column":
            idx = color_levels.index(ck)
            opts["color"] = palette_color(palette, ck, idx) or TAB10[idx % 10]
            if ck not in labeled:
                opts["label"] = str(ck)
                labeled.add(ck)
        elif color_value is not None:
            opts["color"] = color_value
        if ls_kind == "column":
            ls = LINESTYLE_CYCLE[ls_levels.index(lk) % len(LINESTYLE_CYCLE)]
            if ls is not None:
                opts["linestyle"] = ls
        elif ls_value is not None:
            opts["linestyle"] = ls_value
        if alpha_kind == "column":
            opts["alpha"] = _alpha_for_level(alpha_levels.index(ak),
                                              len(alpha_levels), alphas)
        elif alpha_value is not None:
            opts["alpha"] = alpha_value
        records.append({"type": kind, "xs": xs_g, "ys": ys_g, "opts": opts})
    # The raster/simplify thresholds gate on the artist call's total mark
    # count, not each fan-out slice — ten 10k-point groups strain the
    # renderer exactly like one 100k-point series.
    for rec in records:
        rec["opts"]["_fanout_n"] = n
    return records


_CURVE_VALUES = ("linear", "step-before", "step-after", "step-mid")


def _step_coords(xs, ys, mode):
    """Interleave (xs, ys) into step-shaped coordinates.

    `mode` is one of 'before' | 'after' | 'mid'. NaN values pass through
    unchanged — the path-building stage breaks the stroke at them, so
    gaps don't get bridged by a phantom step."""
    n = len(xs)
    if n < 2:
        return list(xs), list(ys)
    out_x = [xs[0]]
    out_y = [ys[0]]
    for i in range(1, n):
        x0, x1 = xs[i - 1], xs[i]
        y0, y1 = ys[i - 1], ys[i]
        if mode == "before":
            out_x.append(x0); out_y.append(y1)
        elif mode == "after":
            out_x.append(x1); out_y.append(y0)
        else:  # mid
            mid = (x0 + x1) / 2
            out_x.append(mid); out_y.append(y0)
            out_x.append(mid); out_y.append(y1)
        out_x.append(x1); out_y.append(y1)
    return out_x, out_y


def _xy_minmax(xs, ys):
    """Min/max for an x/y series, ignoring NaN. Returns dict ready to merge
    into a data_attrs result."""
    fxs = [x for x in xs if isinstance(x, (int, float)) and x == x]
    fys = [y for y in ys if isinstance(y, (int, float)) and y == y]
    out = {}
    if fxs:
        out["x-min"] = min(fxs)
        out["x-max"] = max(fxs)
    if fys:
        out["y-min"] = min(fys)
        out["y-max"] = max(fys)
    return out


def _line_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        out = segment(x0, y_mid, x0 + sw, y_mid,
                      color=a["_color"],
                      width=a["opts"].get("linewidth", ctx.defaults["linewidth"]),
                      dash=a["opts"].get("linestyle"))
        if a["opts"].get("marker"):
            out += marker(a["opts"]["marker"], x0 + sw / 2, y_mid,
                          a["opts"].get("markersize", ctx.defaults["markersize"]),
                          a["_color"], 1)
        return out
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _refline_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return segment(x0, y_mid, x0 + sw, y_mid,
                       color=a["_color"],
                       width=a["opts"].get("linewidth", ctx.defaults["refline_width"]),
                       dash=a["opts"].get("linestyle"))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _bar_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return rect(x0, y_mid - 5, sw, 10, fill=a["_color"],
                    alpha=a["opts"].get("alpha", 1))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def _refspan_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        sw = _LEGSPEC["swatch_width"]
        return rect(x0, y_mid - 5, sw, 10, fill=a["_color"],
                    alpha=a["opts"].get("alpha", ctx.defaults["refspan_alpha"]))
    return [{"label": label, "color": a.get("_color"), "paint": paint}]
