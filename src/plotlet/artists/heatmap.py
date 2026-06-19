"""Categorical heatmap artist.

User-facing categorical x × y. Cells are drawn at category band centers
using `ctx.x_scale.bandwidth` (padding=0 so cells render flush against
each other; set by frame_defaults).

This is the artist `c.heatmap(df, ...)` records. The numeric-scale
`c.imshow(matrix, ...)` artist stays separate — that one is for image
data with continuous extents (correlation surfaces, real images, etc.).

Splitting them this way means a categorical heatmap can `share_x` /
`share_y` with any other category-scale panel (bars, strips,
dendrograms with `labels=`) by passing the same category names —
no `[i+0.5]` + `width=1.0` coordinate translation needed.

Rendering branches on size: below `imshow_max_rects` we emit one `<rect>`
per cell (vector-clean, zoomable). Above the threshold we encode the
whole grid as a base64 PNG inside one `<image>` — same fallback shape as
imshow, just keyed on the category-scale extent instead of a numeric one.

For row/column clustering with visual gaps and ordering, call
``c.sectors({cluster: [members], ...}, axis="x" | "y")`` on the panel.
The category scale picks up the implied split positions and inserts a
gap between groups; ``_align_to_scale`` (below) reorders the matrix at
draw time to match the sector cat order, so the input matrix can stay in
its natural order and the user only declares the clustering once.
"""
import base64

from ..registry import ArtistSpec, add_artist
from ..utils import to_list_2d
from .._spec import _D
from .. import _splits
from ..draw import rect, text_path
from ..draw import encode_rgb
from ..draw import colormap_lut, ContinuousNorm
from ..draw import resolve_color


def _hex_to_rgb(h):
    """Parse a resolved #rrggbb or #rgb hex string to (r, g, b) ints."""
    h = h.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rel_luminance(r, g, b):
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _parse_heatmap_input(args, kw):
    """Extract (matrix, cols, rows) from a raw c.heatmap(df, ...) call.

    Accepts a DataFrame (uses .values/.columns/.index), a list-of-lists,
    or a 2-D array.  xticklabels= / yticklabels= override the inferred
    labels.  Both label lists are stringified.
    """
    df = args[0]
    xticklabels = kw.get("xticklabels")
    yticklabels = kw.get("yticklabels")
    if hasattr(df, "values") and hasattr(df, "columns") and hasattr(df, "index"):
        cols = list(df.columns) if xticklabels is None else list(xticklabels)
        rows = list(df.index)   if yticklabels is None else list(yticklabels)
        matrix = to_list_2d(df.values)
    else:
        matrix = to_list_2d(df)
        n_rows = len(matrix); n_cols = len(matrix[0]) if matrix else 0
        cols = list(xticklabels) if xticklabels is not None else list(range(n_cols))
        rows = list(yticklabels) if yticklabels is not None else list(range(n_rows))
    return matrix, [str(x) for x in cols], [str(x) for x in rows]


def _png_for_blocks(ctx, cols, rows, bw, bh, rgb_at):
    """Emit one `<image>` per (row-block × col-block) cell-flush region.

    Reads block boundaries straight off the shared scales — this is the
    only place that needs them, and the scale's `.splits` are always in
    display order even when a peer artist (dendrogram) drove the cats
    order. `_splits.block_bboxes_2d` yields a single full-range block
    when no splits are set, so this is also the no-split fallback — one
    PNG covering all cells.
    """
    out = []
    for r0, r1, c0, c1, sy_t, sy_b, sx_l, sx_r in _splits.block_bboxes_2d(
            ctx, rows, cols, bw, bh,
            ctx.y_scale.splits, ctx.x_scale.splits):
        buf = bytearray()
        for r in range(r0, r1):
            for c in range(c0, c1):
                rr, gg, bb = rgb_at(r, c)
                buf.append(rr); buf.append(gg); buf.append(bb)
        png = encode_rgb(bytes(buf), c1 - c0, r1 - r0)
        b64 = base64.b64encode(png).decode("ascii")
        out.append(f'<image x="{sx_l:.3f}" y="{sy_t:.3f}" '
                   f'width="{sx_r - sx_l:.3f}" height="{sy_b - sy_t:.3f}" '
                   f'preserveAspectRatio="none" image-rendering="pixelated" '
                   f'href="data:image/png;base64,{b64}"/>')
    return out


def _heatmap_frame_defaults(args, kw):
    _, cols, rows = _parse_heatmap_input(args, kw)
    # `order=` provides the heatmap's first-seen order as a default — it
    # routes to `*_order_default` via the frame-default tagging in core,
    # so a peer artist's `axis_order` (e.g. a clustering dendrogram) and
    # any categorical ``c.sectors(...)`` can override.
    out = [
        ("xscale", ["category"], {"order": cols, "padding": 0}),
        ("yscale", ["category"], {"order": rows, "padding": 0}),
        ("xticks", [None], {"marks": False}),
        ("yticks", [None], {"marks": False}),
    ]
    # Default `border=False` — the colored cells alone define the data
    # block, which is the typical look when wrapping the heatmap with
    # annotation strips. Pass `border=True` to draw the axis-spine
    # rectangle.
    if not kw.get("border", False):
        out.append(("spines", [], {"top": False, "right": False,
                                   "bottom": False, "left": False}))
    return out


def _heatmap_record(args, kw):
    matrix, cols, rows = _parse_heatmap_input(args, kw)
    nrows  = len(matrix)
    ncols  = len(matrix[0]) if matrix else 0
    if nrows != len(rows) or (matrix and ncols != len(cols)):
        raise ValueError(
            f"heatmap: matrix shape ({nrows}x{ncols}) doesn't match "
            f"labels (rows={len(rows)}, cols={len(cols)})"
        )
    opts = {k: v for k, v in kw.items()
            if k not in ("xticklabels", "yticklabels", "border")}

    base: dict = {}
    palette = opts.get("palette")
    if palette is not None:
        return {"type": "heatmap", "_matrix": matrix, "_cols": cols, "_rows": rows,
                "_nrows": nrows, "_ncols": ncols, "_is_categorical": True,
                "_palette": palette, "opts": opts, **base}

    vmin = opts.get("vmin"); vmax = opts.get("vmax")
    norm = opts.get("norm", "linear")
    if vmin is None or vmax is None:
        if norm == "log":
            flat = [v for row in matrix for v in row if v is not None and v == v and v > 0]
        else:
            flat = [v for row in matrix for v in row if v is not None and v == v]
        if flat:
            if vmin is None: vmin = min(flat)
            if vmax is None: vmax = max(flat)
        else:
            vmin, vmax = (1.0, 10.0) if norm == "log" else (0.0, 1.0)
    return {"type": "heatmap", "_matrix": matrix, "_cols": cols, "_rows": rows,
            "_nrows": nrows, "_ncols": ncols, "_vmin": vmin, "_vmax": vmax,
            "opts": opts, **base}


def _heatmap_xdomain(a): return list(a["_cols"])
def _heatmap_ydomain(a): return list(a["_rows"])


def _align_to_scale(a, ctx):
    """Return `(cols, rows, matrix, annot)` in scale display order.

    Heatmap's record stores everything in its own first-seen clustered
    order. When a peer artist (e.g. a clustering dendrogram) wins the
    axis via `axis_order`, `ctx.x_scale.cats` differs from `a["_cols"]`
    — we reorder matrix + custom annot once here so the rest of draw
    can index by position. Fast path (no copy) when the scale agrees.
    """
    cols = ctx.x_scale.cats
    rows = ctx.y_scale.cats
    matrix = a["_matrix"]
    annot = a["opts"].get("annot")
    if cols == a["_cols"] and rows == a["_rows"]:
        return cols, rows, matrix, annot
    col_pos = {c: i for i, c in enumerate(a["_cols"])}
    row_pos = {r: i for i, r in enumerate(a["_rows"])}
    cp = [col_pos[c] for c in cols]
    rp = [row_pos[r] for r in rows]
    matrix = [[a["_matrix"][rp[r]][cp[c]] for c in range(len(cols))]
              for r in range(len(rows))]
    if annot not in (None, True, False):
        a_orig = to_list_2d(annot)
        annot = [[a_orig[rp[r]][cp[c]] for c in range(len(cols))]
                 for r in range(len(rows))]
    return cols, rows, matrix, annot


def _heatmap_draw_categorical(a, ctx):
    cols, rows, matrix, annot_arg = _align_to_scale(a, ctx)
    nrows = len(rows); ncols = len(cols)
    if nrows == 0 or ncols == 0:
        return ""
    opts = a["opts"]
    palette = {k: resolve_color(v) for k, v in a["_palette"].items()}
    absent_fill = resolve_color(opts.get("absent_fill", "#eeeeee"))

    bw = ctx.x_scale.bandwidth
    bh = ctx.y_scale.bandwidth
    lw = opts.get("linewidth", 0)
    lc = resolve_color(opts.get("linecolor", "white")) if lw else None
    use_rects = nrows * ncols <= _D["imshow_max_rects"]
    out = []

    if use_rects:
        for r in range(nrows):
            cy = ctx.y_scale(rows[r])
            y0 = cy - bh / 2
            for c in range(ncols):
                cx = ctx.x_scale(cols[c])
                x0 = cx - bw / 2
                v = matrix[r][c]
                fill = palette.get(v, absent_fill) if v is not None else absent_fill
                if lw:
                    out.append(rect(x0, y0, bw, bh, fill=fill,
                                    stroke=lc, stroke_width=lw,
                                    project=ctx.warp))
                else:
                    out.append(rect(x0, y0, bw, bh, fill=fill,
                                    project=ctx.warp))
    else:
        rgb_map = {k: _hex_to_rgb(v) for k, v in palette.items()}
        absent_rgb = _hex_to_rgb(absent_fill)
        def rgb_at(r, c):
            v = matrix[r][c]
            return rgb_map.get(v, absent_rgb) if v is not None else absent_rgb
        out.extend(_png_for_blocks(ctx, cols, rows, bw, bh, rgb_at))

    annot = annot_arg
    if annot is not False and annot is not None:
        label_source = matrix if annot is True else to_list_2d(annot)
        if len(label_source) != nrows or (label_source and len(label_source[0]) != ncols):
            raise ValueError(
                f"heatmap: annot array shape ({len(label_source)}x"
                f"{len(label_source[0]) if label_source else 0}) "
                f"doesn't match data ({nrows}x{ncols})"
            )
        fontsize = opts.get("annot_fontsize", 10)
        color_opt = opts.get("annot_color", "auto")
        for r in range(nrows):
            cy = ctx.y_scale(rows[r])
            for c in range(ncols):
                label = label_source[r][c]
                if label is None:
                    continue
                txt = str(label)
                if color_opt == "auto":
                    v = matrix[r][c]
                    fill_hex = palette.get(v, absent_fill) if v is not None else absent_fill
                    rr, gg, bb = _hex_to_rgb(fill_hex)
                    txt_col = "#ffffff" if _rel_luminance(rr, gg, bb) < 0.55 else "#000000"
                else:
                    txt_col = color_opt
                cx = ctx.x_scale(cols[c])
                ax, ay = cx, cy + fontsize / 3
                if ctx.warp is not None:
                    ax, ay = ctx.warp(ax, ay)
                out.append(text_path(txt, ax, ay,
                                     fontsize, anchor="middle", color=txt_col))

    return "".join(out)


def _heatmap_draw(a, ctx):
    if a.get("_is_categorical"):
        return _heatmap_draw_categorical(a, ctx)

    cols, rows, matrix, annot_arg = _align_to_scale(a, ctx)
    nrows = len(rows); ncols = len(cols)
    if nrows == 0 or ncols == 0:
        return ""
    opts = a["opts"]
    norm = ContinuousNorm(a["_vmin"], a["_vmax"],
                           kind=opts.get("norm", "linear"),
                           center=opts.get("center"))
    lut = colormap_lut(opts.get("cmap", _D["default_cmap"]))
    absent_fill = resolve_color(opts.get("absent_fill", "#eeeeee"))
    absent_rgb  = _hex_to_rgb(absent_fill)

    bw = ctx.x_scale.bandwidth
    bh = ctx.y_scale.bandwidth
    lw = opts.get("linewidth", 0)
    lc = resolve_color(opts.get("linecolor", "white")) if lw else None
    use_rects = nrows * ncols <= _D["imshow_max_rects"]
    out = []

    if use_rects:
        for r in range(nrows):
            cy = ctx.y_scale(rows[r])
            y0 = cy - bh / 2
            for c in range(ncols):
                cx = ctx.x_scale(cols[c])
                x0 = cx - bw / 2
                v = matrix[r][c]
                if v is None or v != v:
                    fill = absent_fill
                else:
                    i = int(norm.to_unit(v) * 255 + 0.5) * 3
                    fill = f"rgb({lut[i]},{lut[i+1]},{lut[i+2]})"
                if lw:
                    out.append(rect(x0, y0, bw, bh, fill=fill,
                                    stroke=lc, stroke_width=lw,
                                    project=ctx.warp))
                else:
                    out.append(rect(x0, y0, bw, bh, fill=fill,
                                    project=ctx.warp))
    else:
        # Category-scale PNG fallback. `_png_for_blocks` covers the
        # no-split case as a single full-range block — one image flush
        # across all cells.
        def rgb_at(r, c):
            v = matrix[r][c]
            if v is None or v != v:
                return absent_rgb
            i = int(norm.to_unit(v) * 255 + 0.5) * 3
            return lut[i], lut[i + 1], lut[i + 2]
        out.extend(_png_for_blocks(ctx, cols, rows, bw, bh, rgb_at))

    annot = annot_arg
    if annot is not False and annot is not None:
        # Same convention as imshow: `True` → format the cell value;
        # 2-D array → use the supplied labels (numbers via `fmt`,
        # strings verbatim). Text color "auto" picks black/white from
        # the cell's rendered luminance so labels stay readable.
        label_source = matrix if annot is True else to_list_2d(annot)
        if len(label_source) != nrows or (label_source and len(label_source[0]) != ncols):
            raise ValueError(
                f"heatmap: annot array shape ({len(label_source)}x"
                f"{len(label_source[0]) if label_source else 0}) "
                f"doesn't match data ({nrows}x{ncols})"
            )
        fmt = opts.get("fmt", ".2g")
        color_opt = opts.get("annot_color", "auto")
        fontsize = opts.get("annot_fontsize", 10)
        for r in range(nrows):
            cy = ctx.y_scale(rows[r])
            for c in range(ncols):
                label = label_source[r][c]
                if label is None or (isinstance(label, float) and label != label):
                    continue
                txt = format(label, fmt) if isinstance(label, (int, float)) \
                      else str(label)
                if color_opt == "auto":
                    v = matrix[r][c]
                    if v is None or v != v:
                        txt_col = "#ffffff" if _rel_luminance(*absent_rgb) < 0.55 else "#000000"
                    else:
                        i = int(norm.to_unit(v) * 255 + 0.5) * 3
                        if _rel_luminance(lut[i], lut[i+1], lut[i+2]) < 0.55:
                            txt_col = "#ffffff"
                        else:
                            txt_col = "#000000"
                else:
                    txt_col = color_opt
                cx = ctx.x_scale(cols[c])
                ax, ay = cx, cy + fontsize / 3
                if ctx.warp is not None:
                    ax, ay = ctx.warp(ax, ay)
                out.append(text_path(txt, ax, ay,
                                     fontsize, anchor="middle", color=txt_col))

    return "".join(out)


def _heatmap_legend_entries(a):
    if not a.get("_is_categorical"):
        return []
    palette = a["_palette"]
    legend_opts = a["opts"].get("legend") or {}
    order = legend_opts.get("order", list(palette.keys()))
    return [{"label": str(k), "color": resolve_color(palette[k])}
            for k in order if k in palette]


def _heatmap_legend_gradient(a):
    if a.get("_is_categorical"):
        return None
    legend_opts = a["opts"].get("legend") or {}
    return {
        "kind": "continuous",
        "cmap": a["opts"].get("cmap", _D["default_cmap"]),
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "norm": a["opts"].get("norm", "linear"),
        "center": a["opts"].get("center"),
        "label": legend_opts.get("label"),
        "ticks": legend_opts.get("ticks"),
    }


def _heatmap_data_attrs(a):
    if a.get("_is_categorical"):
        return {
            "rows": a["_nrows"],
            "cols": a["_ncols"],
            "mode": "categorical",
            "categories": list(a["_palette"].keys()),
        }
    out = {
        "rows": a["_nrows"],
        "cols": a["_ncols"],
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "cmap": a["opts"].get("cmap", _D["default_cmap"]),
        "data-encoding": "png-embedded" if (a["_nrows"] * a["_ncols"]
                                            > _D["imshow_max_rects"]) else "rects",
    }
    norm = a["opts"].get("norm", "linear")
    if norm != "linear":
        out["norm"] = norm
    center = a["opts"].get("center")
    if center is not None:
        out["center"] = float(center)
    annot = a["opts"].get("annot", False)
    if annot is not False and annot is not None:
        out["annot"] = "values" if annot is True else "custom"
    return out


add_artist(ArtistSpec(
    name="heatmap",
    accepts_data_positional=False,
    record=_heatmap_record,
    xdomain=_heatmap_xdomain,
    ydomain=_heatmap_ydomain,
    draw=_heatmap_draw,
    legend_entries=_heatmap_legend_entries,
    legend_gradient=_heatmap_legend_gradient,
    frame_defaults=_heatmap_frame_defaults,
    uses_color_cycle=False,
    data_attrs=_heatmap_data_attrs,
    tight_domain=True,
    coord_native=True,
))
