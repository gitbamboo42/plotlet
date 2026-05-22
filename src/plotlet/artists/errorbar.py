"""Points with vertical (and/or horizontal) error bars and optional caps —
the matplotlib `ax.errorbar` staple. `yerr`/`xerr` accept a scalar,
a per-point sequence, or a `(lower, upper)` tuple for asymmetric bars.
"""
from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from ..draw import marker, segment
from .._spec import _D, _LEGSPEC
from .._artist_impl import _artist_errorbar, _expand_err
from ._shared import _xy_minmax


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
