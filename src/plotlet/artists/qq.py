"""Quantile-quantile plot — sample vs theoretical quantiles.

The classic "is my sample normal?" diagnostic. Default comparison is the
standard normal; pass a `scipy.stats` distribution (or another sample)
for an arbitrary reference.

API:
  c.qq(data=df, sample="col")                    # vs N(0, 1)
  c.qq(data=df, sample="col", dist=other)        # two-sample / scipy RV
  c.qq(data=df, sample="col", color="group")     # one series per level

The dashed reference line passes through the 0.25/0.75 quantile pair —
robust to outliers in the tails. Ungrouped it stays neutral gray; with
`color=` grouping each group's line takes the group color.

Aesthetics:
  color=          literal point color OR column name → one series per level
  palette=        maps levels → colors when `color=` is a column

Styling kwargs:
  dist="normal"   "normal" | another sample | scipy.stats RV
  size=2.5        point radius in pixels
  alpha=0.7       point opacity
"""
from scipy.stats import norm

from ..registry import ArtistSpec, add_artist
from ..draw import circle, segment
from ..utils import to_list, resolve_aes, long_form_1d, pack_opts
from .._spec import _D


def _qq_build(values, kw):
    sample = sorted(values)
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


def _qq_record(data=None, sample=None, color=None, palette=None,
               # `dist` is consumed by `_qq_build` at record; the rest are
               # style read at draw. All ride in opts.
               dist=None, size=None, alpha=None, label=None, legend=None):
    if data is None or sample is None:
        raise TypeError("qq requires data=, sample= (dist= optional).")
    color_kind, color_value = resolve_aes(data, color)
    base = pack_opts(dist=dist, size=size, alpha=alpha,
                     label=label, legend=legend)
    if color_kind == "column":
        groups, vals = long_form_1d(data, sample, color)
        records = []
        for j, (g, v) in enumerate(zip(groups, vals)):
            opts = dict(base)
            opts["palette"] = palette
            opts["label"] = str(g)
            rec = _qq_build(v, opts)
            rec["groups"] = groups
            rec["_j"] = j
            records.append(rec)
        return records
    if color_value is not None:
        base["color"] = color_value
    return _qq_build(to_list(data[sample]), base)


def _qq_xdomain(a): return a["theo"]
def _qq_ydomain(a): return a["sample"]


def _qq_draw(a, ctx):
    col = ctx.color
    r = a["opts"].get("size", 2.5)
    alpha = a["opts"].get("alpha", 0.7)
    out = []
    for tx, sy in zip(a["theo"], a["sample"]):
        px = ctx.x_scale(tx); py = ctx.y_scale(sy)
        out.append(circle(px, py, r, fill=col, alpha=alpha, project=ctx.warp))
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
            ref_col = col if a.get("groups") else _D["qq_ref_color"]
            out.append(segment(ctx.x_scale(x0), ctx.y_scale(y0),
                               ctx.x_scale(x1e), ctx.y_scale(y1e),
                               color=ref_col, width=1, dash="4,3",
                               project=ctx.warp))
    return "".join(out)


def _qq_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    alpha = a["opts"].get("alpha", 0.7)
    def paint(_a, _ctx, x0, y_mid):
        col = _a.get("_color", _ctx.color)
        return circle(x0 + 11, y_mid, 3, fill=col, alpha=alpha)
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


add_artist(ArtistSpec(
    name="qq",
    record=_qq_record,
    xdomain=_qq_xdomain,
    ydomain=_qq_ydomain,
    draw=_qq_draw,
    legend_entries=_qq_legend_entries,
))
