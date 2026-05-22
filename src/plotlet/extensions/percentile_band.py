"""Custom artist: percentile band (median + spread).

Given a 2-D sample (rows = x positions, cols = repetitions), draw the
median as a solid line and the band between two percentiles (default
25/75) as a translucent ribbon — the classic confidence-band idiom
also seen in seaborn `lineplot(estimator='median')`.

This recipe is also a composition example: most of the work is done by
two `fill_between` + `line` calls under the hood, but we wrap them in
one artist so the call site stays a single line. The reusable bit is
the `_percentiles_from_grid` helper at the top — its output is just
data and can be fed straight to built-in `fill_between` / `line` if
you'd rather skip the artist registration.

API: c.percentile_band(xs, samples, qs=(0.25, 0.75)).
`samples` is a list of rows, each a list of repetitions at xs[i].
"""

SUMMARY = "Median line plus filled percentile ribbon (seaborn `estimator='median'` analogue)."
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list, quantile
from plotlet.draw import polygon, polyline, rect, segment


def _percentiles_from_grid(samples, qs):
    """For each row, compute (median, q_low, q_high)."""
    med = [quantile(row, 0.5) for row in samples]
    lo = [quantile(row, qs[0]) for row in samples]
    hi = [quantile(row, qs[1]) for row in samples]
    return med, lo, hi


def pband_record(args, kw):
    xs = to_list(args[0])
    samples = [list(to_list(row)) for row in args[1]]
    qs = kw.get("qs", (0.25, 0.75))
    med, lo, hi = _percentiles_from_grid(samples, qs)
    return {"type": "percentile_band", "xs": xs, "_med": med,
            "_lo": lo, "_hi": hi, "opts": kw}


def pband_xdomain(a): return a["xs"]
def pband_ydomain(a): return a["_lo"] + a["_hi"]


def pband_draw(a, ctx):
    col = ctx.color
    fill_alpha = a["opts"].get("alpha", 0.25)
    lw = a["opts"].get("linewidth", 1.6)
    # Build the ribbon as a single closed polygon: upper boundary
    # left-to-right, lower boundary right-to-left.
    top = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(a["xs"], a["_hi"])]
    bot = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(a["xs"], a["_lo"])]
    pts = top + bot[::-1]
    out = [polygon(pts, fill=col, alpha=fill_alpha)]
    # Median line.
    line_pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(a["xs"], a["_med"])]
    out.append(polyline(line_pts, color=col, width=lw))
    return "".join(out)


def pband_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        col = a["_color"]
        return (
            rect(x0, y_mid - 5, 22, 10, fill=col, alpha=0.25)
            + segment(x0, y_mid, x0 + 22, y_mid, color=col, width=1.6)
        )
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


pt.add_artist(pt.ArtistSpec(
    name="percentile_band",
    record=pband_record,
    xdomain=pband_xdomain,
    ydomain=pband_ydomain,
    draw=pband_draw,
    legend_entries=pband_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random, math
    random.seed(3)
    xs = [i * 0.5 for i in range(20)]
    # Build samples: noisy sinusoid, 30 reps per x.
    samples = []
    for x in xs:
        mu = math.sin(x) + 0.05 * x
        samples.append([mu + random.gauss(0, 0.3 + 0.05 * x) for _ in range(30)])
    c = pt.chart()
    c.percentile_band(xs, samples, qs=(0.1, 0.9), label="10–90%")
    c.title("Median ± 10/90 percentile").xlabel("x").ylabel("y").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
