"""Line — connected xy points, single-series or long-form with hue split.

  c.line(xs, ys)                                       # wide-form
  c.line(data=df, x="col_x", y="col_y")                # long-form
  c.line(data=df, x="col_x", y="col_y", hue="group")   # one line per hue
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list, long_form_xy, hue_color
from .._spec import _D, _LEGSPEC
from ..draw import marker, path as draw_path, segment
from ._shared import _xy_minmax, _line_legend_entries, _CURVE_VALUES, _step_coords


def _artist_line(a, xs_, ys_, col, xs, ys):
    out = []
    opts = a["opts"]
    alpha = opts.get("alpha", 1)
    curve = opts.get("curve", "linear")
    if curve not in _CURVE_VALUES:
        raise ValueError(
            f"unknown curve={curve!r}; expected one of {_CURVE_VALUES}"
        )
    if curve == "linear":
        path_xs, path_ys = xs, ys
    else:
        path_xs, path_ys = _step_coords(xs, ys, curve[5:])
    path_pts = [(xs_(x), ys_(y)) for x, y in zip(path_xs, path_ys)]
    path_pts = [(px, py) if (math.isfinite(px) and math.isfinite(py)) else None
                for px, py in path_pts]
    d_segs, started = [], False
    for p in path_pts:
        if p is None:
            started = False
            continue
        d_segs.append(f'{"M" if not started else "L"}{p[0]:.2f},{p[1]:.2f}')
        started = True
    ls = opts.get("linestyle")
    if ls not in ("", "none"):
        out.append(draw_path("".join(d_segs), stroke=col,
                             stroke_width=opts.get("linewidth", _D["linewidth"]),
                             dash=ls, alpha=alpha))
    if opts.get("marker"):
        sz = opts.get("markersize", _D["markersize"])
        for x, y in zip(xs, ys):
            px, py = xs_(x), ys_(y)
            if not (math.isfinite(px) and math.isfinite(py)):
                continue
            out.append(marker(opts["marker"], px, py, sz, col, alpha))
    return "".join(out)


def _line_record(args, kw):
    kw = dict(kw)
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x_col = kw.pop("x", None)
        y_col = kw.pop("y", None)
        hue_col = kw.pop("hue", None)
        if data is None or x_col is None or y_col is None:
            raise TypeError(
                "line long-form requires data=, x=, y= (hue= optional)."
            )
        hues, groups = long_form_xy(data, x_col, y_col, hue_col)
    else:
        hues = [None]
        groups = [(to_list(args[0]), to_list(args[1]))]
    return {"type": "line", "hues": hues, "groups": groups, "opts": kw}


def _line_xdomain(a):
    return [x for xs, _ in a["groups"] for x in xs]


def _line_ydomain(a):
    return [y for _, ys in a["groups"] for y in ys]


def _line_data_attrs(a):
    xs = [x for xs, _ in a["groups"] for x in xs]
    ys = [y for _, ys in a["groups"] for y in ys]
    out = {"n": len(xs)}
    out.update(_xy_minmax(xs, ys))
    opts = a["opts"]
    if opts.get("linestyle"): out["linestyle"] = opts["linestyle"]
    if opts.get("marker"): out["marker"] = opts["marker"]
    curve = opts.get("curve")
    if curve and curve != "linear": out["curve"] = curve
    return out


def _line_draw(a, ctx):
    palette = a["opts"].get("palette")
    out = []
    for j, (xs, ys) in enumerate(a["groups"]):
        col = hue_color(a["hues"], palette, j, ctx.color)
        out.append(_artist_line(a, ctx.x_scale, ctx.y_scale, col, xs, ys))
    return "".join(out)


def _line_legend_entries_multi(a):
    hues = a["hues"]
    if hues == [None]:
        return _line_legend_entries(a)
    opts = a["opts"]
    palette = opts.get("palette")
    lw = opts.get("linewidth", _D["linewidth"])
    sw = _LEGSPEC["swatch_width"]
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col):
            return segment(x0, y_mid, x0 + sw, y_mid, color=_col, width=lw,
                           dash=opts.get("linestyle"))
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="line",
    record=_line_record,
    xdomain=_line_xdomain,
    ydomain=_line_ydomain,
    draw=_line_draw,
    legend_entries=_line_legend_entries_multi,
    data_attrs=_line_data_attrs,
))
