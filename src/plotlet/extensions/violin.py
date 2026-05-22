"""Custom artist: violin plot.

Mirrored KDE outline per category, with a mini-boxplot (Q1-Q3 box +
median line + 1.5*IQR whiskers) drawn inside — the ggplot2-style violin.
The KDE shape conveys the distribution, the inner box conveys the
Tukey summary.

Two input shapes, picked by which kwargs are present:
  - Wide-form (positional):  c.violin(cats, values_per_cat)
  - Long-form (seaborn):     c.violin(data=df, x="cat", y="value",
                                       hue="group", palette={...})

Long-form with `hue=` dodges sub-violins side-by-side within each cat
and emits one legend entry per hue category. `palette=` accepts a dict
(category → color) or a sequence; missing entries fall through to TAB10.

Styling kwargs (all optional):
  - `orientation='v'`       — `'h'` for horizontal violins (cats on y axis).
  - `width=0.8`             — total dodge-group width as a band fraction.
  - `gap=0.1`               — fraction of slot width left as a gap between
                              adjacent dodged violins.
  - `inner='box'`           — `'box'` mini-boxplot (Q1-Q3 outlined + median
                              line + 1.5*IQR whiskers), `'quartile'` three
                              dashed lines at Q1/Q2/Q3, `None` KDE only.
  - `trim=True`             — clip the KDE at min/max of the data. `False`
                              extends 10 % past each end (matplotlib default).
  - `fill=True`             — set False for outline-only violins.
  - `fill_alpha=0.4`        — body-fill opacity (outline stays opaque).
  - `linecolor=<themed>`    — override outline / inner-box color.
  - `linewidth=1`           — outline / inner-box stroke width.
  - `whis=1.5`              — IQR multiplier for the whisker fences (when
                              `inner='box'`).
  - `inner_box_fill=<bg>`   — mini-boxplot fill (when `inner='box'`).
                              Defaults to the figure background so the box
                              reads as negative space against the violin
                              body on any theme.
  - `n_grid=80`             — KDE evaluation grid resolution.
  - `bw_adjust=1.0`         — Silverman bandwidth multiplier (>1 smoother).
"""

SUMMARY = 'Mirrored KDE outline + mini-boxplot inside, per category; long-form `hue=` dodges sub-violins.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import (to_list, quantile, hue_color,
                            dodge_positions, categorical_groups)
from plotlet.draw import path, rect, segment
from plotlet._spec import _FRAME, _FIGSPEC


def _silverman_bw(xs):
    n = len(xs)
    if n < 2:
        return 1.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / n
    sd = math.sqrt(var) or 1.0
    return 1.06 * sd * n ** (-1 / 5)


def _kde(samples, grid, bw):
    inv = 1.0 / (bw * math.sqrt(2 * math.pi))
    out = []
    for g in grid:
        s = 0.0
        for x in samples:
            z = (g - x) / bw
            s += math.exp(-0.5 * z * z)
        out.append(s * inv / len(samples))
    return out


def violin_record(args, kw):
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x = kw.pop("x", None)
        y = kw.pop("y", None)
        hue = kw.pop("hue", None)
        if data is None or x is None or y is None:
            raise TypeError(
                "violin long-form requires data=, x=, y= (hue= optional)."
            )
        cats, hues, groups = categorical_groups(data, x, y, hue)
    elif len(args) >= 2:
        cats = to_list(args[0])
        groups_1d = [list(to_list(g)) for g in args[1]]
        hues = [None]
        groups = [[g] for g in groups_1d]
    else:
        raise TypeError(
            "violin requires either positional (cats, values_per_cat) "
            "or keyword (data=, x=, y=)."
        )
    return {"type": "violin", "cats": cats, "hues": hues,
            "groups": groups, "opts": kw}


def _violin_horizontal(a): return a["opts"].get("orientation") == "h"
def _violin_values(a):
    return [v for row in a["groups"] for g in row for v in g]


def violin_xdomain(a):
    return _violin_values(a) if _violin_horizontal(a) else a["cats"]


def violin_ydomain(a):
    return a["cats"] if _violin_horizontal(a) else _violin_values(a)


def violin_draw(a, ctx):
    cats, hues, groups = a["cats"], a["hues"], a["groups"]
    n_hues = len(hues)
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
    do_fill    = opts.get("fill", True)
    line       = opts.get("linecolor", _FRAME["color"])
    horizontal = _violin_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_hues):
            vals = groups[i][j]
            if not vals:
                continue
            fill = hue_color(hues, palette, j, ctx.color) if do_fill else None
            cp, slot_w = dodge_positions(cat_scale, cat, n_hues, j,
                                          band_frac=w_frac, gap=gap)
            half_w_px = slot_w / 2

            bw = _silverman_bw(vals) * bw_adjust
            lo, hi = min(vals), max(vals)
            pad = 0 if trim else ((hi - lo) * 0.1 or 1.0)
            grid = [lo - pad + (hi - lo + 2 * pad) * k / (n_grid - 1)
                    for k in range(n_grid)]
            d = _kde(vals, grid, bw)
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

            q1 = quantile(vals, 0.25)
            q2 = quantile(vals, 0.50)
            q3 = quantile(vals, 0.75)
            vp_q1 = val_scale(q1)
            vp_q2 = val_scale(q2)
            vp_q3 = val_scale(q3)
            if inner == "box":
                box_half = half_w_px * 0.18
                box_fill = opts.get("inner_box_fill", _FIGSPEC["background"])
                iqr = q3 - q1
                lo_fence = q1 - whis * iqr
                hi_fence = q3 + whis * iqr
                inliers = [v for v in vals if lo_fence <= v <= hi_fence]
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


def violin_legend_entries(a):
    hues = a["hues"]
    if hues == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    fill_alpha = opts.get("fill_alpha", 0.4)
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


pt.add_artist(pt.ArtistSpec(
    name="violin",
    record=violin_record,
    xdomain=violin_xdomain,
    ydomain=violin_ydomain,
    draw=violin_draw,
    legend_entries=violin_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    rows = []
    for genotype in ("wild-type", "+drug", "knockout", "rescue"):
        for treatment, shift in (("A", 0.0), ("B", 1.2)):
            mu = {"wild-type": 5, "+drug": 4, "knockout": 7, "rescue": 5.5}[genotype] + shift
            sd = {"wild-type": 1, "+drug": 0.8, "knockout": 1.4, "rescue": 1.0}[genotype]
            for _ in range(120):
                rows.append({"genotype": genotype, "treatment": treatment,
                             "expression": random.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart()
    c.xscale("category", order=["wild-type", "+drug", "knockout", "rescue"])
    c.violin(data=data, x="genotype", y="expression", hue="treatment",
             palette={"A": "#3F97C5", "B": "#F99917"}, inner="box")
    c.title("Expression level by genotype and treatment")
    c.xlabel("genotype").ylabel("log₂ FPKM")
    c.legend(True, position="right")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
