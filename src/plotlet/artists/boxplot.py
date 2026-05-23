"""Tukey-style box-and-whisker: Q1-Q3 box, median line, 1.5*IQR whiskers, outlier dots.

Wide-form: c.boxplot(cats, values_per_cat)
Long-form:  c.boxplot(data=df, x="cat", y="value", hue="group", palette={...})

Long-form with `hue=` dodges sub-boxes side-by-side within each cat and emits
one legend entry per hue category.

Styling kwargs:
  orientation='v'       'h' for horizontal (cats on y axis)
  width=0.6             total dodge-group width as a band fraction
  gap=0.1               slot-gap fraction between dodged boxes
  fill=True             False for outline-only boxes
  fill_alpha=0.55       box-fill opacity
  linecolor=<themed>    border / whisker / cap color
  linewidth=1           border / whisker / cap stroke width
  median_linewidth=1.6  median line stroke width
  notch=False           draw 95 % CI waist on the box
  showmeans=False       show mean as a small triangle marker
  mean_marker='^'       marker kind for the mean indicator
  whis=1.5              IQR multiplier for whisker fences
  showfliers=True       False hides outliers
  flier_size=2.2        outlier-marker radius
  flier_color=<linecolor>  override outlier stroke color
"""
import math

from ..registry import ArtistSpec, add_artist
from ..utils import to_list, quantile, hue_color, dodge_positions, categorical_groups
from ..utils import _drop_nan
from ..draw import segment, rect, circle, errorbar_v, errorbar_h, polygon, marker
from .._spec import _FRAME


def _boxplot_record(args, kw):
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x = kw.pop("x", None)
        y = kw.pop("y", None)
        hue = kw.pop("hue", None)
        if data is None or x is None or y is None:
            raise TypeError(
                "boxplot long-form requires data=, x=, y= (hue= optional)."
            )
        cats, hues, groups = categorical_groups(data, x, y, hue)
    elif len(args) >= 2:
        cats = to_list(args[0])
        groups_1d = [list(to_list(g)) for g in args[1]]
        hues = [None]
        groups = [[g] for g in groups_1d]
    else:
        raise TypeError(
            "boxplot requires either positional (cats, values_per_cat) "
            "or keyword (data=, x=, y=)."
        )
    return {"type": "boxplot", "cats": cats, "hues": hues,
            "groups": groups, "opts": kw}


def _boxplot_horizontal(a): return a["opts"].get("orientation") == "h"
def _boxplot_values(a):
    return [v for row in a["groups"] for g in row for v in g]


def _boxplot_xdomain(a):
    return _boxplot_values(a) if _boxplot_horizontal(a) else a["cats"]


def _boxplot_ydomain(a):
    return a["cats"] if _boxplot_horizontal(a) else _boxplot_values(a)


def _boxplot_draw(a, ctx):
    cats, hues, groups = a["cats"], a["hues"], a["groups"]
    n_hues = len(hues)
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
    do_fill    = opts.get("fill", True)
    line       = opts.get("linecolor", _FRAME["color"])
    flier_line = opts.get("flier_color", line)
    horizontal = _boxplot_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    eb_along_val = errorbar_h if horizontal else errorbar_v
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_hues):
            vals = _drop_nan(groups[i][j])
            if not vals:
                continue
            fill = hue_color(hues, palette, j, ctx.color) if do_fill else None
            cp, box_w = dodge_positions(cat_scale, cat, n_hues, j,
                                        band_frac=bw_frac, gap=gap)
            cp_lo = cp - box_w / 2
            cp_hi = cp + box_w / 2
            q1 = quantile(vals, 0.25)
            q2 = quantile(vals, 0.50)
            q3 = quantile(vals, 0.75)
            iqr = q3 - q1
            lo_fence = q1 - whis * iqr
            hi_fence = q3 + whis * iqr
            inliers = [v for v in vals if lo_fence <= v <= hi_fence]
            outliers = [v for v in vals if v < lo_fence or v > hi_fence] if show_fliers else []
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
                n_samples = len(vals)
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
                                   fill_alpha=fill_alpha if do_fill else 1.0))
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
                                fill_alpha=fill_alpha if do_fill else 1.0))

            out.append(segment(median[0], median[1], median[2], median[3],
                               color=line, width=median_lw))
            cap_w = box_w * 0.4
            out.append(eb_along_val(cp, vp_q3, vp_hi, capsize=cap_w,
                                    color=line, width=lw))
            out.append(eb_along_val(cp, vp_q1, vp_lo, capsize=cap_w,
                                    color=line, width=lw))
            if show_means:
                mean_v = sum(vals) / len(vals)
                vp_m = val_scale(mean_v)
                cx_m, cy_m = (vp_m, cp) if horizontal else (cp, vp_m)
                out.append(marker(mean_marker_k, cx_m, cy_m,
                                  flier_size * 1.5, line, 1,
                                  edgecolor=fill if do_fill else None,
                                  edgewidth=lw * 0.8))
            for v in outliers:
                vp = val_scale(v)
                cx_dot, cy_dot = (vp, cp) if horizontal else (cp, vp)
                out.append(circle(cx_dot, cy_dot, flier_size,
                                  stroke=flier_line, stroke_width=lw * 0.9))
    return "".join(out)


def _boxplot_legend_entries(a):
    hues = a["hues"]
    if hues == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    fill_alpha = opts.get("fill_alpha", 0.55)
    lw = opts.get("linewidth", 1)
    do_fill = opts.get("fill", True)
    line = opts.get("linecolor", _FRAME["color"])
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, line)
        fill = col if do_fill else None
        def paint(_a, _ctx, _x0, _y_mid,
                  _fill=fill, _line=line, _lw=lw, _fa=fill_alpha):
            return rect(_x0, _y_mid - 5, 22, 10,
                        fill=_fill, stroke=_line, stroke_width=_lw,
                        fill_alpha=_fa if _fill else 1.0)
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


add_artist(ArtistSpec(
    name="boxplot",
    record=_boxplot_record,
    xdomain=_boxplot_xdomain,
    ydomain=_boxplot_ydomain,
    draw=_boxplot_draw,
    legend_entries=_boxplot_legend_entries,
))
