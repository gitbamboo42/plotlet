"""Custom artist: boxplot.

Tukey-style box-and-whisker: a box from Q1 to Q3, a median line, whiskers
out to the most extreme value within 1.5*IQR of each edge, and outliers
as individual dots. The matplotlib/seaborn staple for distribution-by-
category summaries.

API: c.boxplot(cats, values_per_cat). x is categorical, y is numeric.
Each entry of `values_per_cat` is the sample for that category.
"""

SUMMARY = 'Tukey-style box + whiskers + outlier dots, one box per category.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import segment, rect, circle, errorbar_v


def _quantile(xs, q):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float("nan")
    if n == 1:
        return xs[0]
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def boxplot_record(args, kw):
    cats = to_list(args[0])
    groups = [list(to_list(g)) for g in args[1]]
    return {"type": "boxplot", "cats": cats, "groups": groups, "opts": kw}


def boxplot_xdomain(a): return a["cats"]
def boxplot_ydomain(a): return [v for g in a["groups"] for v in g]


def boxplot_draw(a, ctx):
    col = ctx.color
    bw_frac = a["opts"].get("width", 0.6)
    # On a category scale the band-width comes from the scale itself.
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    box_w = band * bw_frac
    out = []
    for cat, vals in zip(a["cats"], a["groups"]):
        if not vals:
            continue
        q1 = _quantile(vals, 0.25)
        q2 = _quantile(vals, 0.50)
        q3 = _quantile(vals, 0.75)
        iqr = q3 - q1
        lo_fence = q1 - 1.5 * iqr
        hi_fence = q3 + 1.5 * iqr
        inliers = [v for v in vals if lo_fence <= v <= hi_fence]
        outliers = [v for v in vals if v < lo_fence or v > hi_fence]
        whisker_lo = min(inliers) if inliers else q1
        whisker_hi = max(inliers) if inliers else q3
        cx = ctx.x_scale(cat)
        x0 = cx - box_w / 2
        x1 = cx + box_w / 2
        y_q1 = ctx.y_scale(q1)
        y_q2 = ctx.y_scale(q2)
        y_q3 = ctx.y_scale(q3)
        y_lo = ctx.y_scale(whisker_lo)
        y_hi = ctx.y_scale(whisker_hi)
        # Box (Q1-Q3), translucent fill + solid stroke.
        out.append(rect(x0, min(y_q1, y_q3), box_w, abs(y_q3 - y_q1),
                        fill=col, stroke=col, stroke_width=1, alpha=0.35))
        # Median line.
        out.append(segment(x0, y_q2, x1, y_q2, color=col, width=1.6))
        # Whiskers: an errorbar on each side of the box.
        cap_w = box_w * 0.4
        out.append(errorbar_v(cx, y_q3, y_hi, capsize=cap_w, color=col))
        out.append(errorbar_v(cx, y_q1, y_lo, capsize=cap_w, color=col))
        # Outlier dots — outline-only so they read as "extreme" not "data".
        for v in outliers:
            out.append(circle(cx, ctx.y_scale(v), 2.2,
                              stroke=col, stroke_width=0.9))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="boxplot",
    record=boxplot_record,
    xdomain=boxplot_xdomain,
    ydomain=boxplot_ydomain,
    draw=boxplot_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    cats = ["control", "low", "mid", "high"]
    groups = [
        [random.gauss(5, 1) for _ in range(40)],
        [random.gauss(6, 1.2) for _ in range(40)] + [12, -2],
        [random.gauss(7.5, 1.5) for _ in range(40)],
        [random.gauss(9, 1.8) for _ in range(40)] + [16],
    ]
    c = pt.chart()
    c.xscale("category", order=cats)
    c.boxplot(cats, groups)
    c.title("Dose response").xlabel("group").ylabel("score")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
