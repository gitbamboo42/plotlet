"""Line / step — connected xy points, single-series per record.

  c.line(data=df, x="col_x", y="col_y")                # long-form
  c.line(data=df, x="col_x", y="col_y", color="g")     # one line per color level
  c.line(data=df, x="col_x", y="col_y",                # invisible split — one
          color="cohort", group="subject")              #   line per subject,
                                                        #   colors only by cohort
  c.line(data=df, ..., linestyle="--")                 # literal dash
  c.line(data=df, ..., linestyle="cohort")             # dash cycle per level
  c.line(data=df, ..., alpha="cohort", alphas=(.3, 1)) # opacity per level
  c.line(data=df, ..., arc=False)                      # straight chords under
                                                        #   CircularCoordinate
                                                        #   (no-op in Cartesian)
  c.step(data=df, x="col_x", y="col_y", where="post")  # step variant; where=
                                                        #   "pre" | "post" | "mid"
  c.line(data=df, x="dose", y="resp",                  # aggregate replicate
          estimator="mean")                             #   rows per x with a
                                                        #   CI band (seaborn
                                                        #   lineplot)

Aggregation (estimator=): replicate rows sharing an x collapse to their
mean/median, drawn with a shaded CI band. `ci="t"` (default) is the
analytic t interval on the mean; `ci="boot"` a percentile bootstrap
(any estimator); `ci=None` just the aggregated line. `level=0.95`,
`n_boot=1000`, `seed=0`, `band_alpha=0.2` tune it. Applies per series
after color=/group= splitting; needs curve='linear'.

`linestyle=` dispatches on the value:
  * not-a-column string (`"--"`, `":"`, `"6,3,1,3"`) → literal dash
  * column name → cycle through dash patterns per level

Column-driven splitting (any of `color`/`group`/`linestyle`/`alpha`) is
handled at the Chart layer — the artist itself always sees one series
per record.
"""
import math
import random

from ..registry import ArtistSpec, add_artist
from ..utils import quantile, validate_ci, ci_bounds
from .._spec import _D
from ..draw import coord, marker, path as draw_path, polygon, polyline
from ._shared import (_xy_minmax, _line_legend_entries, _CURVE_VALUES,
                       _step_coords, expand_xy_long_form, DEFAULT_ALPHA_RANGE)


def _artist_line(a, xs_, ys_, col, xs, ys, warp=None):
    out = []
    opts = a["opts"]
    alpha = opts.get("alpha", 1)
    arc = opts.get("arc", True)
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
    ls = opts.get("linestyle")
    lw = opts.get("linewidth", _D["linewidth"])
    if ls not in ("", "none"):
        if warp is None:
            # Single <path> with multiple M/L subpaths — broken lines (None
            # gaps) become separate subpaths inside one path d-string.
            d_segs, started = [], False
            for p in path_pts:
                if p is None:
                    started = False
                    continue
                d_segs.append(f'{"M" if not started else "L"}{coord(p[0])},{coord(p[1])}')
                started = True
            out.append(draw_path("".join(d_segs), stroke=col, stroke_width=lw,
                                 dash=ls, alpha=alpha))
        else:
            # Coord-native: emit one polyline per contiguous run so each
            # edge subdivides through warp into a smooth arc. Broken lines
            # become separate <path> elements (the visual break is the same).
            # `arc=False` skips per-edge subdivision: pre-project the data
            # points themselves (endpoints still warp to the correct angle
            # and ring), then connect them with literal straight chords.
            def _emit(run):
                if arc:
                    return polyline(run, color=col, width=lw, dash=ls,
                                     alpha=alpha, project=warp)
                pts = [warp(*pt) for pt in run]
                return polyline(pts, color=col, width=lw, dash=ls,
                                 alpha=alpha, project=None)
            run = []
            for p in path_pts:
                if p is None:
                    if run:
                        out.append(_emit(run))
                        run = []
                else:
                    run.append(p)
            if run:
                out.append(_emit(run))
    if opts.get("marker"):
        sz = opts.get("size", _D["markersize"])
        for x, y in zip(xs, ys):
            px, py = xs_(x), ys_(y)
            if not (math.isfinite(px) and math.isfinite(py)):
                continue
            out.append(marker(opts["marker"], px, py, sz, col, alpha,
                              project=warp))
    return "".join(out)


def _line_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "line requires long-form input: "
            "c.line(data=df, x='col', y='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError(
            "line requires data=, x=, y= (color/group/linestyle/alpha optional)."
        )
    if "linetype" in kw:
        raise TypeError(
            "line takes `linestyle=` for dash style "
            "(literal `\"--\"`, `\":\"`, `\"-.\"`, … → fixed; column name → "
            "cycle dashes per level)."
        )
    if "markersize" in kw:
        raise TypeError(
            "line takes `size=` for marker radius (px)."
        )
    color   = kw.pop("color", None)
    group   = kw.pop("group", None)
    ls      = kw.pop("linestyle", None)
    alpha   = kw.pop("alpha", None)
    palette = kw.pop("palette", None)
    alphas  = kw.pop("alphas", DEFAULT_ALPHA_RANGE)
    estimator = kw.get("estimator")
    if estimator not in (None, "mean", "median"):
        raise ValueError(
            f"line: estimator={estimator!r} — expected 'mean', 'median', "
            f"or None."
        )
    if estimator is None and ("ci" in kw or "band_alpha" in kw):
        raise TypeError("line: ci=/band_alpha= apply with estimator=.")
    if estimator is not None and kw.get("curve", "linear") != "linear":
        raise ValueError(
            "line: estimator= aggregation draws a linear band — "
            "it doesn't combine with curve=/step()."
        )
    records = expand_xy_long_form("line", data, x_col, y_col,
                                   color, group, ls, alpha,
                                   palette, alphas, kw)
    if estimator is not None:
        for rec in records:
            _aggregate_series(rec, estimator)
    return records


def _aggregate_series(rec, estimator):
    """Collapse replicate rows sharing an x to their estimator, in place.
    x order: ascending when numeric, first-seen otherwise. NaN/None pairs
    drop. `ci` attaches `_band_lo`/`_band_hi` alongside the aggregate."""
    opts = rec["opts"]
    ci = opts.get("ci", "t")
    validate_ci("line", ci)
    level = opts.get("level", 0.95)
    n_boot = opts.get("n_boot", 1000)
    rng = random.Random(opts.get("seed", 0))
    cells = {}
    for x, y in zip(rec["xs"], rec["ys"]):
        if x is None or (isinstance(x, float) and x != x):
            continue
        if y is None or (isinstance(y, float) and y != y):
            continue
        cells.setdefault(x, []).append(y)
    xs = list(cells)
    if all(isinstance(x, (int, float)) for x in xs):
        xs.sort()
    est_fn = ((lambda v: sum(v) / len(v) if v else float("nan"))
              if estimator == "mean" else (lambda v: quantile(v, 0.5)))
    rec["xs"] = xs
    rec["ys"] = [est_fn(cells[x]) for x in xs]
    if ci is None:
        return
    los, his = ci_bounds([cells[x] for x in xs], est_fn, estimator,
                         ci, level, n_boot, rng)
    rec["_band_lo"] = los
    rec["_band_hi"] = his


def _line_xdomain(a): return a["xs"]


def _line_ydomain(a):
    if "_band_lo" in a:
        return list(a["ys"]) + a["_band_lo"] + a["_band_hi"]
    return a["ys"]


def _line_ydomain_log(a):
    """Log-axis vote: the CI band's non-positive bounds are unplottable
    on log and must not poison the domain — only the plottable part of
    the band votes (mpl/seaborn clip the band at the axis instead)."""
    if "_band_lo" in a:
        return (list(a["ys"])
                + [v for v in a["_band_lo"] + a["_band_hi"] if v > 0])
    return a["ys"]


def _line_data_attrs(a):
    xs, ys = a["xs"], a["ys"]
    out = {"n": len(xs)}
    out.update(_xy_minmax(xs, ys))
    opts = a["opts"]
    if opts.get("linestyle"): out["linestyle"] = opts["linestyle"]
    if opts.get("marker"): out["marker"] = opts["marker"]
    curve = opts.get("curve")
    if curve and curve != "linear": out["curve"] = curve
    if opts.get("arc") is False: out["arc"] = False
    if opts.get("estimator"): out["estimator"] = opts["estimator"]
    return out


def _band_y_px(y_scale, v):
    """Pixel for one band bound. A bound the scale can't plot (log,
    v <= 0) clips to the axis floor — one NaN coordinate would make
    browsers drop the whole band polygon."""
    p = y_scale(v)
    if p == p:
        return p
    return y_scale(y_scale.d0)


def _line_draw(a, ctx):
    out = ""
    if a.get("_band_lo"):
        pts_top = [(ctx.x_scale(x), _band_y_px(ctx.y_scale, y))
                   for x, y in zip(a["xs"], a["_band_hi"])]
        pts_bot = [(ctx.x_scale(x), _band_y_px(ctx.y_scale, y))
                   for x, y in zip(a["xs"], a["_band_lo"])]
        out = polygon(pts_top + pts_bot[::-1], fill=ctx.color,
                      alpha=a["opts"].get("band_alpha", 0.2),
                      project=ctx.warp)
    return out + _artist_line(a, ctx.x_scale, ctx.y_scale, ctx.color,
                              a["xs"], a["ys"], warp=ctx.warp)


add_artist(ArtistSpec(
    name="line",
    record=_line_record,
    xdomain=_line_xdomain,
    ydomain=_line_ydomain,
    ydomain_log=_line_ydomain_log,
    draw=_line_draw,
    legend_entries=_line_legend_entries,
    data_attrs=_line_data_attrs,
))


_STEP_WHERE = {"pre": "step-before", "post": "step-after", "mid": "step-mid"}


def _step_record(args, kw):
    where = kw.pop("where", "post")
    curve = _STEP_WHERE.get(where)
    if curve is None:
        raise ValueError(
            f"step() where= expects 'pre', 'post', or 'mid'; got {where!r}"
        )
    kw["curve"] = curve
    return _line_record(args, kw)


add_artist(ArtistSpec(
    name="step",
    record=_step_record,
    xdomain=_line_xdomain,
    ydomain=_line_ydomain,
    ydomain_log=_line_ydomain_log,
    draw=_line_draw,
    legend_entries=_line_legend_entries,
    data_attrs=_line_data_attrs,
))
