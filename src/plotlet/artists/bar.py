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
from ..utils import (UNSET, pack_opts, to_list, resolve_aes, dodge_positions,
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


def _stat_cells(data, x_col, y_col, group_col, stat):
    """Bucket rows into per-(group, cat) value lists. `stat='mean'`
    drops NaN/None rows; other stats keep every row."""
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
    return cats, groups, cells


def _mean_ci_offsets(cells, series, n_cats, n_groups, ci, level, n_boot, seed):
    """CI bounds per cell → whisker offset grids around the drawn bar
    top. A bound-less (empty) cell keeps a zero offset, so the 0-height
    bar has no whisker."""
    rng = random.Random(seed)
    mean_fn = lambda v: sum(v) / len(v) if v else float("nan")
    los, his = ci_bounds([c for row in cells for c in row], mean_fn, "mean",
                         ci, level, n_boot, rng)
    err_lo = [[0.0] * n_cats for _ in range(n_groups)]
    err_hi = [[0.0] * n_cats for _ in range(n_groups)]
    for j in range(n_groups):
        for i in range(n_cats):
            lo, hi = los[j * n_cats + i], his[j * n_cats + i]
            if lo != lo:
                continue
            err_lo[j][i] = series[j][i] - lo
            err_hi[j][i] = hi - series[j][i]
    return err_lo, err_hi


def _aggregate_stat(data, x_col, y_col, group_col, stat, ci,
                    level, n_boot, seed):
    """Row-level table → per-(group, cat) stat aggregation. `stat='count'`
    counts rows per cell; `stat='mean'` averages y per cell (NaN/None rows
    dropped), with `ci` supplying err_lo/err_hi offset grids shaped like
    `series` (None when `ci` is None). Empty cells aggregate to 0 with no
    error bar."""
    cats, groups, cells = _stat_cells(data, x_col, y_col, group_col, stat)
    if stat == "count":
        return cats, groups, [[len(c) for c in row] for row in cells], None, None
    series = [[(sum(c) / len(c) if c else 0.0) for c in row] for row in cells]
    if ci is None:
        return cats, groups, series, None, None
    err_lo, err_hi = _mean_ci_offsets(cells, series, len(cats), len(groups),
                                      ci, level, n_boot, seed)
    return cats, groups, series, err_lo, err_hi


def _resolve_stat_ci(stat, data, x, y, ci):
    """Validate the stat/ci corner of the signature and resolve the ci
    default. `ci=None` is meaningful (mean bars without a CI), so unset
    gets a sentinel default rather than None."""
    if stat not in _STATS:
        raise ValueError(
            f"unknown stat={stat!r}; expected one of {_STATS}."
        )
    if data is None or x is None or (y is None and stat != "count"):
        raise TypeError(
            "bar requires data=, x=, y= (fill= optional)."
        )
    if stat == "count" and y is not None:
        raise TypeError(
            "bar: stat='count' counts rows per category — drop y=."
        )
    if ci is UNSET:
        ci = "t" if stat == "mean" else None
    if ci is not None and stat != "mean":
        raise TypeError("bar: ci= applies to stat='mean'.")
    validate_ci("bar", ci)
    return ci


def _resolve_err_spec(stat, orientation, bottom, yerr, xerr):
    """Validate the error-bar corner of the signature and pick the
    value-axis spec: yerr for vertical bars, xerr for horizontal."""
    if bottom is not None and hasattr(bottom, "__iter__") \
            and not isinstance(bottom, str):
        raise TypeError(
            "bar: bottom= must be a scalar baseline; for grouped bars "
            "pass fill='series_col' with position='stack'."
        )
    if stat != "identity" and (yerr is not None or xerr is not None):
        raise TypeError(
            "bar: stat= aggregates for you — stat='mean' supplies error "
            "bars from the CI; drop yerr=/xerr=."
        )
    horizontal = orientation == "h"
    if yerr is not None and horizontal:
        raise TypeError("bar: horizontal bars take xerr= (the value axis is x).")
    if xerr is not None and not horizontal:
        raise TypeError("bar: vertical bars take yerr= (the value axis is y).")
    return xerr if horizontal else yerr


def _resolve_position(position, n_series, err, stat):
    """Default and validate `position`. Multi-series defaults to
    "stack", except with error bars or stat='mean', which default to
    "dodge" (error bars aren't defined for stacked bars, and stacked
    means are misleading). Single-series stays None."""
    if position is None:
        if n_series == 1:
            return None
        return "dodge" if (err is not None or stat == "mean") else "stack"
    if position not in _POSITIONS:
        raise ValueError(
            f"unknown position={position!r}; expected one of {_POSITIONS}."
        )
    if stat == "mean" and position in ("stack", "fill"):
        raise ValueError(
            f"bar: stacked means are misleading — stat='mean' takes "
            f"position='dodge', not {position!r}."
        )
    return position


def _bar_record(data=None,
                # input & aggregation — consumed here at record
                x=None, y=None, fill=None,
                stat="identity", ci=UNSET, level=0.95, n_boot=1000, seed=0,
                position=None, yerr=None, xerr=None,
                # style — packed into opts for the draw/legend/attrs side
                orientation=None, bottom=None, width=None, gap=None,
                color=None, alpha=None, linewidth=None, linestyle=None,
                ecolor=None, capsize=None, palette=None,
                label=None, legend=None):
    ci = _resolve_stat_ci(stat, data, x, y, ci)
    # `fill=` may be a literal color or a column name. Column → drives
    # grouping; literal → applied to every bar.
    fill_kind, fill_value = resolve_aes(data, fill)
    group_col = fill if fill_kind == "column" else None
    stat_err_lo = stat_err_hi = None
    if stat == "identity":
        cats, groups, series = _aggregate_long(data, x, y, group_col)
    else:
        cats, groups, series, stat_err_lo, stat_err_hi = _aggregate_stat(
            data, x, y, group_col, stat, ci, level, n_boot, seed)
    opts = pack_opts(orientation=orientation, bottom=bottom, width=width,
                     gap=gap, color=color, alpha=alpha, linewidth=linewidth,
                     linestyle=linestyle, ecolor=ecolor, capsize=capsize,
                     palette=palette, label=label, legend=legend)
    if fill_kind == "literal":
        opts["_fill_literal"] = fill_value
    if group_col is not None and group_col == x:
        opts["_redundant_grouping"] = True
    err = _resolve_err_spec(stat, orientation, bottom, yerr, xerr)
    position = _resolve_position(position, len(series), err, stat)
    rec = {"type": "bar", "cats": cats, "groups": groups, "series": series,
           "_position": position, "opts": opts}
    if err is not None:
        if position in ("stack", "fill"):
            raise ValueError(
                f"bar: yerr/xerr isn't defined for position={position!r} — "
                f"use position='dodge'."
            )
        rec["err_lo"], rec["err_hi"] = _aggregate_err(
            data, x, group_col, err, cats, groups)
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


def _draw_env(a, ctx):
    """Per-draw geometry + style environment, derived once and read by
    the stack / dodge / single passes below: scales picked by
    orientation, band width, baseline pixel, fill-normalized series,
    rect styling, and the error-bar treatment. Plain dict."""
    opts = a["opts"]
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
            f"size the bars. For bars at numeric positions, use "
            f"c.numeric_bar(...).")
    series = a["series"]
    multi = len(series) > 1
    if multi and a["_position"] == "fill":
        cats = a["cats"]
        totals = [sum(s[i] for s in series) or 1 for i in range(len(cats))]
        series = [[s[i] / totals[i] for i in range(len(cats))] for s in series]
    stroke = resolve_color(opts.get("color"))
    fill_literal = resolve_color(opts.get("_fill_literal"))
    return {
        "opts": opts, "horizontal": horizontal,
        "cat_scale": cat_scale, "val_scale": val_scale, "band": band,
        "series": series, "multi": multi,
        "base_px": val_scale(opts.get("bottom", 0)),
        "alpha": opts.get("alpha", _D["bar_alpha"]),
        "stroke": stroke,
        "lw": opts.get("linewidth", _D["linewidth"]) if stroke else 1,
        "sr": "crispEdges" if getattr(cat_scale, "padding", 0.2) == 0 else None,
        "fill_fallback": fill_literal if fill_literal is not None else ctx.color,
        "err_lo": a.get("err_lo"), "err_hi": a.get("err_hi"),
        "ecolor": resolve_color(opts.get("ecolor", _D["bar_ecolor"])),
        "capsize": opts.get("capsize", _D["errorbar_capsize"]),
        "warp": ctx.warp,
    }


def _bar_rect(env, x, y, w, h, col):
    return draw_rect(x, y, w, h, fill=col, stroke=env["stroke"],
                     stroke_width=env["lw"],
                     dash=env["opts"].get("linestyle"),
                     alpha=env["alpha"], shape_rendering=env["sr"],
                     project=env["warp"])


def _bar_whisker(env, cat_px, j, i, v):
    if env["err_lo"] is None:
        return ""
    lo, hi = env["err_lo"][j][i], env["err_hi"][j][i]
    if not (lo or hi):
        return ""
    p0, p1 = env["val_scale"](v - lo), env["val_scale"](v + hi)
    whisker = errorbar_h if env["horizontal"] else errorbar_v
    return whisker(cat_px, p0, p1, capsize=env["capsize"],
                   color=env["ecolor"], width=_D["errorbar_linewidth"],
                   project=env["warp"])


def _stack_pass(a, env):
    """position="stack" / "fill": groups pile on a per-category running
    total from 0 (fill-normalized series come pre-divided in env)."""
    cats, groups = a["cats"], a["groups"]
    palette = env["opts"].get("palette")
    cat_scale, val_scale, band = env["cat_scale"], env["val_scale"], env["band"]
    out = []
    running = [0.0] * len(cats)
    for j, s in enumerate(env["series"]):
        col = _group_fill(groups, palette, j, env["fill_fallback"])
        for i, (cat, v) in enumerate(zip(cats, s)):
            cp = cat_scale(cat) - band / 2
            bot_px = val_scale(running[i])
            top_px = val_scale(running[i] + v)
            out.append(_bar_rect(env, *band_rect(cp, band, bot_px, top_px,
                                                 horizontal=env["horizontal"]),
                                 col))
            running[i] += v
    return out


def _dodge_pass(a, env):
    """position="dodge": per-group slots inside the band, whiskers at
    slot centers. Redundant grouping (fill= names the x column) claims
    the full band for every bar."""
    cats, groups = a["cats"], a["groups"]
    opts = env["opts"]
    palette = opts.get("palette")
    width = opts.get("width", DODGE_WIDTH)
    gap = opts.get("gap", DODGE_GAP)
    redundant = opts.get("_redundant_grouping", False)
    out = []
    for j, s in enumerate(env["series"]):
        col = _group_fill(groups, palette, j, env["fill_fallback"])
        for i, (cat, v) in enumerate(zip(cats, s)):
            cp, slot_w = dodge_positions(env["cat_scale"], cat,
                                         1 if redundant else len(groups),
                                         0 if redundant else j,
                                         band_frac=width, gap=gap)
            vp = env["val_scale"](v)
            out.append(_bar_rect(env, *band_rect(cp - slot_w / 2, slot_w,
                                                 env["base_px"], vp,
                                                 horizontal=env["horizontal"]),
                                 col))
            out.append(_bar_whisker(env, cp, j, i, v))
    return out


def _single_pass(a, env):
    """Single series: one bar per category at full band width, rising
    from the baseline; whiskers at band centers."""
    cat_scale, val_scale, band = env["cat_scale"], env["val_scale"], env["band"]
    out = []
    for i, (cat, v) in enumerate(zip(a["cats"], env["series"][0])):
        cp = cat_scale(cat) - band / 2
        vp = val_scale(v)
        out.append(_bar_rect(env, *band_rect(cp, band, env["base_px"], vp,
                                             horizontal=env["horizontal"]),
                             env["fill_fallback"]))
        out.append(_bar_whisker(env, cat_scale(cat), 0, i, v))
    return out


def _bar_draw(a, ctx):
    env = _draw_env(a, ctx)
    position = a["_position"]
    if env["multi"] and position in ("stack", "fill"):
        parts = _stack_pass(a, env)
    elif env["multi"] and position == "dodge":
        parts = _dodge_pass(a, env)
    else:
        parts = _single_pass(a, env)
    return "".join(parts)


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
