"""Custom artist: bump chart.

A bump chart tracks each series' *rank* over a sequence of periods.
Y is inverted-rank (1 at the top), x is the period. Each entry's line
connects its rank from period to period, with a dot at each step.

API: c.bump(periods, values_per_period_per_series, label=...).
- `periods` -> list of period labels (strings or numbers); used directly
  for the x ticks.
- `values_per_period_per_series` -> list aligned with `periods`; each
  element is itself a list of values for all series at that period.
  Series are identified by index; the highest value gets rank 1.

You typically call bump once per series with the same `periods` —
plotlet's color cycle gives each series its own color and the legend
ties them together.
"""

SUMMARY = 'Ranked categorical lines over a sequence of periods (rank 1 at the top).'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list


def _ranks_descending(values):
    """Return ranks 1..n where rank 1 = largest value (ties broken by index)."""
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))
    ranks = [0] * len(values)
    for r, i in enumerate(order):
        ranks[i] = r + 1
    return ranks


def bump_record(args, kw):
    periods = to_list(args[0])
    series_index = kw.pop("series", None)
    matrix = [list(to_list(row)) for row in args[1]]
    if series_index is None:
        raise TypeError("bump requires series=<index> to identify which row to draw")
    # Compute ranks per period, pull out this series' rank trajectory.
    n_series = len(matrix[0]) if matrix else 0
    if not (0 <= series_index < n_series):
        raise IndexError(f"series={series_index} out of range (0..{n_series - 1})")
    trace = []
    for row in matrix:
        trace.append(_ranks_descending(row)[series_index])
    return {"type": "bump", "periods": periods, "ranks": trace,
            "n_series": n_series, "opts": kw}


def bump_xdomain(a): return a["periods"]


def bump_ydomain(a):
    # Inverted rank: rank 1 at the top. We feed reversed ranks so the
    # linear scale puts rank 1 high.
    return [1, a["n_series"]]


def bump_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 2)
    r = a["opts"].get("size", 4)
    out = []
    pts = []
    for p, rk in zip(a["periods"], a["ranks"]):
        px = ctx.x_scale(p)
        # Flip so rank 1 is at the top.
        py = ctx.y_scale(a["n_series"] + 1 - rk)
        pts.append((px, py))
    if len(pts) > 1:
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{lw}"/>')
    for x, y in pts:
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{col}"/>')
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="bump",
    record=bump_record,
    xdomain=bump_xdomain,
    ydomain=bump_ydomain,
    draw=bump_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    periods = ["Q1", "Q2", "Q3", "Q4"]
    # Rows = periods, cols = series. 4 series.
    matrix = [
        [10, 20, 15, 18],   # Q1
        [22, 18, 14, 19],   # Q2
        [25, 14, 21, 19],   # Q3
        [20, 12, 28, 22],   # Q4
    ]
    series_names = ["alpha", "beta", "gamma", "delta"]
    c = pt.chart()
    for i, name in enumerate(series_names):
        c.bump(periods, matrix, series=i, label=name)
    # Y-axis: data values are inverted-rank, so we relabel them so rank 1
    # reads as "1" at the top, "4" at the bottom.
    n = len(series_names)
    c.yticks(list(range(1, n + 1)), [str(n + 1 - r) for r in range(1, n + 1)])
    c.title("Quarterly rank").ylabel("rank").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
