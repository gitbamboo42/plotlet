"""imshow needs a preprocessing step (2-D-ify, autocompute vmin/vmax) before
domain can be computed. We do that in record() rather than _render.
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list_2d
from .._spec import _D
from .._artist_impl import _artist_imshow


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
