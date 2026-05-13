"""Custom artist: letter-value plot (a.k.a. boxenplot).

Heskes / Hofmann / Wickham's modern alternative to the boxplot for big
samples (n ≥ ~100). Where boxplot has one box covering Q1–Q3, boxenplot
draws a *nested* stack of boxes at successively further-out quantile
pairs ([Q1, Q3], [Q1/2, Q3·2], [Q1/4, Q3·4 — i.e. octiles, hexadeciles, …)
giving a richer tail picture. Each outer box is shaded lighter than the
inner one so you can read the levels at a glance.

API:
    c.boxen(cats, values_per_cat, width=0.7, max_levels=5)
"""

SUMMARY = 'Letter-value plot (boxenplot): nested quantile boxes for big-sample distribution detail.'

from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist


def _quantile(xs, q):
    xs = sorted(xs)
    n = len(xs)
    if n == 0: return float("nan")
    if n == 1: return xs[0]
    pos = (n - 1) * q
    lo = int(pos); hi = min(lo + 1, n - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def boxen_record(args, kw):
    cats = _to_pylist(args[0])
    groups = [list(_to_pylist(g)) for g in args[1]]
    return {"type": "boxen", "cats": cats, "groups": groups, "opts": kw}


def boxen_xdomain(a): return a["cats"]
def boxen_ydomain(a): return [v for g in a["groups"] for v in g]


def _mix_to_white(hex_col, t):
    """Mix a hex color toward white by fraction t in [0, 1]."""
    r = int(hex_col[1:3], 16); g = int(hex_col[3:5], 16); b = int(hex_col[5:7], 16)
    r = int(r + (255 - r) * t); g = int(g + (255 - g) * t); b = int(b + (255 - b) * t)
    return f"rgb({r},{g},{b})"


def boxen_draw(a, ctx):
    col = ctx.color
    bw_frac = a["opts"].get("width", 0.7)
    max_levels = a["opts"].get("max_levels", 5)
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    out = []
    for cat, vals in zip(a["cats"], a["groups"]):
        if len(vals) < 4:
            continue
        median = _quantile(vals, 0.5)
        cx = ctx.x_scale(cat)
        # Levels: q = 0.25 (innermost = box), then halve outward.
        # k = 0: [0.25, 0.75]
        # k = 1: [0.125, 0.875]
        # k = 2: [0.0625, 0.9375] ...
        # Stop when fewer than ~8 samples would fall outside.
        out_boxes = []
        n = len(vals)
        for k in range(max_levels):
            q_lo = 0.25 / (2 ** k)
            q_hi = 1 - q_lo
            if q_lo * n < 1:
                break
            out_boxes.append((q_lo, q_hi, k))
        # Draw outermost first (widest, palest); innermost last.
        for q_lo, q_hi, k in reversed(out_boxes):
            v_lo = _quantile(vals, q_lo)
            v_hi = _quantile(vals, q_hi)
            # Width shrinks for outer boxes — gives the visual ladder.
            scale = 1.0 - k * 0.18
            w_px = band * bw_frac * max(scale, 0.2)
            shade = _mix_to_white(col, min(0.75, 0.18 * k))
            y_top = ctx.y_scale(max(v_lo, v_hi))
            y_bot = ctx.y_scale(min(v_lo, v_hi))
            out.append(
                f'<rect x="{cx - w_px / 2:.2f}" y="{y_top:.2f}" '
                f'width="{w_px:.2f}" height="{abs(y_bot - y_top):.2f}" '
                f'fill="{shade}" stroke="{col}" stroke-width="0.6"/>'
            )
        # Median tick across the innermost box.
        y_med = ctx.y_scale(median)
        inner_w = band * bw_frac
        out.append(
            f'<line x1="{cx - inner_w / 2:.2f}" x2="{cx + inner_w / 2:.2f}" '
            f'y1="{y_med:.2f}" y2="{y_med:.2f}" stroke="{col}" stroke-width="1.6"/>'
        )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="boxen",
    record=boxen_record,
    xdomain=boxen_xdomain,
    ydomain=boxen_ydomain,
    draw=boxen_draw,
))


if __name__ == "__main__":
    import random
    random.seed(0)
    cats = ["A", "B", "C", "D"]
    groups = [
        [random.gauss(5, 1) for _ in range(500)],
        [random.gauss(6, 1.2) for _ in range(500)] + [random.gauss(11, 0.5) for _ in range(20)],
        [random.gauss(5.5, 0.8) for _ in range(500)],
        [random.gauss(7.5, 1.5) for _ in range(500)] + [random.gauss(2, 0.5) for _ in range(15)],
    ]
    c = pt.chart()
    c.xscale("category", order=cats)
    c.boxen(cats, groups)
    c.title("Letter-value plot").xlabel("group").ylabel("value")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
