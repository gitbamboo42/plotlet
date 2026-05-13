"""Custom artist: stacked bar chart.

Bars composed of vertically-stacked segments, one per series. Each call
to `c.stacked_bar(cats, vals, ...)` adds one *segment*; the segment's
baseline is provided explicitly via the internal `_base` kwarg so the
artist stays a pure function of its inputs (no cross-call state in the
record() function, which the deferred-rendering contract forbids).

The `stacked_bars(...)` helper handles the bookkeeping for the common
case where you have a list of series and want them stacked in order.

API:
    stacked_bars(c, cats, [series_a, series_b, ...], labels=[...])
"""

SUMMARY = 'Vertically stacked segments per category; ships with a `stacked_bars(...)` helper.'
from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from plotlet._spec import _D


def stacked_bar_record(args, kw):
    kw = dict(kw)
    base = kw.pop("_base", None)
    tops = kw.pop("_tops", None)
    out = {"type": "stacked_bar",
           "cats": _to_pylist(args[0]),
           "vals": _to_pylist(args[1]),
           "opts": kw}
    if base is not None: out["_base"] = base
    if tops is not None: out["_tops"] = tops
    return out


def stacked_bar_xdomain(a): return a["cats"]


def stacked_bar_ydomain(a):
    # `_tops` is each segment's cumulative top edge — set by the helper
    # so autoscale sees the *real* stack height, not just one segment.
    return list(a.get("_tops", a["vals"])) + [0]


def stacked_bar_draw(a, ctx):
    col = ctx.color
    alpha = a["opts"].get("alpha", _D["bar_alpha"])
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    bar_w = band * a["opts"].get("width", 0.8)
    base = a.get("_base", {cat: 0 for cat in a["cats"]})
    out = []
    for cat, v in zip(a["cats"], a["vals"]):
        cx = ctx.x_scale(cat)
        x0 = cx - bar_w / 2
        y_top = ctx.y_scale(base.get(cat, 0) + v)
        y_bot = ctx.y_scale(base.get(cat, 0))
        out.append(
            f'<rect x="{x0:.2f}" y="{min(y_top, y_bot):.2f}" '
            f'width="{bar_w:.2f}" height="{abs(y_bot - y_top):.2f}" '
            f'fill="{col}" opacity="{alpha}"/>'
        )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="stacked_bar",
    record=stacked_bar_record,
    xdomain=stacked_bar_xdomain,
    ydomain=stacked_bar_ydomain,
    draw=stacked_bar_draw,
    legend_swatch=lambda a, ctx, x0, ym: (
        f'<rect x="{x0}" y="{ym - 5}" width="22" height="10" fill="{a["_color"]}"/>'
    ),
))


def stacked_bars(c, cats, series_vals, labels=None, colors=None, **opts):
    """Stack `series_vals` on `cats`, computing baselines as we go."""
    labels = labels or [f"series {i}" for i in range(len(series_vals))]
    base = {cat: 0 for cat in cats}
    for i, vals in enumerate(series_vals):
        my_base = dict(base)
        kw = {"label": labels[i],
              "_base": my_base,
              "_tops": [my_base[cat] + v for cat, v in zip(cats, vals)],
              **opts}
        if colors:
            kw["color"] = colors[i]
        c.stacked_bar(cats, vals, **kw)
        for cat, v in zip(cats, vals):
            base[cat] += v
    return c


if __name__ == "__main__":
    cats = ["Q1", "Q2", "Q3", "Q4"]
    series_vals = [
        [12, 18, 15, 22],   # product A
        [ 8, 14, 16, 18],   # product B
        [ 5,  7,  9, 11],   # product C
    ]
    c = pt.chart()
    stacked_bars(c, cats, series_vals, labels=["A", "B", "C"])
    c.title("Revenue by product").ylabel("$M").legend(True)
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
