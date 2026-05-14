"""Custom artist: quantile-quantile plot.

Plots sample quantiles against theoretical quantiles. Default is the
standard normal; pass a `scipy.stats` distribution (or another sample)
for the comparison. The classic diagnostic for "is my sample normal?"
or "do these two distributions match?".

API:
    c.qq(values, dist="normal")              # vs N(0, 1)
    c.qq(values, dist=other_sample)          # vs another sample (two-sample)
    c.qq(values, dist=scipy.stats.t(df=5))   # vs an arbitrary scipy.stats RV

Reference line goes through the 0.25/0.75 quantile pair (matplotlib's
`qqline="q"` rule).
"""

SUMMARY = "Quantile-quantile plot vs the standard normal (or any scipy.stats distribution / another sample)."

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from scipy.stats import norm


def qq_record(args, kw):
    sample = sorted(to_list(args[0]))
    dist = kw.get("dist", "normal")
    n = len(sample)
    pp = [(i + 1) / (n + 1) for i in range(n)]  # plotting positions
    if dist == "normal":
        theo = list(norm.ppf(pp))
    elif hasattr(dist, "ppf"):                  # any scipy.stats RV
        theo = list(dist.ppf(pp))
    else:
        other = sorted(to_list(dist))
        m = len(other)
        theo = []
        for p in pp:
            pos = (m - 1) * p
            lo = int(pos); hi = min(lo + 1, m - 1)
            theo.append(other[lo] + (other[hi] - other[lo]) * (pos - lo))
    return {"type": "qq", "theo": theo, "sample": sample, "opts": kw}


def qq_xdomain(a): return a["theo"]
def qq_ydomain(a): return a["sample"]


def qq_draw(a, ctx):
    col = ctx.color
    r = a["opts"].get("size", 2.5)
    out = []
    for tx, sy in zip(a["theo"], a["sample"]):
        px = ctx.x_scale(tx); py = ctx.y_scale(sy)
        out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{r}" '
                   f'fill="{col}" opacity="0.7"/>')
    n = len(a["sample"])
    if n >= 4:
        i25 = int(0.25 * (n - 1)); i75 = int(0.75 * (n - 1))
        x1, y1 = a["theo"][i25], a["sample"][i25]
        x2, y2 = a["theo"][i75], a["sample"][i75]
        if x2 != x1:
            slope = (y2 - y1) / (x2 - x1)
            intercept = y1 - slope * x1
            x_lo = min(a["theo"]); x_hi = max(a["theo"])
            pad = (x_hi - x_lo) * 0.05
            x0, x1e = x_lo - pad, x_hi + pad
            y0, y1e = intercept + slope * x0, intercept + slope * x1e
            out.append(
                f'<line x1="{ctx.x_scale(x0):.2f}" x2="{ctx.x_scale(x1e):.2f}" '
                f'y1="{ctx.y_scale(y0):.2f}" y2="{ctx.y_scale(y1e):.2f}" '
                f'stroke="#888" stroke-width="1" stroke-dasharray="4,3"/>'
            )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="qq",
    record=qq_record,
    xdomain=qq_xdomain,
    ydomain=qq_ydomain,
    draw=qq_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(2)
    sample = [random.gauss(0, 1) + 0.2 * (random.expovariate(1) - 1) for _ in range(150)]
    c = pt.chart()
    c.qq(sample, dist="normal")
    c.title("Q-Q plot vs N(0, 1)").xlabel("theoretical quantile").ylabel("sample quantile")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
