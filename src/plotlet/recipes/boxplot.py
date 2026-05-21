"""Custom artist: boxplot.

Tukey-style box-and-whisker: a box from Q1 to Q3, a median line, whiskers
out to the most extreme value within 1.5*IQR of each edge, and outliers
as individual dots. The matplotlib/seaborn staple for distribution-by-
category summaries.

Two input shapes, picked by which kwargs are present:
  - Wide-form (positional):  c.boxplot(cats, values_per_cat)
  - Long-form (seaborn):     c.boxplot(data=df, x="cat", y="value",
                                       hue="group", palette={...})

Long-form with `hue=` dodges sub-boxes side-by-side within each cat and
emits one legend entry per hue category. `palette=` accepts a dict
(category → color) or a sequence; missing entries fall through to TAB10.

Styling kwargs (all optional):
  - `width=0.6`             — total dodge-group width as a band fraction.
  - `gap=0.1`               — fraction of slot width left as a gap between
                              adjacent dodged boxes.
  - `fill_alpha=0.55`       — box-fill opacity (border stays opaque).
  - `linewidth=1`           — border / whisker / cap stroke width.
  - `median_linewidth=1.6`  — median line stroke width.
  - `whis=1.5`              — IQR multiplier for the whisker fences.
  - `flier_size=2.2`        — outlier-marker radius.
  - `showfliers=True`       — set False to hide outliers.
"""

SUMMARY = 'Tukey-style box + whiskers + outlier dots, one box per category; long-form `hue=` dodges sub-boxes.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import (to_list, quantile, hue_color,
                            dodge_positions, categorical_groups)
from plotlet.draw import segment, rect, circle, errorbar_v, errorbar_h
from plotlet._spec import _FRAME


def boxplot_record(args, kw):
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


def boxplot_xdomain(a):
    return _boxplot_values(a) if _boxplot_horizontal(a) else a["cats"]


def boxplot_ydomain(a):
    return a["cats"] if _boxplot_horizontal(a) else _boxplot_values(a)


def boxplot_draw(a, ctx):
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
    horizontal = _boxplot_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    eb_along_val = errorbar_h if horizontal else errorbar_v
    line = _FRAME["color"]
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_hues):
            vals = groups[i][j]
            if not vals:
                continue
            fill = hue_color(hues, palette, j, ctx.color)
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
                            fill_alpha=fill_alpha))
            out.append(segment(median[0], median[1], median[2], median[3],
                               color=line, width=median_lw))
            cap_w = box_w * 0.4
            out.append(eb_along_val(cp, vp_q3, vp_hi, capsize=cap_w,
                                    color=line, width=lw))
            out.append(eb_along_val(cp, vp_q1, vp_lo, capsize=cap_w,
                                    color=line, width=lw))
            for v in outliers:
                vp = val_scale(v)
                cx_dot, cy_dot = (vp, cp) if horizontal else (cp, vp)
                out.append(circle(cx_dot, cy_dot, flier_size,
                                  stroke=line, stroke_width=lw * 0.9))
    return "".join(out)


def boxplot_legend_entries(a):
    hues = a["hues"]
    if hues == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    fill_alpha = opts.get("fill_alpha", 0.55)
    lw = opts.get("linewidth", 1)
    line = _FRAME["color"]
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, line)
        def paint(_a, _ctx, _x0, _y_mid,
                  _fill=col, _line=line, _lw=lw, _fa=fill_alpha):
            return rect(_x0, _y_mid - 5, 22, 10,
                        fill=_fill, stroke=_line, stroke_width=_lw,
                        fill_alpha=_fa)
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


pt.add_artist(pt.ArtistSpec(
    name="boxplot",
    record=boxplot_record,
    xdomain=boxplot_xdomain,
    ydomain=boxplot_ydomain,
    draw=boxplot_draw,
    legend_entries=boxplot_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    # Long-form: a row per measurement, with group + treatment cols.
    rows = []
    for group in ("control", "low", "mid", "high"):
        for treatment, shift in (("A", 0.0), ("B", 1.4)):
            mu = {"control": 5, "low": 6, "mid": 7.5, "high": 9}[group] + shift
            sd = {"control": 1, "low": 1.2, "mid": 1.5, "high": 1.8}[group]
            for _ in range(40):
                rows.append({"group": group, "treatment": treatment,
                             "score": random.gauss(mu, sd)})
    # A couple of outliers so the IQR fence has work to do.
    rows.append({"group": "low",  "treatment": "A", "score": 12})
    rows.append({"group": "low",  "treatment": "A", "score": -2})
    rows.append({"group": "high", "treatment": "B", "score": 16})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart()
    c.xscale("category", order=["control", "low", "mid", "high"])
    c.boxplot(data=data, x="group", y="score", hue="treatment",
              palette={"A": "#3F97C5", "B": "#F99917"})
    c.title("Dose response by treatment").xlabel("group").ylabel("score")
    c.legend(True, position="right")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
