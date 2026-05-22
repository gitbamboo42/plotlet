"""Custom artist: strip / jitter plot.

Categorical scatter with deterministic horizontal jitter — seaborn's
`stripplot`. Each sample is a small dot near its category center,
offset by a hash-derived pseudo-random amount so overlapping points
stay distinguishable. The jitter is deterministic (no per-render RNG)
so the SVG is byte-identical on every render.

Two input shapes, picked by which kwargs are present:
  - Wide-form (positional):  c.strip(cats, values_per_cat)
  - Long-form (seaborn):     c.strip(data=df, x="cat", y="value",
                                      hue="group", palette={...})

Long-form with `hue=` dodges sub-strips side-by-side within each cat
and emits one legend entry per hue category. `palette=` accepts a dict
(category → color) or a sequence; missing entries fall through to TAB10.

Styling kwargs (all optional):
  - `orientation='v'`       — `'h'` for horizontal strips (cats on y axis).
  - `width=0.8`             — total dodge-group width as a band fraction.
  - `gap=0.1`               — fraction of slot width left as a gap between
                              adjacent dodged sub-strips.
  - `jitter=0.2`            — spread of points within each slot, as a
                              slot-width fraction (points land in
                              ±jitter/2 * slot_w from the slot center).
  - `size=3`                — point radius in pixels.
  - `alpha=0.7`             — point opacity.
  - `linewidth=0`           — outline stroke width (seaborn default 0 = no
                              outline).
  - `edgecolor=<line>`      — outline color when `linewidth > 0`. Defaults
                              to the themed line color.
"""

SUMMARY = 'Categorical scatter with deterministic jitter (no per-render RNG); long-form `hue=` dodges sub-strips.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import (to_list, hue_color, dodge_positions,
                            categorical_groups)
from plotlet.draw import circle
from plotlet._spec import _FRAME


_M64 = 0xFFFFFFFFFFFFFFFF


def _jitter_hash(*ints):
    """Deterministic pseudo-random in [-0.5, 0.5] from one or more ints.
    Splitmix64-style avalanche: mixes well even for small inputs (the
    previous bit-shift-only hash collapsed near zero for low i/j).
    No RNG state — byte-identical across runs."""
    z = 0
    for a in ints:
        z = (z * 0x9E3779B97F4A7C15 + (a & _M64)) & _M64
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
    z ^= z >> 31
    return ((z & 0xFFFFFFFF) / 0xFFFFFFFF) - 0.5


def strip_record(args, kw):
    if "data" in kw or "x" in kw or "y" in kw:
        data = kw.pop("data", None)
        x = kw.pop("x", None)
        y = kw.pop("y", None)
        hue = kw.pop("hue", None)
        if data is None or x is None or y is None:
            raise TypeError(
                "strip long-form requires data=, x=, y= (hue= optional)."
            )
        cats, hues, groups = categorical_groups(data, x, y, hue)
    elif len(args) >= 2:
        cats = to_list(args[0])
        groups_1d = [list(to_list(g)) for g in args[1]]
        hues = [None]
        groups = [[g] for g in groups_1d]
    else:
        raise TypeError(
            "strip requires either positional (cats, values_per_cat) "
            "or keyword (data=, x=, y=)."
        )
    return {"type": "strip", "cats": cats, "hues": hues,
            "groups": groups, "opts": kw}


def _strip_horizontal(a): return a["opts"].get("orientation") == "h"
def _strip_values(a):
    return [v for row in a["groups"] for g in row for v in g]


def strip_xdomain(a):
    return _strip_values(a) if _strip_horizontal(a) else a["cats"]


def strip_ydomain(a):
    return a["cats"] if _strip_horizontal(a) else _strip_values(a)


def strip_draw(a, ctx):
    cats, hues, groups = a["cats"], a["hues"], a["groups"]
    n_hues = len(hues)
    opts = a["opts"]
    palette   = opts.get("palette")
    w_frac    = opts.get("width", 0.8)
    gap       = opts.get("gap", 0.1)
    jitter    = opts.get("jitter", 0.2)
    r         = opts.get("size", 3)
    alpha     = opts.get("alpha", 0.7)
    lw        = opts.get("linewidth", 0)
    edgecolor = opts.get("edgecolor", _FRAME["color"])
    horizontal = _strip_horizontal(a)
    cat_scale, val_scale = (ctx.y_scale, ctx.x_scale) if horizontal else (ctx.x_scale, ctx.y_scale)
    out = []
    for i, cat in enumerate(cats):
        for j in range(n_hues):
            vals = groups[i][j]
            if not vals:
                continue
            col = hue_color(hues, palette, j, ctx.color)
            cp, slot_w = dodge_positions(cat_scale, cat, n_hues, j,
                                          band_frac=w_frac, gap=gap)
            for k, v in enumerate(vals):
                if v != v:  # NaN
                    continue
                off = _jitter_hash(i, j, k) * slot_w * jitter
                vp = val_scale(v)
                cx, cy = (vp, cp + off) if horizontal else (cp + off, vp)
                out.append(circle(cx, cy, r, fill=col, alpha=alpha,
                                  stroke=edgecolor if lw > 0 else None,
                                  stroke_width=lw))
    return "".join(out)


def strip_legend_entries(a):
    hues = a["hues"]
    if hues == [None]:
        return []
    opts = a["opts"]
    palette = opts.get("palette")
    r = opts.get("size", 3)
    alpha = opts.get("alpha", 0.7)
    lw = opts.get("linewidth", 0)
    edgecolor = opts.get("edgecolor", _FRAME["color"])
    entries = []
    for j, h in enumerate(hues):
        col = hue_color(hues, palette, j, _FRAME["color"])
        def paint(_a, _ctx, _x0, _y_mid,
                  _col=col, _r=r, _al=alpha, _lw=lw, _ec=edgecolor):
            return circle(_x0 + 11, _y_mid, _r, fill=_col, alpha=_al,
                          stroke=_ec if _lw > 0 else None, stroke_width=_lw)
        entries.append({"label": str(h), "color": col, "paint": paint})
    return entries


pt.add_artist(pt.ArtistSpec(
    name="strip",
    record=strip_record,
    xdomain=strip_xdomain,
    ydomain=strip_ydomain,
    draw=strip_draw,
    legend_entries=strip_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(1)
    rows = []
    for cond in ("A", "B", "C", "D"):
        for treatment, shift in (("control", 0.0), ("dose", 0.8)):
            mu = {"A": 3.0, "B": 4.5, "C": 5.2, "D": 6.1}[cond] + shift
            sd = {"A": 0.8, "B": 1.0, "C": 0.6, "D": 1.2}[cond]
            for _ in range(30):
                rows.append({"condition": cond, "treatment": treatment,
                             "value": random.gauss(mu, sd)})
    data = {k: [r[k] for r in rows] for k in rows[0]}

    c = pt.chart()
    c.xscale("category", order=["A", "B", "C", "D"])
    c.strip(data=data, x="condition", y="value", hue="treatment",
            palette={"control": "#3F97C5", "dose": "#F99917"})
    c.title("Per-sample strip by condition and treatment")
    c.xlabel("condition").ylabel("value")
    c.legend(True, position="right")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
