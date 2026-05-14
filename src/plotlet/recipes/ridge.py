"""Custom artist: ridgeline plot.

Stacked, vertically-offset density curves — seaborn / R `ggridges`'s
"joyplot" idiom. Each series gets its own baseline on y; densities are
KDE-shaped via a simple Gaussian kernel, no scipy required.

The whole stack is rendered as one artist so it owns its own y-baselines.
Categories are placed at integer y; densities are scaled to a fraction of
the row spacing.

API: c.ridge(labels, samples_per_label, overlap=1.4, bw=None).
"""

SUMMARY = 'Stacked KDE / joyplot densities, multiple series offset vertically.'
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


def ridge_record(args, kw):
    labels = to_list(args[0])
    groups = [list(to_list(g)) for g in args[1]]
    return {"type": "ridge", "labels": labels, "groups": groups, "opts": kw}


def ridge_xdomain(a):
    flat = [v for g in a["groups"] for v in g]
    return flat


def ridge_ydomain(a):
    # One row per series, plus headroom for the top ridge to spill upward.
    n = len(a["labels"])
    overlap = a["opts"].get("overlap", 1.4)
    return [0, n - 1 + overlap]


def ridge_draw(a, ctx):
    col = ctx.color
    fill_alpha = a["opts"].get("alpha", 0.6)
    overlap = a["opts"].get("overlap", 1.4)
    n_grid = a["opts"].get("n_grid", 200)
    flat = [v for g in a["groups"] for v in g]
    if not flat:
        return ""
    lo, hi = min(flat), max(flat)
    pad = (hi - lo) * 0.05 or 1.0
    lo -= pad; hi += pad
    grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
    out = []
    n = len(a["labels"])
    for i, (label, vals) in enumerate(zip(a["labels"], a["groups"])):
        if not vals:
            continue
        bw = a["opts"].get("bw") or _silverman_bw(vals)
        d = _kde(vals, grid, bw)
        dmax = max(d) or 1.0
        baseline_y = n - 1 - i
        pts = []
        for gx, dy in zip(grid, d):
            px = ctx.x_scale(gx)
            py = ctx.y_scale(baseline_y + (dy / dmax) * overlap)
            pts.append(f"{px:.2f},{py:.2f}")
        # Close back along the baseline to form a filled polygon.
        x_right = ctx.x_scale(grid[-1])
        x_left = ctx.x_scale(grid[0])
        y_base = ctx.y_scale(baseline_y)
        path_d = "M" + " L".join(pts) + f" L{x_right:.2f},{y_base:.2f} L{x_left:.2f},{y_base:.2f} Z"
        out.append(
            f'<path d="{path_d}" fill="{col}" fill-opacity="{fill_alpha}" '
            f'stroke="{col}" stroke-width="1"/>'
        )
        # Row label at the left baseline, in data coords using ctx.x_scale(lo).
        # Use a generic text path through plotlet.font so it's text-as-path.
        from plotlet.draw import text_path
        out.append(text_path(label, ctx.x_scale(lo) + 4,
                              ctx.y_scale(baseline_y) - 3, 11, anchor="start"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="ridge",
    record=ridge_record,
    xdomain=ridge_xdomain,
    ydomain=ridge_ydomain,
    draw=ridge_draw,
    uses_color_cycle=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(2)
    labels = ["Jan", "Feb", "Mar", "Apr", "May"]
    groups = [
        [random.gauss(20 + i, 3) for _ in range(200)]
        for i in range(5)
    ]
    c = pt.chart(data_height=260)
    c.ridge(labels, groups, overlap=1.6)
    c.yticks([])  # row labels are drawn inside; hide the numeric ticks
    c.title("Monthly temperature").xlabel("°C")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
