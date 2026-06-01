"""Quantile-quantile plot — sample vs theoretical quantiles.

The classic "is my sample normal?" diagnostic. Default comparison is the
standard normal; pass a `scipy.stats` distribution (or another sample)
for an arbitrary reference.

API:
  c.qq(values, dist="normal")              # vs N(0, 1)
  c.qq(values, dist=other_sample)          # two-sample
  c.qq(values, dist=scipy.stats.t(df=5))   # arbitrary scipy.stats RV

The dashed reference line passes through the 0.25/0.75 quantile pair —
robust to outliers in the tails.

Styling kwargs:
  dist="normal"   "normal" | another sample | scipy.stats RV
  size=2.5        point radius in pixels
  alpha=0.7       point opacity
"""
from scipy.stats import norm

from ..registry import ArtistSpec, add_artist
from ..draw import circle, segment
from ..utils import to_list


def _qq_record(args, kw):
    sample = sorted(to_list(args[0]))
    dist = kw.get("dist", "normal")
    n = len(sample)
    pp = [(i + 1) / (n + 1) for i in range(n)]
    if dist == "normal":
        theo = list(norm.ppf(pp))
    elif hasattr(dist, "ppf"):
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


def _qq_xdomain(a): return a["theo"]
def _qq_ydomain(a): return a["sample"]


def _qq_draw(a, ctx):
    col = ctx.color
    r = a["opts"].get("size", 2.5)
    alpha = a["opts"].get("alpha", 0.7)
    out = []
    for tx, sy in zip(a["theo"], a["sample"]):
        px = ctx.x_scale(tx); py = ctx.y_scale(sy)
        out.append(circle(px, py, r, fill=col, alpha=alpha))
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
            out.append(segment(ctx.x_scale(x0), ctx.y_scale(y0),
                               ctx.x_scale(x1e), ctx.y_scale(y1e),
                               color="#888", width=1, dash="4,3"))
    return "".join(out)


add_artist(ArtistSpec(
    name="qq",
    record=_qq_record,
    xdomain=_qq_xdomain,
    ydomain=_qq_ydomain,
    draw=_qq_draw,
))
