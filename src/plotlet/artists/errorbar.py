"""Points with vertical (and/or horizontal) error bars and optional caps —
the matplotlib `ax.errorbar` staple. `yerr`/`xerr` accept a scalar,
a per-point sequence, or a `(lower, upper)` tuple for asymmetric bars.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from ..draw import marker, segment, errorbar_v, errorbar_h
from .._spec import _D, _LEGSPEC
from ._shared import _xy_minmax


def _expand_err(err, n):
    """Normalize an error-spec into (lower, upper) lists of length n.
    Accepts scalar, list/array, or a 2-tuple (lower, upper) for asymmetric."""
    if err is None:
        return [0.0] * n, [0.0] * n
    if isinstance(err, tuple) and len(err) == 2:
        lo = to_list(err[0]); hi = to_list(err[1])
        if len(lo) == 1: lo = lo * n
        if len(hi) == 1: hi = hi * n
        return lo, hi
    if hasattr(err, "__iter__") and not isinstance(err, str):
        v = to_list(err)
        return list(v), list(v)
    return [float(err)] * n, [float(err)] * n


def _artist_errorbar(a, xs_, ys_, col):
    xs, ys, opts = a["xs"], a["ys"], a["opts"]
    n = len(xs)
    xlo, xhi = _expand_err(opts.get("xerr"), n)
    ylo, yhi = _expand_err(opts.get("yerr"), n)
    capsize = opts.get("capsize", _D["errorbar_capsize"])
    lw = opts.get("linewidth", _D["errorbar_linewidth"])
    mk = opts.get("marker", "o")
    msize = opts.get("markersize", _D["markersize"])
    alpha = opts.get("alpha", 1)
    out = []
    for x, y, dxl, dxh, dyl, dyh in zip(xs, ys, xlo, xhi, ylo, yhi):
        px = xs_(x); py = ys_(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        if dyl or dyh:
            out.append(errorbar_v(px, ys_(y - dyl), ys_(y + dyh),
                                  capsize=capsize, color=col, width=lw, alpha=alpha))
        if dxl or dxh:
            out.append(errorbar_h(py, xs_(x - dxl), xs_(x + dxh),
                                  capsize=capsize, color=col, width=lw, alpha=alpha))
        if mk:
            out.append(marker(mk, px, py, msize, col, alpha))
    return "".join(out)


def _errorbar_xdomain(a):
    xs = a["xs"]
    xlo, xhi = _expand_err(a["opts"].get("xerr"), len(xs))
    return [x - lo for x, lo in zip(xs, xlo)] + [x + hi for x, hi in zip(xs, xhi)]


def _errorbar_ydomain(a):
    ys = a["ys"]
    ylo, yhi = _expand_err(a["opts"].get("yerr"), len(ys))
    return [y - lo for y, lo in zip(ys, ylo)] + [y + hi for y, hi in zip(ys, yhi)]


def _errorbar_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _errorbar_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        col = a["_color"]
        msize = a["opts"].get("markersize", ctx.defaults["markersize"])
        cx = x0 + _LEGSPEC["swatch_width"] / 2
        return (
            segment(cx, y_mid - 5, cx, y_mid + 5,
                    color=col, width=_D["errorbar_linewidth"])
            + marker(a["opts"].get("marker", "o"), cx, y_mid, msize, col, 1)
        )
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="errorbar",
    record=lambda args, kw: {"type": "errorbar",
                              "xs": to_list(args[0]),
                              "ys": to_list(args[1]),
                              "opts": kw},
    xdomain=_errorbar_xdomain,
    ydomain=_errorbar_ydomain,
    draw=lambda a, ctx: _artist_errorbar(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_errorbar_legend_entries,
    data_attrs=_errorbar_data_attrs,
))
