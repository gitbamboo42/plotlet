"""Heatmap artist — tidy/long input, continuous or categorical x.

Input is a **tidy table** (dict-of-columns or DataFrame), like `scatter`:
``c.heatmap(data=df, x="x", values=["a", "b"])``. Each table **row**
becomes one heatmap **column** (its x-position from the `x` column); each
**value column** becomes one heatmap **row** (a track). `values=`
picks/orders the tracks; by default every column except `x`/`sector` is a
track. A bare matrix is *not* accepted — reshape it into a table first.

The `x` column's dtype picks the x-axis: **numeric → continuous** (a
linear scale; cell edges inferred as neighbour midpoints, so uneven
spacing works), **string → categorical** band labels. The y-axis (the
tracks) is always categorical. A continuous-x heatmap `share_x`-aligns to
a scatter/line on the same numeric scale — the annotation-track shape.
Every cell feature is dtype-independent: NaN/None → `absent_fill`, cell
borders, annotations, discrete `palette=`, and circular warp via
`project=ctx.warp`.

Sectors: pass `sector=` (a column of per-column group tags) with a
panel-level ``c.sectors(Sectors(...), axis="x", column=...)``. The
framework's sector remap tags each column's x into its sector, and cell
edges are grouped per sector so gaps fall between sector groups.

`c.imshow(matrix, ...)` stays separate — a pure image blitter (uniform
pixels, no per-cell styling, no warp, no labels) for real image /
dense-array data. Reach for heatmap when you need labels, missing-value
handling, borders, or a non-affine coordinate; imshow when you just want
pixels from a matrix.

Rendering branches on size: below `imshow_max_rects` we emit one `<rect>`
per cell (vector-clean, zoomable). Above the threshold we encode the grid
as a base64 PNG inside one `<image>` — `_png_for_blocks` for a categorical
x (honours sector splits), a single imshow-style image for a continuous x
— except when a flat image can't represent the geometry (a warp, uneven
or sector-tagged continuous cells, y sector splits): `_use_rects` then
keeps the per-cell rects at any size.

For categorical-x clustering with visual gaps and ordering, call
``c.sectors({cluster: [members], ...}, axis="x" | "y")`` on the panel.
The category scale picks up the implied split positions and inserts a
gap between groups; ``_resolve_display`` (below) reorders the matrix at
draw time to match the sector cat order.
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list_2d, to_list, all_numeric, _data_has_column
from ..sectors import SectoredValue
from .._spec import _D
from .. import _splits
from ..draw import rect, text_path
from ..draw import image_png
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


def _centers_to_edges(positions):
    """Cell-center coordinates → `n+1` cell edges (matplotlib pcolormesh
    center→edge rule). Interior edges are neighbor midpoints; the two
    outer edges are extrapolated so the first/last cell is symmetric
    about its center. Handles uneven spacing. A single center falls back
    to unit width.
    """
    p = list(positions)
    n = len(p)
    if n == 1:
        return [p[0] - 0.5, p[0] + 0.5]
    inner = [(p[i] + p[i + 1]) / 2 for i in range(n - 1)]
    return [2 * p[0] - inner[0], *inner, 2 * p[-1] - inner[-1]]


def _cell_edges(positions):
    """Per-cell `(left, right)` edges from cell centers.

    Plain numbers → neighbour midpoints, so adjacent cells share a
    boundary and render flush (same geometry as `_centers_to_edges`).

    `SectoredValue`-tagged centers (a sectored x-axis, tagged upstream by
    the framework's sector remap) → edges are inferred **within each
    sector** and re-tagged with the cell's sector index. A cell therefore
    never bridges a sector gap: the boundary between two columns is only
    shared when both belong to the same sector; at a sector change each
    side gets its own symmetric edge, and `_SectoredLinearScale` renders
    the gap between them.
    """
    p = list(positions)
    n = len(p)
    if n == 0:
        return []
    if not isinstance(p[0], SectoredValue):
        e = _centers_to_edges(p)
        return [(e[i], e[i + 1]) for i in range(n)]

    def in_sector(i, j):
        return 0 <= j < n and p[j].sector_idx == p[i].sector_idx

    out = []
    for i in range(n):
        idx = p[i].sector_idx
        left_half = (p[i] - p[i - 1]) / 2 if in_sector(i, i - 1) else None
        right_half = (p[i + 1] - p[i]) / 2 if in_sector(i, i + 1) else None
        if left_half is None:
            left_half = right_half if right_half is not None else 0.5
        if right_half is None:
            right_half = left_half
        left = float(p[i]) - left_half
        right = float(p[i]) + right_half
        out.append((SectoredValue(left, idx), SectoredValue(right, idx)))
    return out


def _columns_of(data):
    """Ordered column names of a tidy table (DataFrameLite or dict)."""
    if hasattr(data, "columns"):
        return list(data.columns)
    return list(data.keys())


_HEATMAP_USAGE = (
    "heatmap requires tidy input: "
    "c.heatmap(data=df, x='col'[, sector='group', values=[...]]). "
    "A bare matrix must be reshaped into a table first."
)

# Column-selection kwargs consumed before opts, plus every opt the draw /
# legend / attrs paths read. Anything outside these (and the ignored aes
# below) is a typo or a stale call shape — reject it loudly.
_HEATMAP_KWARGS = {
    "data", "x", "sector", "values", "border",
    "cmap", "vmin", "vmax", "norm", "center", "palette", "absent_fill",
    "legend", "annot", "fmt", "annot_color", "annot_fontsize",
    "linewidth", "linecolor", "label",
}
# Chart-level aes injected into every artist call (`pt.chart(df, y=...,
# color=...)`); heatmap doesn't use these, so drop them instead of
# rejecting — a chart-level binding meant for peer marks must not break
# the heatmap layer.
_HEATMAP_IGNORED_AES = {"y", "color", "fill", "group", "linestyle"}


def _resolve_columns(kw):
    """Validate the tidy kwargs and resolve `(data, xs, values)` without
    materializing the value columns — all `frame_defaults` needs, and it
    regenerates on every replay, so the matrix copy stays out of it.

    `values=[...]` picks/orders the value columns; by default every
    column except `x`/`sector` is a track, in first-appearance order.
    """
    data = kw.get("data")
    x_col = kw.get("x")
    if data is None or x_col is None:
        raise TypeError(_HEATMAP_USAGE)
    sector_col = kw.get("sector")
    for name in (x_col, sector_col):
        if name is not None and not _data_has_column(data, name):
            raise ValueError(f"heatmap: column {name!r} is not in data.")
    values = kw.get("values")
    if values is None:
        # `y` may arrive via chart-level aes inheritance; heatmap has no
        # y column, so keep it out of the default tracks.
        skip = {x_col, sector_col, kw.get("y")}
        values = [c for c in _columns_of(data) if c not in skip]
    else:
        for v in values:
            if not _data_has_column(data, v):
                raise ValueError(f"heatmap: value column {v!r} is not in data.")
    if not values:
        raise ValueError("heatmap: no value columns — need at least one track.")
    return data, to_list(data[x_col]), list(values)


def _parse_heatmap_input(kw):
    """Tidy table → `(matrix, xs, tracks)`.

    Each **row** of the table becomes one heatmap **column** (its
    x-position from the `x` column); each **value column** becomes one
    heatmap **row** (a track). So `matrix[track][position]`, `xs` are the
    per-column x values (numeric → continuous axis, strings → categorical
    labels), and `tracks` are the value-column names (the y labels).
    """
    data, xs, values = _resolve_columns(kw)
    matrix = [to_list(data[v]) for v in values]      # [track][position]
    return matrix, xs, [str(v) for v in values]


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
        out.append(image_png(sx_l, sy_t, sx_r - sx_l, sy_b - sy_t,
                             buf, c1 - c0, r1 - r0))
    return out


def _heatmap_frame_defaults(args, kw):
    _, xs, values = _resolve_columns(kw)
    tracks = [str(v) for v in values]
    # A numeric `x` column → continuous axis: skip the category scale +
    # tick suppression so the default linear scale and numeric ticks
    # apply (those ticks are what visibly align with a shared
    # scatter/line). A string `x` column → categorical labels. The value
    # columns (tracks) are always categorical rows. `order=` provides the
    # heatmap's first-seen order as a default — it routes to
    # `*_order_default` in core, so a peer dendrogram's `axis_order` and
    # any categorical ``c.sectors(...)`` can still override it.
    out = []
    if not all_numeric(xs):
        out.append(("xscale", ["category"],
                    {"order": [str(x) for x in xs], "padding": 0}))
        out.append(("xticks", [None], {"marks": False}))
    out.append(("yscale", ["category"], {"order": tracks, "padding": 0}))
    out.append(("yticks", [None], {"marks": False}))
    # Default `border=False` — the colored cells alone define the data
    # block, which is the typical look when wrapping the heatmap with
    # annotation strips. Pass `border=True` to draw the axis-spine
    # rectangle.
    if not kw.get("border", False):
        out.append(("spines", [], {"top": False, "right": False,
                                   "bottom": False, "left": False}))
    return out


def _sort_by_x(xs, matrix, opts):
    """Put continuous columns in ascending-x order (tidy rows carry no
    order contract; the midpoint edge rule needs monotonic centers).
    A 2-D custom `annot` is `[track][position]` in input order, so it
    permutes along or its labels would land on the wrong cells."""
    order = sorted(range(len(xs)), key=lambda i: float(xs[i]))
    if order == list(range(len(xs))):
        return xs, matrix, opts
    xs = [xs[i] for i in order]
    matrix = [[row[i] for i in order] for row in matrix]
    annot = opts.get("annot")
    if annot not in (None, True, False):
        a2 = to_list_2d(annot)
        opts = dict(opts)
        opts["annot"] = [[r[i] for i in order] for r in a2]
    return xs, matrix, opts


def _heatmap_record(args, kw):
    if args:
        raise TypeError(_HEATMAP_USAGE)
    unknown = set(kw) - _HEATMAP_KWARGS - _HEATMAP_IGNORED_AES
    if unknown:
        raise TypeError(
            f"heatmap: unknown kwarg(s) {', '.join(sorted(unknown))}."
        )
    matrix, xs, rows = _parse_heatmap_input(kw)
    nrows  = len(matrix)                        # tracks
    ncols  = len(matrix[0]) if matrix else 0    # positions
    for row in matrix:
        if len(row) != ncols:
            raise ValueError(
                "heatmap: value columns have unequal length "
                f"(expected {ncols}, got {len(row)})."
            )
    if len(xs) != ncols:
        raise ValueError(
            f"heatmap: x column has {len(xs)} rows but the value columns "
            f"have {ncols}."
        )
    opts = {k: v for k, v in kw.items()
            if k not in ("data", "x", "sector", "values", "border")
            and k not in _HEATMAP_IGNORED_AES}
    # Numeric x column → continuous positioning (edges from cell centers);
    # string x → categorical band labels. y (tracks) is always categorical.
    x_continuous = all_numeric(xs)
    if x_continuous:
        # The midpoint edge rule silently emits overlapping / zero-width /
        # NaN cells for non-finite or repeated centers — reject those, and
        # sort the rest (tidy input arrives in any row order).
        if any(v != v for v in xs):
            raise ValueError("heatmap: x column contains NaN.")
        if len({float(v) for v in xs}) != len(xs):
            raise ValueError("heatmap: x column contains duplicate positions.")
        xs, matrix, opts = _sort_by_x(xs, matrix, opts)
    elif any(v is None for v in xs) and \
            all_numeric([v for v in xs if v is not None]):
        # An otherwise-numeric x with missing entries would silently fall
        # back to categorical bands labeled "None" — make it loud.
        raise ValueError(
            "heatmap: x column mixes numbers and missing values (None)."
        )
    cols = [str(x) for x in xs]
    x_edges = _cell_edges(xs) if x_continuous else None

    base: dict = {"_x_continuous": x_continuous, "_x_edges": x_edges}
    palette = opts.get("palette")
    if palette is not None:
        if not isinstance(palette, dict):
            raise TypeError(
                "heatmap: palette= must be a dict mapping cell value → "
                f"color; got {type(palette).__name__}. (A chart-level "
                "palette list does not apply to heatmap.)"
            )
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


def _heatmap_xdomain(a):
    # Continuous axis → numeric extent (outer cell edges) so the panel
    # builds a linear scale; categorical → the label list.
    if a.get("_x_continuous"):
        edges = a["_x_edges"]
        return [edges[0][0], edges[-1][1]]
    return list(a["_cols"])


def _heatmap_ydomain(a):
    return list(a["_rows"])


def _edges_uniform(edges):
    """True iff continuous cells are equal-width and flush — the
    precondition for the single-`<image>` PNG fallback (which stretches
    one image uniformly across the extent)."""
    if len(edges) <= 1:
        return True
    w0 = edges[0][1] - edges[0][0]
    tol = 1e-9 * (abs(w0) + 1.0)
    return all(abs((r - l) - w0) <= tol for (l, r) in edges) and \
        all(abs(edges[i][1] - edges[i + 1][0]) <= tol
            for i in range(len(edges) - 1))


def _axis_geometry(scale, continuous, edges, cats, n):
    """Per-index `(start_px, size_px)` cell geometry for one axis.

    Categorical: band center ± half the (uniform) bandwidth. Continuous:
    map each cell's own `(left, right)` edges through the scale; `min`/`abs`
    absorb a reversed axis, and a sectored scale drops each edge into its
    tagged sector's pixel strip so gaps fall between sectors.
    """
    if continuous:
        return [(min(scale(l), scale(r)), abs(scale(r) - scale(l)))
                for (l, r) in edges]
    bw = scale.bandwidth
    return [(scale(cats[i]) - bw / 2, bw) for i in range(n)]


def _resolve_display(a, ctx):
    """Reorder matrix + custom annot into scale display order along any
    *categorical* axis, and compute per-cell pixel geometry for both axes.

    Returns `(matrix, annot, xgeom, ygeom, xcats, ycats)`. `xgeom[c]` /
    `ygeom[r]` are `(start_px, size_px)`; `xcats` is the display-order
    label list, or `None` on a continuous x (a linear scale exposes no
    `.cats`, and continuous cell positions are fixed — never reordered by
    a peer). The y axis (tracks) is always categorical. Only categorical
    axes go through the peer-order remap that a clustering dendrogram
    drives via `axis_order`.
    """
    x_cont = a.get("_x_continuous")
    matrix = a["_matrix"]
    annot = a["opts"].get("annot")

    if x_cont and hasattr(ctx.x_scale, "cats"):
        # A category scale maps our numeric edges to NaN — every cell
        # would render invisible. Categorical c.sectors(...) or a peer
        # category artist won the axis; the combination can't work.
        raise ValueError(
            "heatmap: numeric x column on a categorical x scale. "
            "Stringify the x column for categorical bands, or use "
            "continuous pt.Sectors(..., column=...) for sector gaps."
        )
    xcats = None if x_cont else ctx.x_scale.cats
    ycats = ctx.y_scale.cats
    x_reordered = xcats is not None and xcats != a["_cols"]
    y_reordered = ycats != a["_rows"]
    if x_reordered or y_reordered:
        col_pos = {c: i for i, c in enumerate(a["_cols"])}
        row_pos = {r: i for i, r in enumerate(a["_rows"])}
        cp = [col_pos[c] for c in xcats] if x_reordered \
            else list(range(len(a["_cols"])))
        rp = [row_pos[r] for r in ycats] if y_reordered \
            else list(range(len(a["_rows"])))
        matrix = [[a["_matrix"][ri][ci] for ci in cp] for ri in rp]
        if annot not in (None, True, False):
            a_orig = to_list_2d(annot)
            annot = [[a_orig[ri][ci] for ci in cp] for ri in rp]

    ncols = len(matrix[0]) if matrix else 0
    nrows = len(matrix)
    xgeom = _axis_geometry(ctx.x_scale, x_cont, a["_x_edges"], xcats, ncols)
    ygeom = _axis_geometry(ctx.y_scale, False, None, ycats, nrows)
    return matrix, annot, xgeom, ygeom, xcats, ycats


def _use_rects(a, ctx, nrows, ncols):
    """Emit per-cell `<rect>`s (vs one PNG) when below the rect threshold,
    or when the PNG fallback can't represent the geometry: under a warp
    (an `<image>` can't bend into an annular sector), or when a
    continuous-x grid can't use the single stretched image — uneven
    cells, sector-tagged edges, or y sector splits (the uniform image
    would paint over the pixel gaps and shift rows off their bands)."""
    if nrows * ncols <= _D["imshow_max_rects"]:
        return True
    if ctx.warp is not None:
        return True
    if a.get("_x_continuous"):
        edges = a["_x_edges"]
        if edges and isinstance(edges[0][0], SectoredValue):
            return True
        if getattr(ctx.y_scale, "splits", None):
            return True
        if not _edges_uniform(edges):
            return True
    return False


def _png_fallback(ctx, xgeom, ygeom, xcats, ycats, rgb_at):
    """Large-grid PNG path. Fully categorical → `_png_for_blocks` (honours
    sector splits). A continuous x → one uniform `<image>` spanning the
    cell bbox, mirroring imshow; rows/cols are walked in pixel order so a
    reversed or descending axis still lands right."""
    if xcats is not None:
        return _png_for_blocks(ctx, xcats, ycats,
                               xgeom[0][1], ygeom[0][1], rgb_at)
    ncols = len(xgeom); nrows = len(ygeom)
    col_order = sorted(range(ncols), key=lambda c: xgeom[c][0])
    row_order = sorted(range(nrows), key=lambda r: ygeom[r][0])
    sx_l = min(g[0] for g in xgeom); sx_r = max(g[0] + g[1] for g in xgeom)
    sy_t = min(g[0] for g in ygeom); sy_b = max(g[0] + g[1] for g in ygeom)
    buf = bytearray()
    for r in row_order:
        for c in col_order:
            rr, gg, bb = rgb_at(r, c)
            buf.append(rr); buf.append(gg); buf.append(bb)
    return [image_png(sx_l, sy_t, sx_r - sx_l, sy_b - sy_t,
                      buf, ncols, nrows)]


def _heatmap_annot(a, ctx, matrix, annot_arg, xgeom, ygeom, txt_col_at, fmt):
    """Shared cell-label pass. `txt_col_at(r,c)` (the auto black/white
    pick) differs between the palette and cmap paths; positioning and the
    warp anchor are common. `fmt` formats numeric labels: the cmap path
    passes the user fmt (labels are measurements), the palette path
    passes None → verbatim `str()` (labels are identifiers/counts)."""
    if annot_arg is False or annot_arg is None:
        return []
    opts = a["opts"]
    nrows = len(ygeom); ncols = len(xgeom)
    label_source = matrix if annot_arg is True else to_list_2d(annot_arg)
    if len(label_source) != nrows or (label_source and len(label_source[0]) != ncols):
        raise ValueError(
            f"heatmap: annot array shape ({len(label_source)}x"
            f"{len(label_source[0]) if label_source else 0}) "
            f"doesn't match data ({nrows}x{ncols})"
        )
    color_opt = opts.get("annot_color", "auto")
    fontsize = opts.get("annot_fontsize", 10)
    out = []
    for r in range(nrows):
        y0, bh = ygeom[r]
        cy = y0 + bh / 2
        for c in range(ncols):
            label = label_source[r][c]
            if label is None or (isinstance(label, float) and label != label):
                continue
            txt = format(label, fmt) \
                if fmt is not None and isinstance(label, (int, float)) \
                else str(label)
            txt_col = txt_col_at(r, c) if color_opt == "auto" else color_opt
            x0, bw = xgeom[c]
            ax, ay = x0 + bw / 2, cy + fontsize / 3
            if ctx.warp is not None:
                ax, ay = ctx.warp(ax, ay)
            out.append(text_path(txt, ax, ay,
                                 fontsize, anchor="middle", color=txt_col))
    return out


def _heatmap_draw_categorical(a, ctx):
    matrix, annot_arg, xgeom, ygeom, xcats, ycats = _resolve_display(a, ctx)
    nrows = len(ygeom); ncols = len(xgeom)
    if nrows == 0 or ncols == 0:
        return ""
    opts = a["opts"]
    palette = {k: resolve_color(v) for k, v in a["_palette"].items()}
    absent_fill = resolve_color(opts.get("absent_fill", "#eeeeee"))
    lw = opts.get("linewidth", 0)
    lc = resolve_color(opts.get("linecolor", "white")) if lw else None
    out = []

    use_rects = _use_rects(a, ctx, nrows, ncols)
    a["_encoding"] = "rects" if use_rects else "png-embedded"
    if use_rects:
        for r in range(nrows):
            y0, bh = ygeom[r]
            for c in range(ncols):
                x0, bw = xgeom[c]
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
        out.extend(_png_fallback(ctx, xgeom, ygeom, xcats, ycats, rgb_at))

    def txt_col_at(r, c):
        v = matrix[r][c]
        fill_hex = palette.get(v, absent_fill) if v is not None else absent_fill
        rr, gg, bb = _hex_to_rgb(fill_hex)
        return "#ffffff" if _rel_luminance(rr, gg, bb) < 0.55 else "#000000"
    out.extend(_heatmap_annot(a, ctx, matrix, annot_arg, xgeom, ygeom,
                              txt_col_at, fmt=None))
    return "".join(out)


def _heatmap_draw(a, ctx):
    if a.get("_is_categorical"):
        return _heatmap_draw_categorical(a, ctx)

    matrix, annot_arg, xgeom, ygeom, xcats, ycats = _resolve_display(a, ctx)
    nrows = len(ygeom); ncols = len(xgeom)
    if nrows == 0 or ncols == 0:
        return ""
    opts = a["opts"]
    norm = ContinuousNorm(a["_vmin"], a["_vmax"],
                           kind=opts.get("norm", "linear"),
                           center=opts.get("center"))
    lut = colormap_lut(opts.get("cmap", _D["default_cmap"]))
    absent_fill = resolve_color(opts.get("absent_fill", "#eeeeee"))
    absent_rgb  = _hex_to_rgb(absent_fill)
    lw = opts.get("linewidth", 0)
    lc = resolve_color(opts.get("linecolor", "white")) if lw else None
    out = []

    use_rects = _use_rects(a, ctx, nrows, ncols)
    a["_encoding"] = "rects" if use_rects else "png-embedded"
    if use_rects:
        for r in range(nrows):
            y0, bh = ygeom[r]
            for c in range(ncols):
                x0, bw = xgeom[c]
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
        def rgb_at(r, c):
            v = matrix[r][c]
            if v is None or v != v:
                return absent_rgb
            i = int(norm.to_unit(v) * 255 + 0.5) * 3
            return lut[i], lut[i + 1], lut[i + 2]
        out.extend(_png_fallback(ctx, xgeom, ygeom, xcats, ycats, rgb_at))

    def txt_col_at(r, c):
        v = matrix[r][c]
        if v is None or v != v:
            return "#ffffff" if _rel_luminance(*absent_rgb) < 0.55 else "#000000"
        i = int(norm.to_unit(v) * 255 + 0.5) * 3
        return "#ffffff" if _rel_luminance(lut[i], lut[i+1], lut[i+2]) < 0.55 \
            else "#000000"
    out.extend(_heatmap_annot(a, ctx, matrix, annot_arg, xgeom, ygeom,
                              txt_col_at, fmt=opts.get("fmt", ".2g")))
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


def _heatmap_axis_attrs(a):
    """Continuous-positioning attrs, emitted only for a numeric `x=`
    axis. A categorical axis is already reported by the panel's
    `data-plotlet-{x,y}scale="category"`, so we add nothing there."""
    out = {}
    if a.get("_x_continuous"):
        edges = a["_x_edges"]
        out["x-axis"] = "continuous"
        out["x-extent"] = f"{float(edges[0][0])},{float(edges[-1][1])}"
    return out


def _heatmap_encoding(a):
    """What the SVG actually contains. Draw stashes its rects-vs-PNG
    decision on the record (`_use_rects` also weighs warp and cell
    geometry, which this attr pass can't see); the size rule is only the
    fallback for a record that was never drawn."""
    stashed = a.get("_encoding")
    if stashed is not None:
        return stashed
    return "png-embedded" if (a["_nrows"] * a["_ncols"]
                              > _D["imshow_max_rects"]) else "rects"


def _heatmap_data_attrs(a):
    if a.get("_is_categorical"):
        return {
            "rows": a["_nrows"],
            "cols": a["_ncols"],
            "mode": "categorical",
            "categories": list(a["_palette"].keys()),
            **_heatmap_axis_attrs(a),
        }
    out = {
        "rows": a["_nrows"],
        "cols": a["_ncols"],
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "cmap": a["opts"].get("cmap", _D["default_cmap"]),
        "data-encoding": _heatmap_encoding(a),
        **_heatmap_axis_attrs(a),
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
))
