"""Custom artist: raincloud plot.

Allen-Wilkinson (2019) "raincloud": a half-violin (the cloud) plus a
mini-boxplot (the umbrella) plus a jittered strip (the rain), stacked
side-by-side per category. Makes the distribution shape, summary
statistics, and individual observations all readable at once — modern
biology paper standard.

Two input shapes, picked by which kwargs are present:
  - Wide-form (positional):  c.raincloud(cats, values_per_cat)
  - Long-form (seaborn):     c.raincloud(data=df, x="cat", y="value",
                                          hue="group", palette={...})

Long-form with `hue=` dodges sub-rainclouds side-by-side within each
cat and emits one legend entry per hue category. `palette=` accepts a
dict (category → color) or a sequence; missing entries fall through to
TAB10.

Layout within each (cat, hue) slot (divided into three sub-bands):
  - Vertical (default):   violin LEFT,  box MIDDLE, strip RIGHT.
                          Violin opens leftward (away from the box).
  - Horizontal (`'h'`):   violin TOP,   box MIDDLE, strip BOTTOM.
                          Violin opens upward (cloud above, rain below).

Styling kwargs (all optional):
  - `orientation='v'`        — `'h'` for horizontal rainclouds.
  - `width=0.8`              — total dodge-group width as a band fraction.
  - `gap=0.1`                — fraction of slot width left as a gap
                               between adjacent dodged sub-rainclouds.
  - `n_grid=80`              — KDE evaluation grid resolution.
  - `bw_adjust=1.0`          — Silverman bandwidth multiplier.
  - `trim=True`              — clip the KDE at min/max of the data.
  - `fill_alpha=0.45`        — half-violin body opacity.
  - `box_alpha=0.25`         — box-fill opacity.
  - `linecolor=<themed>`     — box outline, median, whiskers color.
  - `linewidth=1`            — box outline / whisker stroke width.
  - `median_linewidth=1.6`   — median tick stroke width.
  - `whis=1.5`               — IQR multiplier for the whisker fences.
  - `dot_size=2.5`           — strip dot radius in pixels.
  - `dot_alpha=0.55`         — strip dot opacity.
  - `jitter=0.5`             — strip jitter spread as a sub-band fraction
                               (points land in ±jitter/2 * third).
"""

SUMMARY = "Half-violin + box + jittered strip per category — Allen-Wilkinson modern bio paper standard; long-form `hue=` dodges sub-rainclouds."

import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import (to_list, quantile, hue_color,
                            dodge_positions, categorical_groups)
from plotlet.draw import path, rect, segment, circle
from plotlet._spec import _FRAME


def _silverman(xs):
    n = len(xs)
    if n < 2: return 1.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / n
    return 1.06 * (math.sqrt(var) or 1.0) * n ** (-1 / 5)


def _kde(samples, grid, bw):
    inv = 1.0 / (bw * math.sqrt(2 * math.pi) * len(samples))
    out = []
    for g in grid:
        s = 0.0
        for x in samples:
            z = (g - x) / bw
            s += math.exp(-0.5 * z * z)
        out.append(s * inv)
    return out


_M64 = 0xFFFFFFFFFFFFFFFF


def _jitter_hash(*ints):
    """Splitmix64-style avalanche; same helper as strip.py. Inlined to
    avoid coupling two recipes via shared internal helpers."""
    z = 0
    for a in ints:
        z = (z * 0x9E3779B97F4A7C15 + (a & _M64)) & _M64
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
    z ^= z >> 31
    return ((z & 0xFFFFFFFF) / 0xFFFFFFFF) - 0.5


def raincloud_record(args, kw):
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x = kw.pop("x", None)
        y = kw.pop("y", None)
        hue = kw.pop("hue", None)
        if data is None or x is None or y is None:
            raise TypeError(
                "raincloud long-form requires data=, x=, y= (hue= optional)."
            )
        cats, hues, groups = categorical_groups(data, x, y, hue)
    elif len(args) >= 2:
        cats = to_list(args[0])
        groups_1d = [list(to_list(g)) for g in args[1]]
        hues = [None]
        groups = [[g] for g in groups_1d]
    else:
        raise TypeError(
            "raincloud requires either positional (cats, values_per_cat) "
            "or keyword (data=, x=, y=)."
        )
    return {"type": "raincloud", "cats": cats, "hues": hues,
            "groups": groups, "opts": kw}


def _rc_horizontal(a): return a["opts"].get("orientation") == "h"
def _rc_values(a):
    return [v for row in a["groups"] for g in row for v in g]


def raincloud_xdomain(a):
    return _rc_values(a) if _rc_horizontal(a) else a["cats"]


def raincloud_ydomain(a):
    return a["cats"] if _rc_horizontal(a) else _rc_values(a)


def _emit(horizontal, cp, vp):
    """Pack a (cat-axis, value-axis) point into pixel (x, y)."""
    return (vp, cp) if horizontal else (cp, vp)


def raincloud_draw(a, ctx):
    cats, hues, groups = a["cats"], a["hues"], a["groups"]
    n_hues = len(hues)
    opts = a["opts"]
    palette    = opts.get("palette")
    bw_frac    = opts.get("width", 0.8)
    gap        = opts.get("gap", 0.1)
    n_grid     = opts.get("n_grid", 80)
    bw_adjust  = opts.get("bw_adjust", 1.0)
    trim       = opts.get("trim", True)
    fill_alpha = opts.get("fill_alpha", 0.45)
    box_alpha  = opts.get("box_alpha", 0.25)
    lw         = opts.get("linewidth", 1)
    median_lw  = opts.get("median_linewidth", 1.6)
    whis       = opts.get("whis", 1.5)
    r          = opts.get("dot_size", 2.5)
    dot_alpha  = opts.get("dot_alpha", 0.55)
    jitter     = opts.get("jitter", 0.5)
    line       = opts.get("linecolor", _FRAME["color"])
    horizontal = _rc_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    # In vertical mode the violin is LEFT and opens leftward (open_sign=-1).
    # In horizontal mode the violin is TOP and opens upward (open_sign=+1).
    open_sign = +1 if horizontal else -1
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_hues):
            vals = groups[i][j]
            if not vals:
                continue
            fill = hue_color(hues, palette, j, ctx.color)
            cp, slot_w = dodge_positions(cat_scale, cat, n_hues, j,
                                          band_frac=bw_frac, gap=gap)
            third = slot_w / 3
            violin_cp = cp + open_sign * third
            box_cp    = cp
            strip_cp  = cp - open_sign * third

            # --- half-violin ---
            bw = _silverman(vals) * bw_adjust
            lo_v, hi_v = min(vals), max(vals)
            pad = 0 if trim else ((hi_v - lo_v) * 0.1 or 1.0)
            grid = [lo_v - pad + (hi_v - lo_v + 2 * pad) * k / (n_grid - 1)
                    for k in range(n_grid)]
            d = _kde(vals, grid, bw)
            dmax = max(d) or 1.0
            curve = []
            for gx, dy in zip(grid, d):
                off = open_sign * (dy / dmax) * (third * 0.9)
                curve.append(_emit(horizontal, violin_cp + off, val_scale(gx)))
            # Close along the straight edge at violin_cp.
            curve.append(_emit(horizontal, violin_cp, val_scale(grid[-1])))
            curve.append(_emit(horizontal, violin_cp, val_scale(grid[0])))
            path_d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in curve) + " Z"
            out.append(path(path_d, fill=fill, stroke=fill, stroke_width=0.8,
                            fill_alpha=fill_alpha, stroke_alpha=1))

            # --- box (mini-boxplot, ggplot2 style) ---
            q1 = quantile(vals, 0.25)
            q2 = quantile(vals, 0.50)
            q3 = quantile(vals, 0.75)
            iqr = q3 - q1
            lo_fence = q1 - whis * iqr
            hi_fence = q3 + whis * iqr
            inliers = [v for v in vals if lo_fence <= v <= hi_fence]
            wlo = min(inliers) if inliers else q1
            whi = max(inliers) if inliers else q3
            box_w = third * 0.55
            vp_q1 = val_scale(q1); vp_q2 = val_scale(q2); vp_q3 = val_scale(q3)
            vp_wlo = val_scale(wlo); vp_whi = val_scale(whi)
            # Whiskers
            x1, y1 = _emit(horizontal, box_cp, vp_wlo)
            x2, y2 = _emit(horizontal, box_cp, vp_q1)
            out.append(segment(x1, y1, x2, y2, color=line, width=lw))
            x1, y1 = _emit(horizontal, box_cp, vp_q3)
            x2, y2 = _emit(horizontal, box_cp, vp_whi)
            out.append(segment(x1, y1, x2, y2, color=line, width=lw))
            # Box
            if horizontal:
                out.append(rect(min(vp_q1, vp_q3), box_cp - box_w / 2,
                                abs(vp_q3 - vp_q1), box_w,
                                fill=fill, stroke=line, stroke_width=lw,
                                fill_alpha=box_alpha))
            else:
                out.append(rect(box_cp - box_w / 2, min(vp_q1, vp_q3),
                                box_w, abs(vp_q3 - vp_q1),
                                fill=fill, stroke=line, stroke_width=lw,
                                fill_alpha=box_alpha))
            # Median
            mx1, my1 = _emit(horizontal, box_cp - box_w / 2, vp_q2)
            mx2, my2 = _emit(horizontal, box_cp + box_w / 2, vp_q2)
            out.append(segment(mx1, my1, mx2, my2, color=line, width=median_lw))

            # --- jittered strip ---
            for k, v in enumerate(vals):
                if v != v:  # NaN
                    continue
                off = _jitter_hash(i, j, k) * jitter * third
                vp = val_scale(v)
                cx, cy = _emit(horizontal, strip_cp + off, vp)
                out.append(circle(cx, cy, r, fill=fill, alpha=dot_alpha))
    return "".join(out)


def raincloud_legend_entries(a):
    hues = a["hues"]
    if hues == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    fill_alpha = opts.get("fill_alpha", 0.45)
    lw = opts.get("linewidth", 1)
    line = opts.get("linecolor", _FRAME["color"])
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, _FRAME["color"])
        def paint(_a, _ctx, _x0, _y_mid,
                  _fill=col, _line=line, _lw=lw, _fa=fill_alpha):
            return rect(_x0, _y_mid - 5, 22, 10,
                        fill=_fill, stroke=_line, stroke_width=_lw,
                        fill_alpha=_fa)
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


pt.add_artist(pt.ArtistSpec(
    name="raincloud",
    record=raincloud_record,
    xdomain=raincloud_xdomain,
    ydomain=raincloud_ydomain,
    draw=raincloud_draw,
    legend_entries=raincloud_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    rows = []
    for cond in ("control", "drug A", "drug B"):
        for treatment, shift in (("baseline", 0.0), ("followup", 0.9)):
            mu = {"control": 5.0, "drug A": 6.2, "drug B": 7.5}[cond] + shift
            sd = {"control": 1.0, "drug A": 1.1, "drug B": 1.4}[cond]
            for _ in range(60):
                rows.append({"cond": cond, "treatment": treatment,
                             "score": random.gauss(mu, sd)})
    # A small subpopulation in drug A so the cloud has a second mode.
    for _ in range(8):
        rows.append({"cond": "drug A", "treatment": "baseline",
                     "score": random.gauss(2.5, 0.4)})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart()
    c.xscale("category", order=["control", "drug A", "drug B"])
    c.raincloud(data=data, x="cond", y="score", hue="treatment",
                palette={"baseline": "#3F97C5", "followup": "#F99917"})
    c.title("Raincloud by condition and treatment")
    c.xlabel("group").ylabel("score")
    c.legend(True, position="right")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
