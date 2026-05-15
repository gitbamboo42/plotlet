"""Custom artist: raincloud plot.

Allen-Wilkinson (2019) "rain cloud": a half-violin (the cloud) plus
boxplot (the umbrella) plus jittered strip (the rain), stacked
side-by-side per category. Makes the distribution shape, summary
statistics, and individual observations all readable at once — modern
biology paper standard.

API:
    c.raincloud(cats, values_per_cat, width=0.8)

The half-violin is drawn on the upper side of each category center,
the box is centered, and the strip is on the lower side.
"""

SUMMARY = "Half-violin + box + jittered strip per category — Allen-Wilkinson modern bio paper standard."

import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import path, rect, segment, circle


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


def _quantile(xs, q):
    xs = sorted(xs)
    n = len(xs)
    if n == 0: return float("nan")
    if n == 1: return xs[0]
    pos = (n - 1) * q
    lo = int(pos); hi = min(lo + 1, n - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _hash01(i, j):
    h = (i * 2654435761 ^ j * 40503) & 0xFFFFFFFF
    return (h / 0xFFFFFFFF) - 0.5


def raincloud_record(args, kw):
    cats = to_list(args[0])
    groups = [list(to_list(g)) for g in args[1]]
    return {"type": "raincloud", "cats": cats, "groups": groups, "opts": kw}


def raincloud_xdomain(a): return a["cats"]
def raincloud_ydomain(a): return [v for g in a["groups"] for v in g]


def raincloud_draw(a, ctx):
    col = ctx.color
    bw_frac = a["opts"].get("width", 0.8)
    n_grid = a["opts"].get("n_grid", 80)
    fill_alpha = a["opts"].get("alpha", 0.45)
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    full_w = band * bw_frac
    third = full_w / 3
    out = []
    for i, (cat, vals) in enumerate(zip(a["cats"], a["groups"])):
        if not vals:
            continue
        cx = ctx.x_scale(cat)
        # Three sub-band centers (left to right): violin, box, strip.
        cx_violin = cx - third
        cx_box = cx
        cx_strip = cx + third

        # --- half-violin on the LEFT ---
        bw = _silverman(vals)
        lo_v, hi_v = min(vals), max(vals)
        pad = (hi_v - lo_v) * 0.1 or 1.0
        grid = [lo_v - pad + (hi_v - lo_v + 2 * pad) * j / (n_grid - 1)
                for j in range(n_grid)]
        d = _kde(vals, grid, bw)
        dmax = max(d) or 1.0
        # Half-violin extends LEFT from cx_violin.
        left_pts = []
        for gx, dy in zip(grid, d):
            dx_px = (dy / dmax) * (third * 0.9)
            py = ctx.y_scale(gx)
            left_pts.append((cx_violin - dx_px, py))
        # Close along the vertical axis line.
        top_y = ctx.y_scale(grid[-1]); bot_y = ctx.y_scale(grid[0])
        path_d = ("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in left_pts)
                  + f" L{cx_violin:.2f},{top_y:.2f} L{cx_violin:.2f},{bot_y:.2f} Z")
        out.append(path(path_d, fill=col, stroke=col, stroke_width=0.8,
                        fill_alpha=fill_alpha, stroke_alpha=1))

        # --- box in the MIDDLE ---
        q1 = _quantile(vals, 0.25); q2 = _quantile(vals, 0.5); q3 = _quantile(vals, 0.75)
        iqr = q3 - q1
        whis_lo = max(min(vals), q1 - 1.5 * iqr)
        whis_hi = min(max(vals), q3 + 1.5 * iqr)
        box_w = third * 0.55
        x0 = cx_box - box_w / 2; x1 = cx_box + box_w / 2
        y_q1 = ctx.y_scale(q1); y_q2 = ctx.y_scale(q2); y_q3 = ctx.y_scale(q3)
        y_lo = ctx.y_scale(whis_lo); y_hi = ctx.y_scale(whis_hi)
        out.append(
            rect(x0, min(y_q1, y_q3), box_w, abs(y_q3 - y_q1),
                 fill=col, stroke=col, stroke_width=1,
                 fill_alpha=0.25, stroke_alpha=1)
            + segment(x0, y_q2, x1, y_q2, color=col, width=1.6)
            + segment(cx_box, y_q1, cx_box, y_lo, color=col, width=1)
            + segment(cx_box, y_q3, cx_box, y_hi, color=col, width=1)
        )

        # --- jittered strip on the RIGHT ---
        r = a["opts"].get("dot_size", 2.5)
        for j, v in enumerate(vals):
            dx = _hash01(i, j) * (third * 0.5)
            px = cx_strip + dx
            py = ctx.y_scale(v)
            out.append(circle(px, py, r, fill=col, alpha=0.55))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="raincloud",
    record=raincloud_record,
    xdomain=raincloud_xdomain,
    ydomain=raincloud_ydomain,
    draw=raincloud_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    cats = ["control", "drug A", "drug B"]
    groups = [
        [random.gauss(5, 1.0) for _ in range(80)],
        [random.gauss(6.2, 1.1) for _ in range(80)] + [random.gauss(2.5, 0.4) for _ in range(8)],
        [random.gauss(7.5, 1.4) for _ in range(80)],
    ]
    c = pt.chart()
    c.xscale("category", order=cats)
    c.raincloud(cats, groups)
    c.title("Raincloud plot").xlabel("group").ylabel("score")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
