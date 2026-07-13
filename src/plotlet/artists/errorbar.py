"""Points with vertical (and/or horizontal) error bars and optional caps.

Long-form table input:
  c.errorbar(data=df, x="cat", y="mean", yerr="sd")            # offset (sym)
  c.errorbar(data=df, x="cat", y="mean", yerr=0.5)             # scalar offset
  c.errorbar(data=df, x="cat", y="mean", yerr=("lo", "hi"))     # offset (asym)
  c.errorbar(data=df, x="cat", y="mean", ymin="lo", ymax="hi")  # absolute bounds
  c.errorbar(data=df, x="t", y="mean", xerr="terr", yerr="sd")  # both axes
  c.errorbar(data=df, x="cat", y="mean", yerr="sd", color="series")  # grouped

`yerr=` / `xerr=` accept a column name, a scalar, or a `(lower, upper)`
tuple of column names or scalars for asymmetric bars. `ymin=`/`ymax=`
(and `xmin=`/`xmax=`) take column names for absolute bounds and are
mutually exclusive with the matching `*err=`.

`color=` may be a literal color or a column name. Column → one series
per level (palette= maps levels to colors), and on a categorical axis
the series dodge within each band. `width=0.8` / `gap=0.1` are the same
band fractions as bar's, so a dodged errorbar lands on the same slot
centers as `c.bar(..., position="dodge")` with matching values.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import (UNSET, pack_opts, to_list, all_numeric, resolve_aes,
                     group_color, dodge_positions, DODGE_WIDTH, DODGE_GAP)
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


def _errorbar_record(data=None,
                     # input — consumed here at record
                     x=None, y=None,
                     xerr=None, yerr=None,
                     xmin=None, xmax=None, ymin=None, ymax=None,
                     color=None,
                     # style — packed into opts for the draw/legend/attrs side
                     marker=UNSET, size=None, alpha=None,
                     capsize=None, linewidth=None, width=None, gap=None,
                     palette=None, label=None, legend=None):
    if data is None or x is None or y is None:
        raise TypeError(
            "errorbar requires data=, x=, y= "
            "(yerr/xerr/ymin/ymax/xmin/xmax optional)."
        )
    xs = to_list(data[x])
    ys = to_list(data[y])
    n = len(xs)

    if xerr is not None and (xmin is not None or xmax is not None):
        raise TypeError("errorbar: xerr= and xmin=/xmax= are mutually exclusive.")
    if yerr is not None and (ymin is not None or ymax is not None):
        raise TypeError("errorbar: yerr= and ymin=/ymax= are mutually exclusive.")

    xlo, xhi = _resolve_err(data, xerr, n)
    ylo, yhi = _resolve_err(data, yerr, n)
    xlo, xhi = _resolve_bounds(data, xs, xmin, xmax, xlo, xhi, "x")
    ylo, yhi = _resolve_bounds(data, ys, ymin, ymax, ylo, yhi, "y")

    opts = pack_opts(size=size, alpha=alpha, capsize=capsize,
                     linewidth=linewidth, width=width, gap=gap,
                     palette=palette, label=label, legend=legend)
    # `marker=None` is meaningful (whiskers without a point glyph), so
    # unset gets a sentinel default rather than None.
    if marker is not UNSET:
        opts["marker"] = marker

    # `color=` may be a literal color or a column name; column → grouped
    # multi-series (one nested row list per level).
    color_kind, _ = resolve_aes(data, color)
    if color_kind != "column":
        if color is not None:
            opts["color"] = color
        return {"type": "errorbar",
                "xs": xs, "ys": ys,
                "xlo": xlo, "xhi": xhi, "ylo": ylo, "yhi": yhi,
                "opts": opts}
    gs = to_list(data[color])
    groups = []
    for g in gs:
        if g not in groups:
            groups.append(g)
    group_idx = {g: j for j, g in enumerate(groups)}
    split = {k: [[] for _ in groups]
             for k in ("xs", "ys", "xlo", "xhi", "ylo", "yhi")}
    for g, x, y, xl, xh, yl, yh in zip(gs, xs, ys, xlo, xhi, ylo, yhi):
        j = group_idx[g]
        split["xs"][j].append(x);  split["ys"][j].append(y)
        split["xlo"][j].append(xl); split["xhi"][j].append(xh)
        split["ylo"][j].append(yl); split["yhi"][j].append(yh)
    return {"type": "errorbar", "groups": groups, **split, "opts": opts}


def _errorbar_rows(xs, ys, xlo, xhi, ylo, yhi, opts, xs_, ys_, col, warp,
                   px_of, py_of):
    """Draw one series of rows. `px_of` / `py_of` place the point on each
    axis — the plain scales, or a dodged lookup on the categorical axis;
    whisker extents always use the plain value scales."""
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
        px = px_of(x); py = py_of(y)
        if not (math.isfinite(px) and math.isfinite(py)):
            continue
        if dyl or dyh:
            out.append(errorbar_v(px, ys_(y - dyl), ys_(y + dyh),
                                  capsize=capsize, color=col, width=lw,
                                  alpha=alpha, project=warp))
        if dxl or dxh:
            out.append(errorbar_h(py, xs_(x - dxl), xs_(x + dxh),
                                  capsize=capsize, color=col, width=lw,
                                  alpha=alpha, project=warp))
        if mk:
            out.append(marker(mk, px, py, msize, col, alpha, project=warp))
    return "".join(out)


def _artist_errorbar(a, ctx):
    xs_, ys_, warp = ctx.x_scale, ctx.y_scale, ctx.warp
    opts = a["opts"]
    groups = a.get("groups")
    if groups is None:
        return _errorbar_rows(a["xs"], a["ys"], a["xlo"], a["xhi"],
                              a["ylo"], a["yhi"], opts, xs_, ys_,
                              ctx.color, warp, xs_, ys_)
    width = opts.get("width", DODGE_WIDTH)
    gap = opts.get("gap", DODGE_GAP)
    x_band = getattr(xs_, "bandwidth", None) is not None
    y_band = getattr(ys_, "bandwidth", None) is not None
    out = []
    for j in range(len(groups)):
        px_of, py_of = xs_, ys_
        if x_band:
            px_of = lambda x, _j=j: dodge_positions(
                xs_, x, len(groups), _j, band_frac=width, gap=gap)[0]
        elif y_band:
            py_of = lambda y, _j=j: dodge_positions(
                ys_, y, len(groups), _j, band_frac=width, gap=gap)[0]
        out.append(_errorbar_rows(
            a["xs"][j], a["ys"][j], a["xlo"][j], a["xhi"][j],
            a["ylo"][j], a["yhi"][j], opts, xs_, ys_,
            group_color(groups, opts.get("palette"), j, ctx.color),
            warp, px_of, py_of))
    return "".join(out)


def _flat(a, key):
    if a.get("groups") is None:
        return a[key]
    return [v for grp in a[key] for v in grp]


def _errorbar_xdomain(a):
    xs = _flat(a, "xs")
    if not all_numeric(xs):
        return list(xs)
    xlo, xhi = _flat(a, "xlo"), _flat(a, "xhi")
    return [x - lo for x, lo in zip(xs, xlo)] + [x + hi for x, hi in zip(xs, xhi)]


def _errorbar_ydomain(a):
    ys = _flat(a, "ys")
    if not all_numeric(ys):
        return list(ys)
    ylo, yhi = _flat(a, "ylo"), _flat(a, "yhi")
    return [y - lo for y, lo in zip(ys, ylo)] + [y + hi for y, hi in zip(ys, yhi)]


def _errorbar_data_attrs(a):
    out = {"n": len(_flat(a, "xs"))}
    out.update(_xy_minmax(_flat(a, "xs"), _flat(a, "ys")))
    out["marker"] = a["opts"].get("marker", "o")
    return out


def _legend_paint(col):
    def paint(a, ctx, x0, y_mid):
        msize = a["opts"].get("size", ctx.defaults["markersize"])
        cx = x0 + _LEGSPEC["swatch_width"] / 2
        return (
            segment(cx, y_mid - 5, cx, y_mid + 5,
                    color=col, width=_D["errorbar_linewidth"])
            + marker(a["opts"].get("marker", "o"), cx, y_mid, msize, col, 1)
        )
    return paint


def _errorbar_legend_entries(a):
    groups = a.get("groups")
    if groups is None:
        label = a["opts"].get("label")
        if not label:
            return []
        return [{"label": label, "color": a.get("_color"),
                 "paint": _legend_paint(a.get("_color"))}]
    palette = a["opts"].get("palette")
    entries = []
    for j, g in enumerate(groups):
        col = group_color(groups, palette, j, a.get("_color"))
        entries.append({"label": str(g), "color": col,
                        "paint": _legend_paint(col)})
    return entries


add_artist(ArtistSpec(
    name="errorbar",
    record=_errorbar_record,
    xdomain=_errorbar_xdomain,
    ydomain=_errorbar_ydomain,
    draw=_artist_errorbar,
    legend_entries=_errorbar_legend_entries,
    data_attrs=_errorbar_data_attrs,
))
