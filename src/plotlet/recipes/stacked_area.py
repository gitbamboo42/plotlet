"""Custom artist: stacked area chart.

Each call to `c.stacked_area(xs, ys, ...)` adds a band on top of whatever
previous `stacked_area` calls already drew, like the area-chart cousin
of `stacked_bar`. The `_base` and `_top` values are passed as private
kwargs by the `stacked_areas(...)` helper so each call's `record()`
stays a pure function of its inputs (the deferred-rendering contract).

API:
    stacked_areas(c, xs, [series_a, series_b, ...], labels=[...])
"""

SUMMARY = 'Stacked area chart for additive over-time series (energy mix, market share, epidemic curves).'

from pathlib import Path

import plotlet as pt
from plotlet.draw import polygon, rect
from plotlet.utils import to_list


def stacked_area_record(args, kw):
    kw = dict(kw)
    base = kw.pop("_base", None)
    top = kw.pop("_top", None)
    out = {"type": "stacked_area",
           "xs": to_list(args[0]),
           "ys": to_list(args[1]),
           "opts": kw}
    if base is not None: out["_base"] = base
    if top is not None: out["_top"] = top
    return out


def stacked_area_xdomain(a): return a["xs"]


def stacked_area_ydomain(a):
    # `_top` is the cumulative-top for this segment; use it so autoscale
    # sees the full stack height, not just one band.
    return list(a.get("_top", a["ys"])) + [0]


def stacked_area_draw(a, ctx):
    col = ctx.color
    alpha = a["opts"].get("alpha", 0.85)
    base = a.get("_base", [0] * len(a["xs"]))
    top = [b + y for b, y in zip(base, a["ys"])]
    # Build a closed polygon: top-edge L->R, then base-edge R->L.
    pts = [(ctx.x_scale(x), ctx.y_scale(t)) for x, t in zip(a["xs"], top)]
    pts += [(ctx.x_scale(x), ctx.y_scale(b)) for x, b in zip(reversed(a["xs"]),
                                                              reversed(base))]
    return polygon(pts, fill=col, alpha=alpha)


def stacked_area_legend_swatch(a, ctx, x0, y_mid):
    return rect(x0, y_mid - 5, 22, 10, fill=a["_color"])


pt.add_artist(pt.ArtistSpec(
    name="stacked_area",
    record=stacked_area_record,
    xdomain=stacked_area_xdomain,
    ydomain=stacked_area_ydomain,
    draw=stacked_area_draw,
    legend_swatch=stacked_area_legend_swatch,
))


def stacked_areas(c, xs, series_ys, labels=None, colors=None, **opts):
    """Stack `series_ys` on a shared `xs`, computing baselines as we go."""
    labels = labels or [f"series {i}" for i in range(len(series_ys))]
    base = [0.0] * len(xs)
    for i, ys in enumerate(series_ys):
        my_base = list(base)
        top = [b + y for b, y in zip(my_base, ys)]
        kw = {"label": labels[i], "_base": my_base, "_top": top, **opts}
        if colors:
            kw["color"] = colors[i]
        c.stacked_area(xs, ys, **kw)
        base = top
    return c


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import math
    xs = list(range(0, 30))
    coal     = [max(0, 100 - 2 * x + 5 * math.sin(x / 3))      for x in xs]
    gas      = [50 + 10 * math.sin(x / 4 + 1)                   for x in xs]
    nuclear  = [40                                              for _ in xs]
    renewable = [5 + 2.5 * x + 8 * math.sin(x / 5)              for x in xs]
    c = pt.chart()
    stacked_areas(c, xs, [coal, gas, nuclear, renewable],
                  labels=["coal", "gas", "nuclear", "renewables"])
    c.title("Generation mix").xlabel("year").ylabel("TWh").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
