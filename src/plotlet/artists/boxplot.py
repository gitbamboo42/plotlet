"""Tukey-style box-and-whisker: Q1-Q3 box, median line, 1.5*IQR whiskers, outlier dots.

Long-form only:
  c.boxplot(data=df, x="cat", y="value")
  c.boxplot(data=df, x="cat", y="value", fill="group", palette={...})

Long-form with `fill="col"` dodges sub-boxes side-by-side within each cat and
emits one legend entry per group level. A literal `fill="#hex"` paints every
box the same color; `fill=False` leaves them outline-only.

Aesthetics:
  fill=True/<col>/<literal>/False  body fill (True = palette/cycle default,
                                   col = column-driven grouping, literal
                                   color string, or False for outline-only)
  color=<literal>      box / whisker / cap stroke (defaults to frame color)
  palette=             maps group levels → fills when `fill=` is a column

Other styling kwargs:
  orientation='v'       'h' for horizontal (cats on y axis)
  width=0.6             total dodge-group width as a band fraction
  gap=0.1               slot-gap fraction between dodged boxes
  fill_alpha=0.55       box-fill opacity
  linewidth=1           border / whisker / cap stroke width
  median_linewidth=1.6  median line stroke width
  notch=False           draw 95 % CI waist on the box
  showmeans=False       show mean as a small triangle marker
  mean_marker='^'       marker kind for the mean indicator
  whis=1.5              IQR multiplier for whisker fences
  showfliers=True       False hides outliers
  flier_size=2.2        outlier-marker radius
  flier_color=<color>   override outlier stroke color
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import (quantile, resolve_aes, palette_color,
                     dodge_positions, categorical_groups)
from ..utils import _drop_nan
from ..draw import TAB10, resolve_color
from ..draw import segment, rect, circle, errorbar_v, errorbar_h, polygon, marker
from .._spec import _FRAME


def _resolve_fill_kwarg(data, kw):
    """Pop `fill=` and classify it. Returns `(do_fill, fill_literal,
    group_col)` where `fill_literal` is a hex / CSS color string (None
    when the user did not pass a literal) and `group_col` is a column
    name (None when fill is not column-driven).

    `fill=True` → defaults; `fill=False` → outline-only; literal string →
    same color for every box; column name → drives grouping."""
    fill = kw.pop("fill", True)
    if fill is False or fill is None:
        return False, None, None
    if fill is True:
        return True, None, None
    kind, value = resolve_aes(data, fill)
    if kind == "column":
        return True, None, fill
    return True, value, None


def _boxplot_record(args, kw):
    if args:
        raise TypeError(
            "boxplot requires long-form input: "
            "c.boxplot(data=df, x='col', y='col', fill='col')."
        )
    data = kw.pop("data", None)
    x = kw.pop("x", None)
    y = kw.pop("y", None)
    if data is None or x is None or y is None:
        raise TypeError(
            "boxplot requires data=, x=, y= (fill= optional)."
        )
    do_fill, fill_literal, group_col = _resolve_fill_kwarg(data, kw)
    cats, groups, vals = categorical_groups(data, x, y, group_col)
    kw["_do_fill"] = do_fill
    if fill_literal is not None:
        kw["_fill_literal"] = fill_literal
    # `fill=<x_col>` is redundant grouping — each cat has exactly one
    # nonempty group, so dodging would just shrink the box uselessly.
    # Suppress dodge but keep the per-cat palette coloring.
    if group_col is not None and group_col == x:
        kw["_redundant_grouping"] = True
    return {"type": "boxplot", "cats": cats, "groups": groups,
            "vals": vals, "opts": kw}


def _boxplot_horizontal(a): return a["opts"].get("orientation") == "h"
def _boxplot_values(a):
    return [v for row in a["vals"] for g in row for v in g]


def _boxplot_xdomain(a):
    return _boxplot_values(a) if _boxplot_horizontal(a) else a["cats"]


def _boxplot_ydomain(a):
    return a["cats"] if _boxplot_horizontal(a) else _boxplot_values(a)


def _group_fill(groups, palette, j, fallback):
    """Per-group fill: ungrouped → fallback; grouped → palette lookup
    with TAB10 wraparound."""
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def _boxplot_draw(a, ctx):
    cats, groups, vals = a["cats"], a["groups"], a["vals"]
    n_groups = len(groups)
    opts = a["opts"]
    palette = opts.get("palette")
    bw_frac    = opts.get("width", 0.6)
    gap        = opts.get("gap", 0.1)
    fill_alpha = opts.get("fill_alpha", 0.55)
    lw         = opts.get("linewidth", 1)
    median_lw  = opts.get("median_linewidth", 1.6)
    whis       = opts.get("whis", 1.5)
    flier_size = opts.get("flier_size", 2.2)
    show_fliers = opts.get("showfliers", True)
    show_means = opts.get("showmeans", False)
    mean_marker_k = opts.get("mean_marker", "^")
    notch      = opts.get("notch", False)
    do_fill    = opts.get("_do_fill", True)
    line       = resolve_color(opts.get("color")) or _FRAME["color"]
    flier_line = resolve_color(opts.get("flier_color")) or line
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    horizontal = _boxplot_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    eb_along_val = errorbar_h if horizontal else errorbar_v
    redundant = opts.get("_redundant_grouping", False)
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_groups):
            vs = _drop_nan(vals[i][j])
            if not vs:
                continue
            fill = _group_fill(groups, palette, j, fill_fallback) if do_fill else None
            cp, box_w = dodge_positions(cat_scale, cat,
                                        1 if redundant else n_groups,
                                        0 if redundant else j,
                                        band_frac=bw_frac, gap=gap)
            cp_lo = cp - box_w / 2
            cp_hi = cp + box_w / 2
            q1 = quantile(vs, 0.25)
            q2 = quantile(vs, 0.50)
            q3 = quantile(vs, 0.75)
            iqr = q3 - q1
            lo_fence = q1 - whis * iqr
            hi_fence = q3 + whis * iqr
            inliers = [v for v in vs if lo_fence <= v <= hi_fence]
            outliers = [v for v in vs if v < lo_fence or v > hi_fence] if show_fliers else []
            whisker_lo = min(inliers) if inliers else q1
            whisker_hi = max(inliers) if inliers else q3
            vp_q1 = val_scale(q1)
            vp_q2 = val_scale(q2)
            vp_q3 = val_scale(q3)
            vp_lo = val_scale(whisker_lo)
            vp_hi = val_scale(whisker_hi)

            if notch:
                # 95 % CI of the median ≈ 1.57 * IQR / sqrt(n). Cap at the
                # IQR halves so the indent never crosses Q1 or Q3.
                n_samples = len(vs)
                ci = 1.57 * iqr / math.sqrt(n_samples) if n_samples > 0 else 0
                ci = min(ci, (q2 - q1), (q3 - q2))
                vp_ci_lo = val_scale(q2 - ci)
                vp_ci_hi = val_scale(q2 + ci)
                inset = box_w * 0.2
                cp_lo_in = cp_lo + inset
                cp_hi_in = cp_hi - inset
                pts = [
                    (cp_lo,    vp_q1),
                    (cp_hi,    vp_q1),
                    (cp_hi,    vp_ci_lo),
                    (cp_hi_in, vp_q2),
                    (cp_hi,    vp_ci_hi),
                    (cp_hi,    vp_q3),
                    (cp_lo,    vp_q3),
                    (cp_lo,    vp_ci_hi),
                    (cp_lo_in, vp_q2),
                    (cp_lo,    vp_ci_lo),
                ]
                if horizontal:
                    pts = [(y, x) for x, y in pts]
                out.append(polygon(pts, fill=fill, stroke=line, stroke_width=lw,
                                   fill_alpha=fill_alpha if do_fill else 1.0,
                                   project=ctx.warp))
                if horizontal:
                    median = (vp_q2, cp_lo_in, vp_q2, cp_hi_in)
                else:
                    median = (cp_lo_in, vp_q2, cp_hi_in, vp_q2)
            else:
                if horizontal:
                    rect_xy = (min(vp_q1, vp_q3), cp_lo)
                    rect_wh = (abs(vp_q3 - vp_q1), box_w)
                    median = (vp_q2, cp_lo, vp_q2, cp_hi)
                else:
                    rect_xy = (cp_lo, min(vp_q1, vp_q3))
                    rect_wh = (box_w, abs(vp_q3 - vp_q1))
                    median = (cp_lo, vp_q2, cp_hi, vp_q2)
                out.append(rect(rect_xy[0], rect_xy[1], rect_wh[0], rect_wh[1],
                                fill=fill, stroke=line, stroke_width=lw,
                                fill_alpha=fill_alpha if do_fill else 1.0,
                                project=ctx.warp))

            out.append(segment(median[0], median[1], median[2], median[3],
                               color=line, width=median_lw, project=ctx.warp))
            cap_w = box_w * 0.4
            out.append(eb_along_val(cp, vp_q3, vp_hi, capsize=cap_w,
                                    color=line, width=lw, project=ctx.warp))
            out.append(eb_along_val(cp, vp_q1, vp_lo, capsize=cap_w,
                                    color=line, width=lw, project=ctx.warp))
            if show_means:
                mean_v = sum(vs) / len(vs)
                vp_m = val_scale(mean_v)
                cx_m, cy_m = (vp_m, cp) if horizontal else (cp, vp_m)
                out.append(marker(mean_marker_k, cx_m, cy_m,
                                  flier_size * 1.5, line, 1,
                                  edgecolor=fill if do_fill else None,
                                  edgewidth=lw * 0.8, project=ctx.warp))
            for v in outliers:
                vp = val_scale(v)
                cx_dot, cy_dot = (vp, cp) if horizontal else (cp, vp)
                out.append(circle(cx_dot, cy_dot, flier_size,
                                  stroke=flier_line, stroke_width=lw * 0.9,
                                  project=ctx.warp))
    return "".join(out)


def _boxplot_legend_entries(a):
    groups = a["groups"]
    if groups == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    fill_alpha = opts.get("fill_alpha", 0.55)
    lw = opts.get("linewidth", 1)
    do_fill = opts.get("_do_fill", True)
    line = resolve_color(opts.get("color")) or _FRAME["color"]
    entries = []
    for j, g in enumerate(groups):
        col = _group_fill(groups, palette, j, line)
        fill = col if do_fill else None
        def paint(_a, _ctx, _x0, _y_mid,
                  _fill=fill, _line=line, _lw=lw, _fa=fill_alpha):
            return rect(_x0, _y_mid - 5, 22, 10,
                        fill=_fill, stroke=_line, stroke_width=_lw,
                        fill_alpha=_fa if _fill else 1.0)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="boxplot",
    record=_boxplot_record,
    xdomain=_boxplot_xdomain,
    ydomain=_boxplot_ydomain,
    draw=_boxplot_draw,
    legend_entries=_boxplot_legend_entries,
))
