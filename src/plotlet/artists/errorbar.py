"""Points with vertical (and/or horizontal) error bars and optional caps.

Long-form table input:
  c.errorbar(data=df, x="cat", y="mean", yerr="sd")            # offset (sym)
  c.errorbar(data=df, x="cat", y="mean", yerr=0.5)             # scalar offset
  c.errorbar(data=df, x="cat", y="mean", yerr=("lo", "hi"))     # offset (asym)
  c.errorbar(data=df, x="cat", y="mean", ymin="lo", ymax="hi")  # absolute bounds
  c.errorbar(data=df, x="t", y="mean", xerr="terr", yerr="sd")  # both axes

`yerr=` / `xerr=` accept a column name, a scalar, or a `(lower, upper)`
tuple of column names or scalars for asymmetric bars. `ymin=`/`ymax=`
(and `xmin=`/`xmax=`) take column names for absolute bounds and are
mutually exclusive with the matching `*err=`.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list, all_numeric
from ..draw import marker, segment, errorbar_v, errorbar_h
from .._spec import _D, _LEGSPEC
from ._shared import _xy_minmax


def _resolve_offset(data, spec, n):
    """One side of an error spec (a column name or scalar) → length-n list."""
    if isinstance(spec, str):
        return to_list(data[spec])
    return [float(spec)] * n


def _resolve_err(data, err, n):
    """Normalize an error specification to (lower, upper) offset lists."""
    if err is None:
        return [0.0] * n, [0.0] * n
    if isinstance(err, tuple) and len(err) == 2:
        return _resolve_offset(data, err[0], n), _resolve_offset(data, err[1], n)
    v = _resolve_offset(data, err, n)
    return list(v), list(v)


def _resolve_bounds(data, vals, min_spec, max_spec, err_lo, err_hi, axis):
    """If absolute bounds are given, convert to offsets relative to `vals`.
    Otherwise return the existing offset lists unchanged."""
    if min_spec is None and max_spec is None:
        return err_lo, err_hi
    if min_spec is None or max_spec is None:
        raise TypeError(
            f"errorbar: provide both {axis}min= and {axis}max= "
            f"(or use {axis}err=)."
        )
    lo_vals = to_list(data[min_spec])
    hi_vals = to_list(data[max_spec])
    return ([v - lo for v, lo in zip(vals, lo_vals)],
            [hi - v for v, hi in zip(vals, hi_vals)])


def _errorbar_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "errorbar requires long-form input: "
            "c.errorbar(data=df, x='col', y='col', yerr='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError(
            "errorbar requires data=, x=, y= "
            "(yerr/xerr/ymin/ymax/xmin/xmax optional)."
        )
    if "markersize" in kw:
        raise TypeError(
            "errorbar takes `size=` for marker radius (px)."
        )
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    n = len(xs)

    xerr = kw.pop("xerr", None)
    yerr = kw.pop("yerr", None)
    xmin = kw.pop("xmin", None); xmax = kw.pop("xmax", None)
    ymin = kw.pop("ymin", None); ymax = kw.pop("ymax", None)
    if xerr is not None and (xmin is not None or xmax is not None):
        raise TypeError("errorbar: xerr= and xmin=/xmax= are mutually exclusive.")
    if yerr is not None and (ymin is not None or ymax is not None):
        raise TypeError("errorbar: yerr= and ymin=/ymax= are mutually exclusive.")

    xlo, xhi = _resolve_err(data, xerr, n)
    ylo, yhi = _resolve_err(data, yerr, n)
    xlo, xhi = _resolve_bounds(data, xs, xmin, xmax, xlo, xhi, "x")
    ylo, yhi = _resolve_bounds(data, ys, ymin, ymax, ylo, yhi, "y")

    return {"type": "errorbar",
            "xs": xs, "ys": ys,
            "xlo": xlo, "xhi": xhi, "ylo": ylo, "yhi": yhi,
            "opts": kw}


def _artist_errorbar(a, xs_, ys_, col):
    xs, ys, opts = a["xs"], a["ys"], a["opts"]
    xlo, xhi, ylo, yhi = a["xlo"], a["xhi"], a["ylo"], a["yhi"]
    has_xerr = any(xlo) or any(xhi)
    has_yerr = any(ylo) or any(yhi)
    if has_xerr and not all_numeric(xs):
        raise TypeError(
            "errorbar: xerr/xmin/xmax requires a numeric x; "
            "got non-numeric values."
        )
    if has_yerr and not all_numeric(ys):
        raise TypeError(
            "errorbar: yerr/ymin/ymax requires a numeric y; "
            "got non-numeric values."
        )
    capsize = opts.get("capsize", _D["errorbar_capsize"])
    lw = opts.get("linewidth", _D["errorbar_linewidth"])
    mk = opts.get("marker", "o")
    msize = opts.get("size", _D["markersize"])
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
    if not all_numeric(xs):
        return list(xs)
    xlo, xhi = a["xlo"], a["xhi"]
    return [x - lo for x, lo in zip(xs, xlo)] + [x + hi for x, hi in zip(xs, xhi)]


def _errorbar_ydomain(a):
    ys = a["ys"]
    if not all_numeric(ys):
        return list(ys)
    ylo, yhi = a["ylo"], a["yhi"]
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
        msize = a["opts"].get("size", ctx.defaults["markersize"])
        cx = x0 + _LEGSPEC["swatch_width"] / 2
        return (
            segment(cx, y_mid - 5, cx, y_mid + 5,
                    color=col, width=_D["errorbar_linewidth"])
            + marker(a["opts"].get("marker", "o"), cx, y_mid, msize, col, 1)
        )
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="errorbar",
    record=_errorbar_record,
    xdomain=_errorbar_xdomain,
    ydomain=_errorbar_ydomain,
    draw=lambda a, ctx: _artist_errorbar(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_errorbar_legend_entries,
    data_attrs=_errorbar_data_attrs,
))
