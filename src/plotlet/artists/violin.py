"""Mirrored KDE outline per category with a mini-boxplot inside.

Long-form only:
  c.violin(data=df, x="cat", y="value")
  c.violin(data=df, x="cat", y="value", fill="group", palette={...})

Long-form with `fill="col"` dodges sub-violins side-by-side within each cat
and emits one legend entry per group level.

Aesthetics:
  fill=True/<col>/<literal>/False  body fill (True = palette/cycle default,
                                   col = column-driven grouping, literal
                                   color string, or False for outline-only)
  color=<literal>      outline / inner-box stroke (defaults to frame color)
  palette=             maps group levels → fills when `fill=` is a column

Other styling kwargs:
  orientation='v'       'h' for horizontal (cats on y axis)
  width=0.8             total dodge-group width as a band fraction
  gap=0.1               slot-gap fraction between dodged violins
  inner='box'           'box' mini-boxplot (Q1-Q3 + median + whiskers),
                        'quartile' three dashed Q1/Q2/Q3 lines, None KDE only
  trim=True             clip KDE at min/max of data; False extends 10 % past
  fill_alpha=0.4        body-fill opacity
  linewidth=1           outline / inner-box stroke width
  whis=1.5              IQR multiplier for whisker fences (inner='box')
  inner_box_fill=<bg>   mini-boxplot fill; defaults to figure background so
                        the box reads as negative space on any theme
  n_grid=80             KDE evaluation grid resolution
  bw_adjust=1.0         Silverman bandwidth multiplier (>1 smoother)
"""
from ..registry import ArtistSpec, add_artist
from ..utils import (quantile, resolve_aes, palette_color,
                     dodge_positions, categorical_groups,
                     silverman_bw, kde_1d)
from ..utils import _drop_nan
from ..draw import TAB10, resolve_color
from ..draw import path, rect, segment
from .._spec import _FRAME, _FIGSPEC


def _resolve_fill_kwarg(data, kw):
    fill = kw.pop("fill", True)
    if fill is False or fill is None:
        return False, None, None
    if fill is True:
        return True, None, None
    kind, value = resolve_aes(data, fill)
    if kind == "column":
        return True, None, fill
    return True, value, None


def _violin_record(args, kw):
    if args:
        raise TypeError(
            "violin requires long-form input: "
            "c.violin(data=df, x='col', y='col', fill='col')."
        )
    data = kw.pop("data", None)
    x = kw.pop("x", None)
    y = kw.pop("y", None)
    if data is None or x is None or y is None:
        raise TypeError(
            "violin requires data=, x=, y= (fill= optional)."
        )
    do_fill, fill_literal, group_col = _resolve_fill_kwarg(data, kw)
    cats, groups, vals = categorical_groups(data, x, y, group_col)
    kw["_do_fill"] = do_fill
    if fill_literal is not None:
        kw["_fill_literal"] = fill_literal
    return {"type": "violin", "cats": cats, "groups": groups,
            "vals": vals, "opts": kw}


def _violin_horizontal(a): return a["opts"].get("orientation") == "h"
def _violin_values(a):
    return [v for row in a["vals"] for g in row for v in g]


def _violin_xdomain(a):
    return _violin_values(a) if _violin_horizontal(a) else a["cats"]


def _violin_ydomain(a):
    return a["cats"] if _violin_horizontal(a) else _violin_values(a)


def _group_fill(groups, palette, j, fallback):
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def _violin_draw(a, ctx):
    cats, groups, vals = a["cats"], a["groups"], a["vals"]
    n_groups = len(groups)
    opts = a["opts"]
    palette    = opts.get("palette")
    w_frac     = opts.get("width", 0.8)
    gap        = opts.get("gap", 0.1)
    inner      = opts.get("inner", "box")
    trim       = opts.get("trim", True)
    n_grid     = opts.get("n_grid", 80)
    bw_adjust  = opts.get("bw_adjust", 1.0)
    fill_alpha = opts.get("fill_alpha", 0.4)
    lw         = opts.get("linewidth", 1)
    whis       = opts.get("whis", 1.5)
    do_fill    = opts.get("_do_fill", True)
    line       = resolve_color(opts.get("color")) or _FRAME["color"]
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    horizontal = _violin_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_groups):
            vs = _drop_nan(vals[i][j])
            if not vs:
                continue
            fill = _group_fill(groups, palette, j, fill_fallback) if do_fill else None
            cp, slot_w = dodge_positions(cat_scale, cat, n_groups, j,
                                          band_frac=w_frac, gap=gap)
            half_w_px = slot_w / 2

            bw = silverman_bw(vs) * bw_adjust
            lo, hi = min(vs), max(vs)
            pad = 0 if trim else ((hi - lo) * 0.1 or 1.0)
            grid = [lo - pad + (hi - lo + 2 * pad) * k / (n_grid - 1)
                    for k in range(n_grid)]
            d = kde_1d(vs, grid, bw)
            dmax = max(d) or 1.0

            left = []; right = []
            for gx, dy in zip(grid, d):
                d_px = (dy / dmax) * half_w_px
                vp = val_scale(gx)
                if horizontal:
                    left.append((vp, cp - d_px))
                    right.append((vp, cp + d_px))
                else:
                    left.append((cp - d_px, vp))
                    right.append((cp + d_px, vp))
            pts = left + right[::-1]
            path_d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"
            out.append(path(path_d, fill=fill, stroke=line, stroke_width=lw,
                            fill_alpha=fill_alpha if do_fill else 1.0))

            q1 = quantile(vs, 0.25)
            q2 = quantile(vs, 0.50)
            q3 = quantile(vs, 0.75)
            vp_q1 = val_scale(q1)
            vp_q2 = val_scale(q2)
            vp_q3 = val_scale(q3)
            if inner == "box":
                box_half = half_w_px * 0.18
                box_fill = opts.get("inner_box_fill", _FIGSPEC["background"])
                iqr = q3 - q1
                lo_fence = q1 - whis * iqr
                hi_fence = q3 + whis * iqr
                inliers = [v for v in vs if lo_fence <= v <= hi_fence]
                whisker_lo = min(inliers) if inliers else q1
                whisker_hi = max(inliers) if inliers else q3
                vp_wlo = val_scale(whisker_lo)
                vp_whi = val_scale(whisker_hi)
                if horizontal:
                    out.append(segment(vp_wlo, cp, vp_q1, cp, color=line, width=lw))
                    out.append(segment(vp_q3, cp, vp_whi, cp, color=line, width=lw))
                    out.append(rect(min(vp_q1, vp_q3), cp - box_half,
                                    abs(vp_q3 - vp_q1), 2 * box_half,
                                    fill=box_fill, stroke=line, stroke_width=lw))
                    out.append(segment(vp_q2, cp - box_half, vp_q2, cp + box_half,
                                       color=line, width=lw))
                else:
                    out.append(segment(cp, vp_wlo, cp, vp_q1, color=line, width=lw))
                    out.append(segment(cp, vp_q3, cp, vp_whi, color=line, width=lw))
                    out.append(rect(cp - box_half, min(vp_q1, vp_q3),
                                    2 * box_half, abs(vp_q3 - vp_q1),
                                    fill=box_fill, stroke=line, stroke_width=lw))
                    out.append(segment(cp - box_half, vp_q2, cp + box_half, vp_q2,
                                       color=line, width=lw))
            elif inner == "quartile":
                for q in (q1, q2, q3):
                    vp = val_scale(q)
                    if horizontal:
                        out.append(segment(vp, cp - half_w_px * 0.7,
                                           vp, cp + half_w_px * 0.7,
                                           color=line, width=lw, dash="3,2"))
                    else:
                        out.append(segment(cp - half_w_px * 0.7, vp,
                                           cp + half_w_px * 0.7, vp,
                                           color=line, width=lw, dash="3,2"))
    return "".join(out)


def _violin_legend_entries(a):
    groups = a["groups"]
    if groups == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    fill_alpha = opts.get("fill_alpha", 0.4)
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
    name="violin",
    record=_violin_record,
    xdomain=_violin_xdomain,
    ydomain=_violin_ydomain,
    draw=_violin_draw,
    legend_entries=_violin_legend_entries,
))
