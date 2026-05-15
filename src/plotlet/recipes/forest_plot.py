"""Custom artist: forest plot (meta-analysis).

One row per study (or subgroup): a point estimate, a horizontal CI bar,
and a square sized by study weight. A vertical "no effect" reference
line (default 1 for odds ratio, 0 for mean difference) anchors
interpretation. The bottom row is the pooled estimate as a diamond
spanning its CI.

API:
    c.forest(labels, estimates, lowers, uppers,
             weights=None, ref=1, pooled=None, log_x=False)

`pooled` is a `(estimate, lower, upper, label)` tuple, drawn as a
diamond on its own row. `log_x=True` does the on-screen log mapping
expected for OR/HR-style plots.
"""

SUMMARY = 'Meta-analysis: per-study estimate + CI bar + square-by-weight, pooled diamond at the bottom.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path, segment, rect, errorbar_h, polygon


def forest_record(args, kw):
    labels = to_list(args[0])
    est = to_list(args[1])
    lo = to_list(args[2])
    hi = to_list(args[3])
    return {"type": "forest", "labels": labels, "est": est, "lo": lo,
            "hi": hi, "opts": kw}


def forest_xdomain(a):
    out = list(a["lo"]) + list(a["hi"])
    if a["opts"].get("ref") is not None:
        out.append(a["opts"]["ref"])
    pooled = a["opts"].get("pooled")
    if pooled:
        out += [pooled[1], pooled[2]]
    return out


def forest_ydomain(a):
    n = len(a["labels"])
    if a["opts"].get("pooled"):
        return [-1, n]
    return [0, n]


def forest_draw(a, ctx):
    weights = a["opts"].get("weights")
    if weights is None:
        weights = [1.0] * len(a["est"])
    ref = a["opts"].get("ref", 1)
    pooled = a["opts"].get("pooled")
    color = a["opts"].get("color", "#222222")
    n = len(a["labels"])
    # Reference vertical line.
    x_ref = ctx.x_scale(ref)
    y_top = ctx.y_scale(n)
    y_bot = ctx.y_scale(-1 if pooled else 0)
    out = [segment(x_ref, y_top, x_ref, y_bot,
                   color="#888", width=0.8, dash="3,3")]
    # Study rows: first study at the top, so row i appears at y = n - 1 - i.
    max_w = max(weights) or 1
    for i, (lab, e, l, h, w) in enumerate(zip(a["labels"], a["est"],
                                              a["lo"], a["hi"], weights)):
        y_data = n - 1 - i
        py = ctx.y_scale(y_data)
        px_lo = ctx.x_scale(l); px_hi = ctx.x_scale(h); px_e = ctx.x_scale(e)
        # CI bar with end caps.
        out.append(errorbar_h(py, px_lo, px_hi,
                              capsize=6, color=color, width=1.2))
        # Square scaled by weight.
        s = 3 + 7 * math.sqrt(w / max_w)
        out.append(rect(px_e - s, py - s, 2 * s, 2 * s, fill=color))
        # Study label on the left (just inside data area).
        out.append(text_path(lab, ctx.x_scale(min(a["lo"])) - 6, py + 3,
                              10, anchor="end"))
    # Pooled diamond at y = -1.
    if pooled:
        pe, pl, ph, plab = pooled
        py = ctx.y_scale(-1)
        px_lo = ctx.x_scale(pl); px_hi = ctx.x_scale(ph); px_e = ctx.x_scale(pe)
        s = 8
        out.append(polygon([(px_lo, py), (px_e, py - s),
                            (px_hi, py), (px_e, py + s)], fill=color))
        out.append(text_path(plab, ctx.x_scale(min(a["lo"])) - 6, py + 3,
                              10, anchor="end", color="#000"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="forest",
    record=forest_record,
    xdomain=forest_xdomain,
    ydomain=forest_ydomain,
    draw=forest_draw,
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    labels  = ["Smith 2018",   "Jones 2019",  "Khan 2020",   "Park 2021",
               "Garcia 2022",  "Liu 2023"]
    est     = [0.84,  1.10,  0.65,  0.91,  0.75,  0.82]
    lo      = [0.60,  0.80,  0.45,  0.65,  0.55,  0.65]
    hi      = [1.17,  1.51,  0.94,  1.27,  1.02,  1.04]
    weights = [0.10,  0.18,  0.14,  0.16,  0.22,  0.20]
    pooled  = (0.82, 0.72, 0.93, "Pooled (random)")
    c = pt.chart(data_width=420, data_height=240)
    c.forest(labels, est, lo, hi, weights=weights, ref=1, pooled=pooled)
    c.title("Effect of intervention").xlabel("Odds ratio (95 % CI)")
    c.yticks([])
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
