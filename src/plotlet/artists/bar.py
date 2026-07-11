"""Bar chart — long-form only.

  c.bar(data=df, x="cat", y="val")                                  # single
  c.bar(data=df, x="cat", y="val", fill="C0")                       # constant color
  c.bar(data=df, x="cat", y="val", fill="series", position="stack") # grouped
  c.bar(data=df, x="cat", y="val", fill="series", position="dodge")
  c.bar(data=df, x="cat", y="val", fill="series", position="fill")  # 100% stack
  c.bar(data=df, x="cat", y="mean", fill="series", yerr="sd")       # mean±err
  c.bar(data=df, x="cat", stat="count")                             # countplot
  c.bar(data=df, x="cat", y="raw", stat="mean")                     # mean±CI

`position` defaults to `"stack"` whenever `fill=` is a column with more
than one unique value — except with `yerr=`/`xerr=` or `stat="mean"`,
which default to `"dodge"` (error bars aren't defined for stacked bars,
and stacked means are misleading). Duplicate (cat, group) rows are
summed; with error bars they raise instead, since offsets don't
aggregate the way sums do.

Stats (seaborn countplot / barplot, ggplot geom_bar):
  stat='identity'     y values used as given (duplicates summed)
  stat='count'        bar height = number of rows per category; drop y=
  stat='mean'         bar height = mean of y per category, with a CI
                      error bar: ci='t' (default), 'boot', or None;
                      level=0.95, n_boot=1000, seed=0 as in pointplot

Aesthetics:
  fill=         literal color OR column name → grouped multi-series
  color=        stroke color (constant, default None = no stroke)
  palette=      maps group levels → colors when `fill=` is a column

Error bars (same specs as the errorbar artist — column name, scalar, or
a (lower, upper) tuple of either):
  yerr=         value-axis error for vertical bars
  xerr=         value-axis error for horizontal bars (orientation='h')
  ecolor=<themed>     whisker color
  capsize=<themed>    whisker cap width (px)

Other styling kwargs:
  orientation='v'     'h' for horizontal bars
  bottom=0            baseline value (single / dodge); stacks always start at 0
  alpha=<themed>      bar fill opacity
  linewidth=<themed>  stroke width (used only when color is set)
  width=0.8           dodged-group total width as a band fraction
  gap=0.1             slot-gap fraction between dodged bars
  label=None          legend label (overridden by column-driven grouping)
"""
import random

from ..registry import ArtistSpec, add_artist
from ..utils import (to_list, resolve_aes, dodge_positions,
                     validate_ci, ci_bounds, DODGE_WIDTH, DODGE_GAP)
from ..draw import resolve_color
from .._spec import _D, _LEGSPEC
from ..draw import rect as draw_rect
from ..draw import errorbar_v, errorbar_h
from .errorbar import _resolve_err
from ._shared import band_rect
from ..utils import group_color as _group_fill


_POSITIONS = ("stack", "dodge", "fill")
_STATS = ("identity", "count", "mean")


def _aggregate_long(data, x_col, y_col, group_col):
    """Long-form table -> (cats, groups, series). series[j][i] sums y over
    rows where x == cats[i] and the grouping value == groups[j]."""
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    gs = to_list(data[group_col]) if group_col is not None else [None] * len(xs)
    cats, groups = [], []
    for c in xs:
        if c not in cats: cats.append(c)
    for g in gs:
        if g not in groups: groups.append(g)
    if not groups: groups = [None]
    series = [[0] * len(cats) for _ in groups]
    cat_idx = {c: i for i, c in enumerate(cats)}
    group_idx = {g: j for j, g in enumerate(groups)}
    for x, y, g in zip(xs, ys, gs):
        series[group_idx[g]][cat_idx[x]] += y
    return cats, groups, series


def _aggregate_err(data, x_col, group_col, err, cats, groups):
    """Row-level error spec → per-(group, cat) offset grids shaped like
    `series`. Requires at most one row per cell — duplicate rows sum their
    y values, and offsets have no matching aggregation."""
    xs = to_list(data[x_col])
    gs = to_list(data[group_col]) if group_col is not None else [None] * len(xs)
    lo, hi = _resolve_err(data, err, len(xs))
    cat_idx = {c: i for i, c in enumerate(cats)}
    group_idx = {g: j for j, g in enumerate(groups)}
    err_lo = [[0.0] * len(cats) for _ in groups]
    err_hi = [[0.0] * len(cats) for _ in groups]
    seen = set()
    for x, g, l, h in zip(xs, gs, lo, hi):
        cell = (group_idx[g], cat_idx[x])
        if cell in seen:
            raise ValueError(
                "bar: yerr/xerr requires one row per (category, group) — "
                "pre-aggregate the table."
            )
        seen.add(cell)
        err_lo[cell[0]][cell[1]] = l
        err_hi[cell[0]][cell[1]] = h
    return err_lo, err_hi


def _aggregate_stat(data, x_col, y_col, group_col, stat, ci,
                    level, n_boot, seed):
    """Row-level table → per-(group, cat) stat aggregation. `stat='count'`
    counts rows per cell; `stat='mean'` averages y per cell (NaN/None rows
    dropped), with `ci` supplying err_lo/err_hi offset grids shaped like
    `series` (None when `ci` is None). Empty cells aggregate to 0 with no
    error bar."""
    xs = to_list(data[x_col])
    gs = to_list(data[group_col]) if group_col is not None else [None] * len(xs)
    ys = to_list(data[y_col]) if y_col is not None else [None] * len(xs)
    cats, groups = [], []
    for c in xs:
        if c not in cats: cats.append(c)
    for g in gs:
        if g not in groups: groups.append(g)
    cells = [[[] for _ in cats] for _ in groups]
    cat_idx = {c: i for i, c in enumerate(cats)}
    group_idx = {g: j for j, g in enumerate(groups)}
    for x, y, g in zip(xs, ys, gs):
        if stat == "mean" and (y is None or (isinstance(y, float) and y != y)):
            continue
        cells[group_idx[g]][cat_idx[x]].append(y)
    if stat == "count":
        return cats, groups, [[len(c) for c in row] for row in cells], None, None
    series = [[(sum(c) / len(c) if c else 0.0) for c in row] for row in cells]
    if ci is None:
        return cats, groups, series, None, None
    rng = random.Random(seed)
    mean_fn = lambda v: sum(v) / len(v) if v else float("nan")
    los, his = ci_bounds([c for row in cells for c in row], mean_fn, "mean",
                         ci, level, n_boot, rng)
    # Bounds → whisker offsets around the drawn bar top; a bound-less
    # (empty) cell keeps a zero offset, so the 0-height bar has no whisker.
    err_lo = [[0.0] * len(cats) for _ in groups]
    err_hi = [[0.0] * len(cats) for _ in groups]
    for j in range(len(groups)):
        for i in range(len(cats)):
            lo, hi = los[j * len(cats) + i], his[j * len(cats) + i]
            if lo != lo:
                continue
            err_lo[j][i] = series[j][i] - lo
            err_hi[j][i] = hi - series[j][i]
    return cats, groups, series, err_lo, err_hi


def _bar_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "bar requires long-form input: "
            "c.bar(data=df, x='col', y='col', fill='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    stat = kw.pop("stat", "identity")
    if stat not in _STATS:
        raise ValueError(
            f"unknown stat={stat!r}; expected one of {_STATS}."
        )
    if data is None or x_col is None or (y_col is None and stat != "count"):
        raise TypeError(
            "bar requires data=, x=, y= (fill= optional)."
        )
    if stat == "count" and y_col is not None:
        raise TypeError(
            "bar: stat='count' counts rows per category — drop y=."
        )
    ci = kw.pop("ci", "t" if stat == "mean" else None)
    if ci is not None and stat != "mean":
        raise TypeError("bar: ci= applies to stat='mean'.")
    validate_ci("bar", ci)
    # `fill=` may be a literal color or a column name. Column → drives
    # grouping; literal → applied to every bar.
    fill = kw.pop("fill", None)
    fill_kind, fill_value = resolve_aes(data, fill)
    group_col = fill if fill_kind == "column" else None
    stat_err_lo = stat_err_hi = None
    if stat == "identity":
        cats, groups, series = _aggregate_long(data, x_col, y_col, group_col)
    else:
        cats, groups, series, stat_err_lo, stat_err_hi = _aggregate_stat(
            data, x_col, y_col, group_col, stat, ci,
            kw.pop("level", 0.95), kw.pop("n_boot", 1000), kw.pop("seed", 0))
    if fill_kind == "literal":
        kw["_fill_literal"] = fill_value
    if group_col is not None and group_col == x_col:
        kw["_redundant_grouping"] = True
    bottom = kw.get("bottom", 0)
    if hasattr(bottom, "__iter__") and not isinstance(bottom, str):
        raise TypeError(
            "bar: bottom= must be a scalar baseline; for grouped bars "
            "pass fill='series_col' with position='stack'."
        )
    yerr = kw.pop("yerr", None)
    xerr = kw.pop("xerr", None)
    if stat != "identity" and (yerr is not None or xerr is not None):
        raise TypeError(
            "bar: stat= aggregates for you — stat='mean' supplies error "
            "bars from the CI; drop yerr=/xerr=."
        )
    horizontal = kw.get("orientation") == "h"
    if yerr is not None and horizontal:
        raise TypeError("bar: horizontal bars take xerr= (the value axis is x).")
    if xerr is not None and not horizontal:
        raise TypeError("bar: vertical bars take yerr= (the value axis is y).")
    err = xerr if horizontal else yerr

    if len(series) == 1:
        default_pos = None
    elif err is not None or stat == "mean":
        default_pos = "dodge"
    else:
        default_pos = "stack"
    position = kw.pop("position", default_pos)
    if position is not None and position not in _POSITIONS:
        raise ValueError(
            f"unknown position={position!r}; expected one of {_POSITIONS}."
        )
    if stat == "mean" and position in ("stack", "fill"):
        raise ValueError(
            f"bar: stacked means are misleading — stat='mean' takes "
            f"position='dodge', not {position!r}."
        )
    rec = {"type": "bar", "cats": cats, "groups": groups, "series": series,
           "_position": position, "opts": kw}
    if err is not None:
        if position in ("stack", "fill"):
            raise ValueError(
                f"bar: yerr/xerr isn't defined for position={position!r} — "
                f"use position='dodge'."
            )
        rec["err_lo"], rec["err_hi"] = _aggregate_err(
            data, x_col, group_col, err, cats, groups)
    elif stat_err_lo is not None:
        rec["err_lo"], rec["err_hi"] = stat_err_lo, stat_err_hi
    return rec


def _bar_horizontal(a): return a["opts"].get("orientation") == "h"


def _bar_vals_for_domain(a):
    series = a["series"]
    position = a["_position"]
    bottom = a["opts"].get("bottom", 0)
    multi = len(series) > 1
    if multi and position == "fill":
        return [0, 1]
    if multi and position == "stack":
        sums = [sum(s[i] for s in series) for i in range(len(a["cats"]))]
        return sums + [0]
    flat = [v for s in series for v in s]
    if a.get("err_lo") is not None:
        flat += [v - lo for s, slo in zip(series, a["err_lo"])
                 for v, lo in zip(s, slo)]
        flat += [v + hi for s, shi in zip(series, a["err_hi"])
                 for v, hi in zip(s, shi)]
    return flat + [0, bottom]


def _bar_xdomain(a):
    return _bar_vals_for_domain(a) if _bar_horizontal(a) else a["cats"]


def _bar_ydomain(a):
    return a["cats"] if _bar_horizontal(a) else _bar_vals_for_domain(a)


def _bar_data_attrs(a):
    flat = [v for s in a["series"] for v in s
            if isinstance(v, (int, float)) and v == v]
    out = {"n": len(a["cats"])}
    if flat:
        out["y-min"] = min(flat)
        out["y-max"] = max(flat)
    return out


def _bar_draw(a, ctx):
    cats = a["cats"]
    groups = a["groups"]
    series = a["series"]
    position = a["_position"]
    opts = a["opts"]
    palette = opts.get("palette")
    horizontal = _bar_horizontal(a)
    cat_scale, val_scale = ((ctx.y_scale, ctx.x_scale) if horizontal
                            else (ctx.x_scale, ctx.y_scale))
    band = getattr(cat_scale, "bandwidth", None)
    if band is None:
        axis = "y" if horizontal else "x"
        raise TypeError(
            f"bar places categories on a band {axis}-axis, but this "
            f"chart's {axis}-axis resolved to a numeric scale (an "
            f"explicit {axis}lim= does that) — there are no bands to "
            f"size the bars. For bars at numeric positions, use the "
            f"numeric_bar extension: import plotlet.extensions."
            f"numeric_bar, then c.numeric_bar(...).")
    bottom = opts.get("bottom", 0)
    base_px = val_scale(bottom)
    alpha = opts.get("alpha", _D["bar_alpha"])
    stroke = resolve_color(opts.get("color"))
    lw = opts.get("linewidth", _D["linewidth"]) if stroke else 1
    sr = "crispEdges" if getattr(cat_scale, "padding", 0.2) == 0 else None
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    multi = len(series) > 1

    if multi and position == "fill":
        totals = [sum(s[i] for s in series) or 1 for i in range(len(cats))]
        series = [[s[i] / totals[i] for i in range(len(cats))] for s in series]

    err_lo, err_hi = a.get("err_lo"), a.get("err_hi")
    ecolor = resolve_color(opts.get("ecolor", _D["bar_ecolor"]))
    capsize = opts.get("capsize", _D["errorbar_capsize"])
    elw = _D["errorbar_linewidth"]

    out = []
    def _emit(x, y, w, h, col):
        out.append(draw_rect(x, y, w, h, fill=col, stroke=stroke,
                             stroke_width=lw, dash=opts.get("linestyle"),
                             alpha=alpha, shape_rendering=sr, project=ctx.warp))

    def _emit_err(cat_px, j, i, v):
        if err_lo is None:
            return
        lo, hi = err_lo[j][i], err_hi[j][i]
        if not (lo or hi):
            return
        p0, p1 = val_scale(v - lo), val_scale(v + hi)
        if horizontal:
            out.append(errorbar_h(cat_px, p0, p1, capsize=capsize,
                                  color=ecolor, width=elw, project=ctx.warp))
        else:
            out.append(errorbar_v(cat_px, p0, p1, capsize=capsize,
                                  color=ecolor, width=elw, project=ctx.warp))

    if multi and position in ("stack", "fill"):
        running = [0.0] * len(cats)
        for j, s in enumerate(series):
            col = _group_fill(groups, palette, j, fill_fallback)
            for i, (cat, v) in enumerate(zip(cats, s)):
                cp = cat_scale(cat) - band / 2
                bot_px = val_scale(running[i])
                top_px = val_scale(running[i] + v)
                _emit(*band_rect(cp, band, bot_px, top_px,
                                 horizontal=horizontal), col)
                running[i] += v
    elif multi and position == "dodge":
        width = opts.get("width", DODGE_WIDTH)
        gap = opts.get("gap", DODGE_GAP)
        redundant = opts.get("_redundant_grouping", False)
        for j, s in enumerate(series):
            col = _group_fill(groups, palette, j, fill_fallback)
            for i, (cat, v) in enumerate(zip(cats, s)):
                cp, slot_w = dodge_positions(cat_scale, cat,
                                             1 if redundant else len(groups),
                                             0 if redundant else j,
                                             band_frac=width, gap=gap)
                vp = val_scale(v)
                _emit(*band_rect(cp - slot_w / 2, slot_w, base_px, vp,
                                 horizontal=horizontal), col)
                _emit_err(cp, j, i, v)
    else:
        col = fill_fallback
        for i, (cat, v) in enumerate(zip(cats, series[0])):
            cp = cat_scale(cat) - band / 2
            vp = val_scale(v)
            _emit(*band_rect(cp, band, base_px, vp,
                             horizontal=horizontal), col)
            _emit_err(cat_scale(cat), 0, i, v)

    return "".join(out)


def _bar_legend_entries(a):
    groups = a["groups"]
    opts = a["opts"]
    alpha = opts.get("alpha", _D["bar_alpha"])
    sw = _LEGSPEC["swatch_width"]
    if groups == [None]:
        label = opts.get("label")
        if not label:
            return []
        def paint(_a, _ctx, x0, y_mid):
            return draw_rect(x0, y_mid - 5, sw, 10,
                             fill=_a["_color"], alpha=alpha)
        return [{"label": label, "color": a.get("_color"), "paint": paint}]
    palette = opts.get("palette")
    entries = []
    for j, g in enumerate(groups):
        col = _group_fill(groups, palette, j, a.get("_color"))
        def paint(_a, _ctx, x0, y_mid, _col=col, _alpha=alpha):
            return draw_rect(x0, y_mid - 5, sw, 10, fill=_col, alpha=_alpha)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="bar",
    record=_bar_record,
    xdomain=_bar_xdomain,
    ydomain=_bar_ydomain,
    draw=_bar_draw,
    legend_entries=_bar_legend_entries,
    data_attrs=_bar_data_attrs,
    force_zero_y=lambda a: not _bar_horizontal(a),
    force_zero_x=_bar_horizontal,
))
