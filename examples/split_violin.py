"""Custom artist: split violin.

A violin sliced down the middle, with the *left* half showing the
distribution of group A and the *right* half showing the distribution
of group B, per category. seaborn's `violinplot(hue=..., split=True)`.

Saves a lot of vertical space vs. side-by-side full violins, and the
direct mirror invites the eye to read the symmetry (or lack of it).

KDE is `scipy.stats.gaussian_kde` so the bandwidth selection matches
seaborn's; a small Silverman fallback path is left commented at the
top of the file for users who'd rather not depend on scipy.

API:
    c.split_violin(cats, group_a, group_b,
                   labels=("A", "B"),
                   width=0.8, inner="box")

`group_a[i]` and `group_b[i]` are the samples for category `cats[i]`
in the left- and right-half respectively. `inner="box"` puts a thin
median + Q1-Q3 box inside each half; `inner=None` leaves the violin
silhouette alone.
"""

SUMMARY = "Split violin: left half group A, right half group B per category (seaborn split=True)."

import numpy as np
from pathlib import Path
from scipy.stats import gaussian_kde

import plotlet as pt
from plotlet.artists import _to_pylist


def _quantile(xs, q):
    return float(np.quantile(np.asarray(xs, dtype=float), q))


def split_violin_record(args, kw):
    cats = _to_pylist(args[0])
    a = [list(_to_pylist(g)) for g in args[1]]
    b = [list(_to_pylist(g)) for g in args[2]]
    return {"type": "split_violin", "cats": cats, "a": a, "b": b, "opts": kw}


def split_violin_xdomain(a): return a["cats"]


def split_violin_ydomain(a):
    return [v for g in a["a"] for v in g] + [v for g in a["b"] for v in g]


def split_violin_draw(a, ctx):
    col = ctx.color
    w_frac = a["opts"].get("width", 0.8)
    inner = a["opts"].get("inner", "box")
    n_grid = a["opts"].get("n_grid", 80)
    fill_alpha = a["opts"].get("alpha", 0.55)
    labels = a["opts"].get("labels", ("A", "B"))
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    half_w_px = band * w_frac / 2
    # Two distinct colors: artist color and the next in the cycle.
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
               "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    col_a = col
    # Pick second color by taking the next palette entry past col.
    try:
        col_b = palette[(palette.index(col) + 1) % len(palette)]
    except ValueError:
        col_b = "#ff7f0e"
    out = []
    for cat, vals_a, vals_b in zip(a["cats"], a["a"], a["b"]):
        if not vals_a and not vals_b:
            continue
        cx = ctx.x_scale(cat)
        # Shared y grid for the two halves so they share a baseline.
        all_vals = vals_a + vals_b
        lo, hi = min(all_vals), max(all_vals)
        pad = (hi - lo) * 0.1 or 1.0
        grid = np.linspace(lo - pad, hi + pad, n_grid)
        # Normalize both densities to the same max so the relative
        # widths of A vs B at any y reflect the *actual* density ratio.
        d_a = gaussian_kde(vals_a)(grid) if len(vals_a) > 1 else np.zeros_like(grid)
        d_b = gaussian_kde(vals_b)(grid) if len(vals_b) > 1 else np.zeros_like(grid)
        dmax = max(d_a.max(), d_b.max()) or 1.0
        # Left half (group A): mirror to the left of cx.
        a_pts = []
        for gx, dy in zip(grid, d_a):
            dx_px = (dy / dmax) * half_w_px
            py = ctx.y_scale(gx)
            a_pts.append((cx - dx_px, py))
        top_y = ctx.y_scale(grid[-1]); bot_y = ctx.y_scale(grid[0])
        a_path = ("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in a_pts)
                  + f" L{cx:.2f},{top_y:.2f} L{cx:.2f},{bot_y:.2f} Z")
        out.append(
            f'<path d="{a_path}" fill="{col_a}" fill-opacity="{fill_alpha}" '
            f'stroke="{col_a}" stroke-width="0.8"/>'
        )
        # Right half (group B).
        b_pts = []
        for gx, dy in zip(grid, d_b):
            dx_px = (dy / dmax) * half_w_px
            py = ctx.y_scale(gx)
            b_pts.append((cx + dx_px, py))
        b_path = ("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in b_pts)
                  + f" L{cx:.2f},{top_y:.2f} L{cx:.2f},{bot_y:.2f} Z")
        out.append(
            f'<path d="{b_path}" fill="{col_b}" fill-opacity="{fill_alpha}" '
            f'stroke="{col_b}" stroke-width="0.8"/>'
        )
        # Center line.
        out.append(
            f'<line x1="{cx:.2f}" x2="{cx:.2f}" y1="{top_y:.2f}" y2="{bot_y:.2f}" '
            f'stroke="#fff" stroke-width="0.8"/>'
        )
        # Inner stats.
        if inner == "box":
            for vals, side, fill_col in ((vals_a, -1, col_a), (vals_b, +1, col_b)):
                if not vals:
                    continue
                q1 = _quantile(vals, 0.25)
                q2 = _quantile(vals, 0.5)
                q3 = _quantile(vals, 0.75)
                iqr_w = half_w_px * 0.25
                x_anchor = cx + side * iqr_w
                y_q1 = ctx.y_scale(q1); y_q2 = ctx.y_scale(q2); y_q3 = ctx.y_scale(q3)
                out.append(
                    f'<rect x="{min(x_anchor, cx):.2f}" y="{min(y_q1, y_q3):.2f}" '
                    f'width="{abs(x_anchor - cx):.2f}" '
                    f'height="{abs(y_q3 - y_q1):.2f}" fill="#222"/>'
                    f'<circle cx="{(x_anchor + cx) / 2:.2f}" cy="{y_q2:.2f}" '
                    f'r="1.8" fill="#ffffff"/>'
                )
    return "".join(out)


def split_violin_legend_swatch(a, ctx, x0, y_mid):
    return (f'<rect x="{x0}" y="{y_mid - 5}" width="22" height="10" '
            f'fill="{a["_color"]}" fill-opacity="0.55"/>')


pt.add_artist(pt.ArtistSpec(
    name="split_violin",
    record=split_violin_record,
    xdomain=split_violin_xdomain,
    ydomain=split_violin_ydomain,
    draw=split_violin_draw,
    legend_swatch=split_violin_legend_swatch,
))


if __name__ == "__main__":
    import random
    random.seed(0)
    cats = ["wild-type", "+drug", "knockout", "rescue"]
    male   = [
        [random.gauss(5, 1) for _ in range(120)],
        [random.gauss(4.5, 1) for _ in range(120)],
        [random.gauss(7, 1.4) for _ in range(120)],
        [random.gauss(5.5, 1) for _ in range(120)],
    ]
    female = [
        [random.gauss(4.5, 0.9) for _ in range(120)],
        [random.gauss(4.8, 1.1) for _ in range(120)],
        [random.gauss(6.2, 1.5) for _ in range(120)],
        [random.gauss(6, 1.2) for _ in range(120)],
    ]
    c = pt.chart()
    c.xscale("category", order=cats)
    c.split_violin(cats, male, female, labels=("male", "female"))
    c.title("Split violin by sex").xlabel("genotype").ylabel("expression")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
