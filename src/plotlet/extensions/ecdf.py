"""Custom artist: empirical CDF.

For a 1-D sample, draws F̂(x) = (#{xi ≤ x}) / n as a step function. ECDFs
are the statistician-preferred alternative to histograms: no bin
choice, no smoothing, every observation visible — and overlaying
multiple groups makes distribution differences immediately obvious.

API: c.ecdf(values, complement=False).
- `complement=True` draws 1 - F̂(x) (survival function-ish).
"""

SUMMARY = 'Empirical CDF as a step function — no bin choice, every observation visible.'
from pathlib import Path

import plotlet as pt
from plotlet.draw import polyline, segment
from plotlet.utils import to_list


def ecdf_record(args, kw):
    data = sorted(to_list(args[0]))
    return {"type": "ecdf", "data": data, "opts": kw}


def ecdf_xdomain(a): return a["data"]
def ecdf_ydomain(a): return [0, 1]


def ecdf_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.5)
    complement = a["opts"].get("complement", False)
    n = len(a["data"])
    if n == 0:
        return ""
    # Step coordinates: at each xi, jump from (i-1)/n to i/n.
    pts = []
    prev_y = 1 if complement else 0
    pts.append((ctx.x_scale(a["data"][0]), ctx.y_scale(prev_y)))
    for i, x in enumerate(a["data"], start=1):
        f = i / n
        y = (1 - f) if complement else f
        px = ctx.x_scale(x)
        # Horizontal to xi at previous y, then vertical jump.
        pts.append((px, ctx.y_scale(prev_y)))
        pts.append((px, ctx.y_scale(y)))
        prev_y = y
    return polyline(pts, color=col, width=lw)


def ecdf_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        col = a["_color"]
        return segment(x0, y_mid, x0 + 22, y_mid, color=col, width=1.5)
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


pt.add_artist(pt.ArtistSpec(
    name="ecdf",
    record=ecdf_record,
    xdomain=ecdf_xdomain,
    ydomain=ecdf_ydomain,
    draw=ecdf_draw,
    legend_entries=ecdf_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(0)
    a = [random.gauss(0, 1) for _ in range(200)]
    b = [random.gauss(0.6, 1.3) for _ in range(200)]
    c = pt.chart()
    c.ecdf(a, label="control")
    c.ecdf(b, label="treatment")
    c.title("ECDF").xlabel("value").ylabel("F̂(x)").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
