"""Categorical heatmap artist.

User-facing categorical x × y. Cells are drawn at category band centers
using `ctx.x_scale.bandwidth` (forced to `padding=0` by `Chart.heatmap`
so cells render flush against each other).

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
"""
import base64

from ..registry import ArtistSpec, add_artist
from ..utils import to_list_2d
from .._spec import _D
from ..draw import rect, text_path
from ..draw._png import encode_rgb
from ..draw.colormaps import colormap_lut, _ContinuousNorm


def _rel_luminance(r, g, b):
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _heatmap_record(args, kw):
    matrix = to_list_2d(args[0])
    cols   = list(args[1])
    rows   = list(args[2])
    nrows  = len(matrix)
    ncols  = len(matrix[0]) if matrix else 0
    if nrows != len(rows) or (matrix and ncols != len(cols)):
        raise ValueError(
            f"heatmap: matrix shape ({nrows}x{ncols}) doesn't match "
            f"labels (rows={len(rows)}, cols={len(cols)})"
        )

    vmin = kw.get("vmin"); vmax = kw.get("vmax")
    norm = kw.get("norm", "linear")
    if vmin is None or vmax is None:
        if norm == "log":
            flat = [v for row in matrix for v in row if v == v and v > 0]
        else:
            flat = [v for row in matrix for v in row if v == v]
        if flat:
            if vmin is None: vmin = min(flat)
            if vmax is None: vmax = max(flat)
        else:
            vmin, vmax = (1.0, 10.0) if norm == "log" else (0.0, 1.0)
    return {"type": "heatmap", "_matrix": matrix, "_cols": cols, "_rows": rows,
            "_nrows": nrows, "_ncols": ncols, "_vmin": vmin, "_vmax": vmax,
            "opts": kw}


def _heatmap_xdomain(a): return list(a["_cols"])
def _heatmap_ydomain(a): return list(a["_rows"])


def _heatmap_draw(a, ctx):
    matrix = a["_matrix"]
    nrows  = a["_nrows"]; ncols = a["_ncols"]
    if nrows == 0 or ncols == 0:
        return ""
    cols = a["_cols"]; rows = a["_rows"]
    opts = a["opts"]
    norm = _ContinuousNorm(a["_vmin"], a["_vmax"],
                           kind=opts.get("norm", "linear"),
                           center=opts.get("center"))
    lut = colormap_lut(opts.get("cmap", _D["default_cmap"]))

    bw = ctx.x_scale.bandwidth
    bh = ctx.y_scale.bandwidth
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
                if v != v:
                    fill = "rgb(0,0,0)"
                else:
                    i = int(norm.to_unit(v) * 255 + 0.5) * 3
                    fill = f"rgb({lut[i]},{lut[i+1]},{lut[i+2]})"
                out.append(rect(x0, y0, bw, bh, fill=fill))
    else:
        # Category-scale PNG fallback. Extent is first-band-left to
        # last-band-right; the image spans every cell flush since
        # category_padding is forced to 0 by Chart.heatmap.
        x_left  = ctx.x_scale(cols[0])  - bw / 2
        x_right = ctx.x_scale(cols[-1]) + bw / 2
        y_top    = ctx.y_scale(rows[0])  - bh / 2
        y_bot    = ctx.y_scale(rows[-1]) + bh / 2
        # y-category puts rows[0] at TOP (cy decreases with index). So
        # y_top here is actually the smaller pixel-y of rows[0]'s band,
        # which corresponds to row 0 = top of image. Good — no flip needed.
        sy_t = min(y_top, y_bot); sy_b = max(y_top, y_bot)
        sx_l = min(x_left, x_right); sx_r = max(x_left, x_right)

        buf = bytearray()
        for r in range(nrows):
            for c in range(ncols):
                v = matrix[r][c]
                if v != v:
                    buf.append(0); buf.append(0); buf.append(0)
                else:
                    i = int(norm.to_unit(v) * 255 + 0.5) * 3
                    buf.append(lut[i]); buf.append(lut[i+1]); buf.append(lut[i+2])
        png = encode_rgb(bytes(buf), ncols, nrows)
        b64 = base64.b64encode(png).decode("ascii")
        out.append(f'<image x="{sx_l:.3f}" y="{sy_t:.3f}" '
                   f'width="{sx_r - sx_l:.3f}" height="{sy_b - sy_t:.3f}" '
                   f'preserveAspectRatio="none" image-rendering="pixelated" '
                   f'href="data:image/png;base64,{b64}"/>')

    annot = opts.get("annot", False)
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
                    if v != v:
                        txt_col = "#ffffff"
                    else:
                        i = int(norm.to_unit(v) * 255 + 0.5) * 3
                        if _rel_luminance(lut[i], lut[i+1], lut[i+2]) < 0.55:
                            txt_col = "#ffffff"
                        else:
                            txt_col = "#000000"
                else:
                    txt_col = color_opt
                cx = ctx.x_scale(cols[c])
                out.append(text_path(txt, cx, cy + fontsize / 3,
                                     fontsize, anchor="middle", color=txt_col))

    return "".join(out)


def _heatmap_legend_gradient(a):
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
    record=_heatmap_record,
    xdomain=_heatmap_xdomain,
    ydomain=_heatmap_ydomain,
    draw=_heatmap_draw,
    legend_gradient=_heatmap_legend_gradient,
    uses_color_cycle=False,
    data_attrs=_heatmap_data_attrs,
    tight_domain=True,
))
