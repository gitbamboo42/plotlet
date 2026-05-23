"""Line — connected xy points, single-series per record.

  c.line(xs, ys)                                       # wide-form
  c.line(data=df, x="col_x", y="col_y")                # long-form
  c.line(data=df, x="col_x", y="col_y", color="g")     # one line per color level
  c.line(data=df, x="col_x", y="col_y",                # invisible split — one
          color="cohort", group="subject")              #   line per subject,
                                                        #   colors only by cohort
  c.line(data=df, ..., linetype="cohort")              # dash pattern per level
  c.line(data=df, ..., alpha="cohort", alphas=(.3, 1)) # opacity per level

Column-driven splitting (any of `color`/`group`/`linetype`/`alpha`) is
handled at the Chart layer — the artist itself always sees one series
per record.
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list
from .._spec import _D
from ..draw import marker, path as draw_path
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
    return {"type": "line",
            "xs": to_list(args[0]), "ys": to_list(args[1]),
            "opts": dict(kw)}


def _line_xdomain(a): return a["xs"]
def _line_ydomain(a): return a["ys"]


def _line_data_attrs(a):
    xs, ys = a["xs"], a["ys"]
    out = {"n": len(xs)}
    out.update(_xy_minmax(xs, ys))
    opts = a["opts"]
    if opts.get("linestyle"): out["linestyle"] = opts["linestyle"]
    if opts.get("marker"): out["marker"] = opts["marker"]
    curve = opts.get("curve")
    if curve and curve != "linear": out["curve"] = curve
    return out


def _line_draw(a, ctx):
    return _artist_line(a, ctx.x_scale, ctx.y_scale, ctx.color,
                        a["xs"], a["ys"])


add_artist(ArtistSpec(
    name="line",
    record=_line_record,
    xdomain=_line_xdomain,
    ydomain=_line_ydomain,
    draw=_line_draw,
    legend_entries=_line_legend_entries,
    data_attrs=_line_data_attrs,
))
