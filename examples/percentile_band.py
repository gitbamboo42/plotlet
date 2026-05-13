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
from plotlet.artists import _to_pylist


def _quantile(xs, q):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return float("nan")
    if n == 1:
        return xs[0]
    pos = (n - 1) * q
    lo = int(pos); hi = min(lo + 1, n - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _percentiles_from_grid(samples, qs):
    """For each row, compute (median, q_low, q_high)."""
    med = [_quantile(row, 0.5) for row in samples]
    lo = [_quantile(row, qs[0]) for row in samples]
    hi = [_quantile(row, qs[1]) for row in samples]
    return med, lo, hi


def pband_record(args, kw):
    xs = _to_pylist(args[0])
    samples = [list(_to_pylist(row)) for row in args[1]]
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
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"
    out = [f'<path d="{d}" fill="{col}" fill-opacity="{fill_alpha}"/>']
    # Median line.
    line_pts = [(ctx.x_scale(x), ctx.y_scale(y)) for x, y in zip(a["xs"], a["_med"])]
    d2 = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in line_pts)
    out.append(f'<path d="{d2}" fill="none" stroke="{col}" stroke-width="{lw}"/>')
    return "".join(out)


def pband_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    return (
        f'<rect x="{x0}" y="{y_mid - 5}" width="22" height="10" '
        f'fill="{col}" fill-opacity="0.25"/>'
        f'<line x1="{x0}" x2="{x0 + 22}" y1="{y_mid}" y2="{y_mid}" '
        f'stroke="{col}" stroke-width="1.6"/>'
    )


pt.add_artist(pt.ArtistSpec(
    name="percentile_band",
    record=pband_record,
    xdomain=pband_xdomain,
    ydomain=pband_ydomain,
    draw=pband_draw,
    legend_swatch=pband_legend_swatch,
))


if __name__ == "__main__":
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
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
