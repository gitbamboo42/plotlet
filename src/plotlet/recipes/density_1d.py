"""Custom artist: 1-D density (KDE).

Single Gaussian-KDE curve estimated from a sample. Seaborn's `kdeplot`.
Where `hist` answers "how many in each bin?", `density_1d` answers
"what's the smoothed distribution shape?" — bin-free, scaled so the
area integrates to 1 (so you can overlay multiple groups fairly).

API:
    c.density_1d(values, bw=None, n_grid=200, fill=False, alpha=0.25)

`bw` defaults to Silverman's rule. `fill=True` shades the area under
the curve.
"""

SUMMARY = '1-D Gaussian KDE curve — the bin-free alternative to histogram.'

import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import path, polyline, segment


def _silverman(xs):
    n = len(xs)
    if n < 2: return 1.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / n
    sd = math.sqrt(var) or 1.0
    return 1.06 * sd * n ** (-1 / 5)


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


def density_1d_record(args, kw):
    vals = to_list(args[0])
    n_grid = kw.get("n_grid", 200)
    bw = kw.get("bw") or _silverman(vals)
    if not vals:
        return {"type": "density_1d", "_grid": [], "_d": [], "opts": kw}
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.1 or 1.0
    lo -= pad; hi += pad
    grid = [lo + (hi - lo) * i / (n_grid - 1) for i in range(n_grid)]
    d = _kde(vals, grid, bw)
    return {"type": "density_1d", "_grid": grid, "_d": d, "opts": kw}


def density_1d_xdomain(a): return a["_grid"]
def density_1d_ydomain(a): return list(a["_d"]) + [0]


def density_1d_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.6)
    fill = a["opts"].get("fill", False)
    alpha = a["opts"].get("alpha", 0.25)
    out = []
    pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(a["_grid"], a["_d"])]
    if fill and pts:
        y0 = ctx.y_scale(0)
        d = ("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
             + f" L{pts[-1][0]:.2f},{y0:.2f} L{pts[0][0]:.2f},{y0:.2f} Z")
        out.append(path(d, fill=col, alpha=alpha))
    out.append(polyline(pts, color=col, width=lw))
    return "".join(out)


def density_1d_legend_swatch(a, ctx, x0, y_mid):
    return segment(x0, y_mid, x0 + 22, y_mid, color=a["_color"], width=1.6)


pt.add_artist(pt.ArtistSpec(
    name="density_1d",
    record=density_1d_record,
    xdomain=density_1d_xdomain,
    ydomain=density_1d_ydomain,
    draw=density_1d_draw,
    legend_swatch=density_1d_legend_swatch,
    force_zero_y=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    a = [random.gauss(0, 1) for _ in range(300)]
    b = [random.gauss(1.2, 1.3) for _ in range(300)]
    c = pt.chart()
    c.density_1d(a, label="control", fill=True)
    c.density_1d(b, label="treatment", fill=True)
    c.title("Density").xlabel("value").ylabel("density").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
