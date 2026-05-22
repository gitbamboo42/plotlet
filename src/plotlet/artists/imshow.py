"""imshow needs a preprocessing step (2-D-ify, autocompute vmin/vmax) before
domain can be computed. We do that in record() rather than _render.
"""
import base64

from ..registry import ArtistSpec, add_artist
from ..utils import to_list_2d
from .._spec import _D
from ..draw import rect
from ..draw._png import encode_rgb
from ..draw.colormaps import colormap_lut, _ContinuousNorm


def _artist_imshow(a, xs_, ys_, col):
    """2-D array → colored grid. Branches between many <rect>s and one PNG.

    The threshold (`imshow_max_rects` in spec.json) trades vector cleanliness
    for SVG file size. Below the threshold, each cell is its own <rect> — sharp
    at any zoom. Above, the whole image is encoded as base64 PNG.

    `origin` controls vertical orientation. Default `"lower"` puts row 0 at
    the BOTTOM of the data rectangle (Cartesian). Opt in to `"upper"` for
    matrix-style display (row 0 at top, what you see when you print the
    array); the panel auto-inverts the y-axis in that case so tick "0"
    lands next to row 0, matching matplotlib.

    Color mapping goes through `_ContinuousNorm`, which supports `norm="log"`
    and `center=` on top of the default linear range.
    """
    nrows = a["_nrows"]; ncols = a["_ncols"]
    if nrows == 0 or ncols == 0:
        return ""
    data = a["_data"]
    opts = a["opts"]
    norm = _ContinuousNorm(a["_vmin"], a["_vmax"],
                           kind=opts.get("norm", "linear"),
                           center=opts.get("center"))
    lut = colormap_lut(opts.get("cmap", _D["default_cmap"]))
    origin = opts.get("origin", "lower")

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

    # Render order = order in which we walk pixel rows from top to bottom.
    # Default origin="lower": row 0 belongs at the bottom, so iterate
    # data in reverse to put the highest-index row at top first.
    # origin="upper": row 0 belongs at the top — natural data order.
    row_index = range(nrows) if origin == "upper" \
                else ((nrows - 1 - r) for r in range(nrows))
    rows_in_render_order = [data[i] for i in row_index]

    use_rects = nrows * ncols <= _D["imshow_max_rects"]

    if use_rects:
        out = []
        cw = pw / ncols; ch = ph / nrows
        for r, row in enumerate(rows_in_render_order):
            y = sy_t + r * ch
            for c in range(ncols):
                v = row[c]
                if v != v:
                    fill = "rgb(0,0,0)"
                else:
                    i = int(norm.to_unit(v) * 255 + 0.5) * 3
                    fill = f"rgb({lut[i]},{lut[i+1]},{lut[i+2]})"
                x = sx_l + c * cw
                out.append(rect(x, y, cw, ch, fill=fill))
        return "".join(out)

    buf = bytearray()
    for row in rows_in_render_order:
        for c in range(ncols):
            v = row[c]
            if v != v:
                buf.append(0); buf.append(0); buf.append(0)
            else:
                i = int(norm.to_unit(v) * 255 + 0.5) * 3
                buf.append(lut[i]); buf.append(lut[i+1]); buf.append(lut[i+2])
    png = encode_rgb(bytes(buf), ncols, nrows)
    b64 = base64.b64encode(png).decode("ascii")
    return (f'<image x="{sx_l:.3f}" y="{sy_t:.3f}" '
            f'width="{pw:.3f}" height="{ph:.3f}" '
            f'preserveAspectRatio="none" image-rendering="pixelated" '
            f'href="data:image/png;base64,{b64}"/>')


def _imshow_data_attrs(a):
    out = {
        "rows": a["_nrows"],
        "cols": a["_ncols"],
        "vmin": a["_vmin"],
        "vmax": a["_vmax"],
        "cmap": a["opts"].get("cmap", _D["default_cmap"]),
        # imshow is always raster (PNG-embedded above the rect threshold,
        # individual <rect>s below). The flag is here so AI tools know
        # which decoding strategy they're looking at.
        "data-encoding": "png-embedded" if (a["_nrows"] * a["_ncols"]
                                              > _D["imshow_max_rects"]) else "rects",
    }
    extent = a["opts"].get("extent")
    if extent is not None:
        out["extent"] = ",".join(repr(float(v)) for v in extent)
    origin = a["opts"].get("origin", "lower")
    if origin != "lower":
        out["origin"] = origin
    norm = a["opts"].get("norm", "linear")
    if norm != "linear":
        out["norm"] = norm
    center = a["opts"].get("center")
    if center is not None:
        out["center"] = float(center)
    return out


def _imshow_record(args, kw):
    d = to_list_2d(args[0])
    nrows = len(d)
    ncols = len(d[0]) if d else 0
    vmin = kw.get("vmin"); vmax = kw.get("vmax")
    norm = kw.get("norm", "linear")
    # For log norm, autoscale ignores non-positive values (they can't be
    # log-mapped). User-supplied vmin/vmax are still trusted as-is; the
    # _ContinuousNorm constructor will raise if they're non-positive.
    if vmin is None or vmax is None:
        if norm == "log":
            flat = [v for row in d for v in row if v == v and v > 0]
        else:
            flat = [v for row in d for v in row if v == v]
        if flat:
            if vmin is None: vmin = min(flat)
            if vmax is None: vmax = max(flat)
        else:
            vmin, vmax = (1.0, 10.0) if norm == "log" else (0.0, 1.0)
    return {"type": "imshow", "_data": d, "_nrows": nrows, "_ncols": ncols,
            "_vmin": vmin, "_vmax": vmax, "data": d, "opts": kw}


def _imshow_xdomain(a):
    ext = a["opts"].get("extent")
    if ext is None:
        return [0, a["_ncols"]]
    return [ext[0], ext[1]]


def _imshow_ydomain(a):
    ext = a["opts"].get("extent")
    if ext is None:
        return [0, a["_nrows"]]
    return [ext[2], ext[3]]


def _imshow_legend_gradient(a):
    """Describe imshow's continuous mapping (cmap + range + user overrides) for legend rendering."""
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


add_artist(ArtistSpec(
    name="imshow",
    record=_imshow_record,
    xdomain=_imshow_xdomain,
    ydomain=_imshow_ydomain,
    draw=lambda a, ctx: _artist_imshow(a, ctx.x_scale, ctx.y_scale, None),
    legend_gradient=_imshow_legend_gradient,
    uses_color_cycle=False,
    data_attrs=_imshow_data_attrs,
    flips_y_axis=lambda a: a["opts"].get("origin", "lower") == "upper",
    tight_domain=True,
))
