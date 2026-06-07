"""Custom artist: split violin.

A violin sliced down the middle, with the *left* half showing the
distribution of group A and the *right* half showing the distribution
of group B, per category.

Saves a lot of vertical space vs. side-by-side full violins, and the
direct mirror invites the eye to read the symmetry (or lack of it).

KDE is `scipy.stats.gaussian_kde`; a small Silverman fallback path is
left commented at the top of the file for users who'd rather not depend
on scipy.

API:
    c.split_violin(data=df, x="cat_col", y="value_col", split="group_col",
                   labels=("A", "B"),
                   width=0.8, inner="box")

`split` must have exactly 2 unique levels — the first-appearing level
fills the left half, the second fills the right half. `inner="box"`
puts a thin median + Q1-Q3 box inside each half; `inner=None` leaves
the violin silhouette alone.
"""

SUMMARY = "Split violin: left half group A, right half group B per category."

import numpy as np
from pathlib import Path
from scipy.stats import gaussian_kde

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import path, segment, rect, circle


def _quantile(xs, q):
    return float(np.quantile(np.asarray(xs, dtype=float), q))


def split_violin_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "split_violin requires long-form input: "
            "c.split_violin(data=df, x='cat_col', y='value_col', split='group_col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    split_col = kw.pop("split", None)
    if data is None or x_col is None or y_col is None or split_col is None:
        raise TypeError("split_violin requires data=, x=, y=, split=.")
    xs = to_list(data[x_col])
    ys = to_list(data[y_col])
    splits = to_list(data[split_col])
    cats: list = []
    for c in xs:
        if c not in cats:
            cats.append(c)
    split_levels: list = []
    for s in splits:
        if s not in split_levels:
            split_levels.append(s)
    if len(split_levels) != 2:
        raise ValueError(
            f"split_violin expects exactly 2 levels in split column "
            f"{split_col!r}, got {len(split_levels)}: {split_levels}"
        )
    a = [[] for _ in cats]
    b = [[] for _ in cats]
    cat_idx = {c: i for i, c in enumerate(cats)}
    for x, y, s in zip(xs, ys, splits):
        i = cat_idx[x]
        if s == split_levels[0]:
            a[i].append(y)
        else:
            b[i].append(y)
    if "labels" not in kw:
        kw["labels"] = (str(split_levels[0]), str(split_levels[1]))
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
        out.append(path(a_path, fill=col_a, stroke=col_a, stroke_width=0.8,
                        fill_alpha=fill_alpha, stroke_alpha=1))
        # Right half (group B).
        b_pts = []
        for gx, dy in zip(grid, d_b):
            dx_px = (dy / dmax) * half_w_px
            py = ctx.y_scale(gx)
            b_pts.append((cx + dx_px, py))
        b_path = ("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in b_pts)
                  + f" L{cx:.2f},{top_y:.2f} L{cx:.2f},{bot_y:.2f} Z")
        out.append(path(b_path, fill=col_b, stroke=col_b, stroke_width=0.8,
                        fill_alpha=fill_alpha, stroke_alpha=1))
        # Center line.
        out.append(segment(cx, top_y, cx, bot_y, color="#fff", width=0.8))
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
                    rect(min(x_anchor, cx), min(y_q1, y_q3),
                         abs(x_anchor - cx), abs(y_q3 - y_q1), fill="#222")
                    + circle((x_anchor + cx) / 2, y_q2, 1.8, fill="#ffffff")
                )
    return "".join(out)


def split_violin_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        return rect(x0, y_mid - 5, 22, 10, fill=a["_color"], alpha=0.55)
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


pt.add_artist(pt.ArtistSpec(
    name="split_violin",
    record=split_violin_record,
    xdomain=split_violin_xdomain,
    ydomain=split_violin_ydomain,
    draw=split_violin_draw,
    legend_entries=split_violin_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
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
    # Tidy: one row per observation with cat, sex, value.
    rows = []
    for ci, cat in enumerate(cats):
        for v in male[ci]:
            rows.append({"genotype": cat, "sex": "male", "expr": v})
        for v in female[ci]:
            rows.append({"genotype": cat, "sex": "female", "expr": v})
    df = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart()
    c.xscale("category", order=cats)
    c.split_violin(df, x="genotype", y="expr", split="sex")
    c.title("Split violin by sex").xlabel("genotype").ylabel("expression")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
