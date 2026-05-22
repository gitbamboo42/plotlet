import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._spec import _D
from ..draw import marker, path as draw_path
from ._shared import _xy_minmax, _line_legend_entries, _CURVE_VALUES, _step_coords


def _artist_line(a, xs_, ys_, col):
    out = []
    opts = a["opts"]
    alpha = opts.get("alpha", 1)
    curve = opts.get("curve", "linear")
    if curve not in _CURVE_VALUES:
        raise ValueError(
            f"unknown curve={curve!r}; expected one of {_CURVE_VALUES}"
        )
    # Path coordinates depend on the curve mode; markers always sit at
    # the original data points, so we keep two coordinate lists.
    if curve == "linear":
        path_xs, path_ys = a["xs"], a["ys"]
    else:
        path_xs, path_ys = _step_coords(a["xs"], a["ys"], curve[5:])
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
        for x, y in zip(a["xs"], a["ys"]):
            px, py = xs_(x), ys_(y)
            if not (math.isfinite(px) and math.isfinite(py)):
                continue
            out.append(marker(opts["marker"], px, py, sz, col, alpha))
    return "".join(out)


def _line_data_attrs(a):
    out = {"n": len(a["xs"])}
    out.update(_xy_minmax(a["xs"], a["ys"]))
    if a["opts"].get("linestyle"):
        out["linestyle"] = a["opts"]["linestyle"]
    if a["opts"].get("marker"):
        out["marker"] = a["opts"]["marker"]
    curve = a["opts"].get("curve")
    if curve and curve != "linear":
        out["curve"] = curve
    return out


add_artist(ArtistSpec(
    name="line",
    record=lambda args, kw: {"type": "line", "xs": to_list(args[0]),
                              "ys": to_list(args[1]), "opts": kw},
    xdomain=lambda a: a["xs"],
    ydomain=lambda a: a["ys"],
    draw=lambda a, ctx: _artist_line(a, ctx.x_scale, ctx.y_scale, ctx.color),
    legend_entries=_line_legend_entries,
    data_attrs=_line_data_attrs,
))
