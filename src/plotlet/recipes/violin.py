"""Custom artist: violin plot.

Mirrored KDE outline with a small box-and-median inside, per category.
The matplotlib / seaborn violin staple: shape conveys the distribution,
the inner stats are the conventional Tukey summary.

API: c.violin(cats, values_per_cat, width=0.8, inner="box").
- `inner="box"`  — Q1-Q3 box + median tick (default)
- `inner="quartile"` — three dashed lines at Q1/Q2/Q3
- `inner=None`   — KDE only
"""

SUMMARY = 'Mirrored KDE outline plus Q1-Q3 box and median tick, per category.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list


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


def _quantile(xs, q):
    xs = sorted(xs)
    n = len(xs)
    if n == 0: return float("nan")
    if n == 1: return xs[0]
    pos = (n - 1) * q
    lo = int(pos); hi = min(lo + 1, n - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def violin_record(args, kw):
    cats = to_list(args[0])
    groups = [list(to_list(g)) for g in args[1]]
    return {"type": "violin", "cats": cats, "groups": groups, "opts": kw}


def violin_xdomain(a): return a["cats"]
def violin_ydomain(a): return [v for g in a["groups"] for v in g]


def violin_draw(a, ctx):
    col = ctx.color
    w_frac = a["opts"].get("width", 0.8)
    inner = a["opts"].get("inner", "box")
    n_grid = a["opts"].get("n_grid", 80)
    fill_alpha = a["opts"].get("alpha", 0.5)
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    half_w_px = band * w_frac / 2
    out = []
    for cat, vals in zip(a["cats"], a["groups"]):
        if not vals:
            continue
        bw = _silverman_bw(vals)
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.1 or 1.0
        grid = [lo - pad + (hi - lo + 2 * pad) * i / (n_grid - 1)
                for i in range(n_grid)]
        d = _kde(vals, grid, bw)
        dmax = max(d) or 1.0
        cx = ctx.x_scale(cat)
        # Symmetric mirror: left side then right side reversed.
        left = []; right = []
        for gx, dy in zip(grid, d):
            dx_px = (dy / dmax) * half_w_px
            py = ctx.y_scale(gx)
            left.append((cx - dx_px, py))
            right.append((cx + dx_px, py))
        pts = left + right[::-1]
        path_d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"
        out.append(
            f'<path d="{path_d}" fill="{col}" fill-opacity="{fill_alpha}" '
            f'stroke="{col}" stroke-width="1"/>'
        )
        # Inner stats.
        q1 = _quantile(vals, 0.25); q2 = _quantile(vals, 0.5); q3 = _quantile(vals, 0.75)
        y_q1, y_q2, y_q3 = ctx.y_scale(q1), ctx.y_scale(q2), ctx.y_scale(q3)
        if inner == "box":
            iqr_w = half_w_px * 0.35
            out.append(
                f'<rect x="{cx - iqr_w:.2f}" y="{min(y_q1, y_q3):.2f}" '
                f'width="{2 * iqr_w:.2f}" height="{abs(y_q3 - y_q1):.2f}" '
                f'fill="#222"/>'
                f'<circle cx="{cx:.2f}" cy="{y_q2:.2f}" r="2" fill="#ffffff"/>'
            )
        elif inner == "quartile":
            for q in (q1, q2, q3):
                py = ctx.y_scale(q)
                out.append(
                    f'<line x1="{cx - half_w_px * 0.7:.2f}" '
                    f'x2="{cx + half_w_px * 0.7:.2f}" '
                    f'y1="{py:.2f}" y2="{py:.2f}" stroke="{col}" '
                    f'stroke-width="1" stroke-dasharray="3,2"/>'
                )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="violin",
    record=violin_record,
    xdomain=violin_xdomain,
    ydomain=violin_ydomain,
    draw=violin_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    cats = ["wild-type", "+drug", "knockout", "rescue"]
    groups = [
        [random.gauss(5, 1) for _ in range(150)],
        [random.gauss(4, 0.8) for _ in range(150)],
        [random.gauss(7, 1.4) for _ in range(150)] + [random.gauss(3.5, 0.5) for _ in range(60)],
        [random.gauss(5.5, 1) for _ in range(150)],
    ]
    c = pt.chart()
    c.xscale("category", order=cats)
    c.violin(cats, groups, inner="box")
    c.title("Expression level by genotype").xlabel("genotype").ylabel("log₂ FPKM")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
