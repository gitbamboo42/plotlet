"""Custom artist: letter-value plot (a.k.a. boxenplot).

Modern alternative to the boxplot for big samples (n ≥ ~100). Where
boxplot has one box covering Q1–Q3, boxenplot draws a *nested* stack of
boxes at successively further-out quantile pairs ([Q1, Q3], [Q1/2, Q3·2],
[Q1/4, Q3·4] — i.e. octiles, hexadeciles, …) giving a richer tail
picture. Each outer box is shaded lighter than the inner one so you can
read the levels at a glance.

Input shape (long-form table):

    c.boxen(data=df, x="cat", y="value", fill="group", palette={...})

`fill="col"` dodges sub-boxen side-by-side within each cat
and emits one legend entry per group level. `palette=` accepts a dict
(level → color) or a sequence; missing entries fall through to TAB10.

Aesthetics:
  - `fill=True/<col>/<literal>/False` — body fill (True = palette/cycle
                              default, col = column-driven grouping,
                              literal color string, or False for
                              outline-only).
  - `color=<literal>`        — border / median stroke (defaults to frame).
  - `palette=`               — maps levels → fills when `fill=` is a column.

Other styling kwargs (all optional):
  - `orientation='v'`        — `'h'` for horizontal boxen (cats on y axis).
  - `width=0.7`              — total dodge-group width as a band fraction.
  - `gap=0.1`                — fraction of slot width left as a gap between
                               adjacent dodged sub-boxen.
  - `max_levels=5`           — maximum nesting depth (also capped by
                               sample size: stop when the next level
                               would put <1 sample in the tail).
  - `linewidth=0.6`          — border stroke width.
  - `median_linewidth=1.6`   — median tick stroke width.
"""

SUMMARY = 'Letter-value plot (boxenplot): nested quantile boxes for big-sample distribution detail.'

from pathlib import Path

import plotlet as pt
from plotlet.draw import rect, segment
from plotlet.draw import TAB10, resolve_color
from plotlet.utils import (to_list, quantile, resolve_aes, palette_color,
                            dodge_positions, categorical_groups)
from plotlet._spec import _FRAME


def _mix_to_white(hex_col, t):
    """Mix a `#rrggbb` color toward white by fraction t in [0, 1]. Returns
    the input unchanged if it's not in `#rrggbb` form, so outer levels
    just won't fade for user palettes that use named colors or shortcuts."""
    if not (isinstance(hex_col, str) and len(hex_col) == 7 and hex_col[0] == "#"):
        return hex_col
    try:
        r = int(hex_col[1:3], 16); g = int(hex_col[3:5], 16); b = int(hex_col[5:7], 16)
    except ValueError:
        return hex_col
    r = int(r + (255 - r) * t); g = int(g + (255 - g) * t); b = int(b + (255 - b) * t)
    return f"rgb({r},{g},{b})"


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


def boxen_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "boxen requires long-form input: "
            "c.boxen(data=df, x='cat_col', y='value_col')."
        )
    data = kw.pop("data", None)
    x = kw.pop("x", None)
    y = kw.pop("y", None)
    if data is None or x is None or y is None:
        raise TypeError(
            "boxen requires data=, x=, y= (fill= optional)."
        )
    do_fill, fill_literal, group_col = _resolve_fill_kwarg(data, kw)
    cats, groups, vals = categorical_groups(data, x, y, group_col)
    kw["_do_fill"] = do_fill
    if fill_literal is not None:
        kw["_fill_literal"] = fill_literal
    return {"type": "boxen", "cats": cats, "groups": groups,
            "vals": vals, "opts": kw}


def _boxen_horizontal(a): return a["opts"].get("orientation") == "h"
def _boxen_values(a):
    return [v for row in a["vals"] for g in row for v in g]


def boxen_xdomain(a):
    return _boxen_values(a) if _boxen_horizontal(a) else a["cats"]


def boxen_ydomain(a):
    return a["cats"] if _boxen_horizontal(a) else _boxen_values(a)


def _group_fill(groups, palette, j, fallback):
    if groups == [None]:
        return fallback
    return palette_color(palette, groups[j], j) or TAB10[j % 10]


def boxen_draw(a, ctx):
    cats, groups, vals = a["cats"], a["groups"], a["vals"]
    n_groups = len(groups)
    opts = a["opts"]
    palette    = opts.get("palette")
    bw_frac    = opts.get("width", 0.7)
    gap        = opts.get("gap", 0.1)
    max_levels = opts.get("max_levels", 5)
    lw         = opts.get("linewidth", 0.6)
    median_lw  = opts.get("median_linewidth", 1.6)
    do_fill    = opts.get("_do_fill", True)
    line       = resolve_color(opts.get("color")) or _FRAME["color"]
    fill_literal = resolve_color(opts.get("_fill_literal"))
    fill_fallback = fill_literal if fill_literal is not None else ctx.color
    horizontal = _boxen_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_groups):
            vs = vals[i][j]
            if len(vs) < 4:
                continue
            base_col = _group_fill(groups, palette, j, fill_fallback) if do_fill else None
            cp, slot_w = dodge_positions(cat_scale, cat, n_groups, j,
                                          band_frac=bw_frac, gap=gap)
            median = quantile(vs, 0.5)
            n = len(vs)
            levels = []
            for k in range(max_levels):
                q_lo = 0.25 / (2 ** k)
                if q_lo * n < 1:
                    break
                levels.append((q_lo, 1 - q_lo, k))
            # Outermost first (widest, palest); innermost last so the
            # median tick lands on top of the inner box.
            for q_lo, q_hi, k in reversed(levels):
                v_lo = quantile(vs, q_lo)
                v_hi = quantile(vs, q_hi)
                w_px = slot_w * max(1.0 - k * 0.18, 0.2)
                shade = _mix_to_white(base_col, min(0.75, 0.18 * k)) if base_col else None
                vp_lo = val_scale(v_lo); vp_hi = val_scale(v_hi)
                if horizontal:
                    out.append(rect(min(vp_lo, vp_hi), cp - w_px / 2,
                                    abs(vp_hi - vp_lo), w_px,
                                    fill=shade, stroke=line, stroke_width=lw))
                else:
                    out.append(rect(cp - w_px / 2, min(vp_lo, vp_hi),
                                    w_px, abs(vp_hi - vp_lo),
                                    fill=shade, stroke=line, stroke_width=lw))
            vp_med = val_scale(median)
            if horizontal:
                out.append(segment(vp_med, cp - slot_w / 2,
                                   vp_med, cp + slot_w / 2,
                                   color=line, width=median_lw))
            else:
                out.append(segment(cp - slot_w / 2, vp_med,
                                   cp + slot_w / 2, vp_med,
                                   color=line, width=median_lw))
    return "".join(out)


def boxen_legend_entries(a):
    groups = a["groups"]
    if groups == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    lw = opts.get("linewidth", 0.6)
    do_fill = opts.get("_do_fill", True)
    line = resolve_color(opts.get("color")) or _FRAME["color"]
    entries = []
    for j, g in enumerate(groups):
        col = _group_fill(groups, palette, j, line)
        fill = col if do_fill else None
        def paint(_a, _ctx, _x0, _y_mid,
                  _fill=fill, _line=line, _lw=lw):
            return rect(_x0, _y_mid - 5, 22, 10,
                        fill=_fill, stroke=_line, stroke_width=_lw)
        entries.append({"label": str(g), "color": col, "paint": paint})
    return entries


pt.add_artist(pt.ArtistSpec(
    name="boxen",
    record=boxen_record,
    xdomain=boxen_xdomain,
    ydomain=boxen_ydomain,
    draw=boxen_draw,
    legend_entries=boxen_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    rows = []
    for group in ("A", "B", "C", "D"):
        for treatment, shift in (("control", 0.0), ("dose", 1.4)):
            mu = {"A": 5.0, "B": 6.0, "C": 5.5, "D": 7.5}[group] + shift
            sd = {"A": 1.0, "B": 1.2, "C": 0.8, "D": 1.5}[group]
            for _ in range(400):
                rows.append({"group": group, "treatment": treatment,
                             "value": random.gauss(mu, sd)})
    # Long tails so outer levels have work to do.
    for _ in range(20):
        rows.append({"group": "B", "treatment": "dose", "value": random.gauss(13, 0.5)})
    for _ in range(15):
        rows.append({"group": "D", "treatment": "control", "value": random.gauss(1, 0.4)})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart()
    c.xscale("category", order=["A", "B", "C", "D"])
    c.boxen(data=data, x="group", y="value", fill="treatment",
            palette={"control": "#3F97C5", "dose": "#F99917"})
    c.title("Letter-value plot by group and treatment")
    c.xlabel("group").ylabel("value")
    c.legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
