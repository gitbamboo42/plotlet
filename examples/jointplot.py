"""Cookbook recipe: joint plot.

Like `pair_plot` and unlike most cookbook entries, this is a *composition
helper* rather than a registered artist. It builds a 3-cell layout
using `pt.grid([[...]])`:

    +---------+--+
    | top hist|  |
    +---------+--+
    |         | side
    | scatter | hist
    |         |
    +---------+--+

The seaborn `jointplot` staple. Showcases plotlet's grid composition
plus a small per-panel sizing trick (top / right histograms are short
in their long-axis dimension).

API:
    jointplot(xs, ys, kind="scatter", bins=30, panel_size=320, marg_size=80)
"""

SUMMARY = "Scatter with marginal histograms on top and right — composition recipe."

from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist


def jointplot(xs, ys, kind: str = "scatter", bins: int = 30,
              panel_size: int = 320, marg_size: int = 80) -> "pt.Chart":
    """Build a joint plot for `xs` vs `ys`.

    `kind="scatter"` plots raw points; `kind="hex"` plots a hexbin (needs
    the `hexbin` recipe registered).
    """
    xs = _to_pylist(xs); ys = _to_pylist(ys)
    # Top marginal: histogram of x.
    top = pt.chart(data_width=panel_size, data_height=marg_size)
    top.hist(xs, bins=bins)
    top.xticks([])
    top.yticks([])
    # Right marginal: histogram of y, drawn rotated by swapping x/y.
    # plotlet doesn't have horizontal histograms — easiest path is to
    # draw a `barh` over an externally-binned series. We compute bins
    # and emit one bar per bin.
    right = pt.chart(data_width=marg_size, data_height=panel_size)
    if ys:
        lo, hi = min(ys), max(ys)
        if lo == hi: hi = lo + 1
        width = (hi - lo) / bins
        counts = [0] * bins
        for v in ys:
            i = int((v - lo) / width) if v != hi else bins - 1
            if 0 <= i < bins:
                counts[i] += 1
        # Draw each bin as a `rect`. y in [lo + i*w, lo + (i+1)*w], x in [0, count].
        for i, c_ in enumerate(counts):
            right.rect(0, lo + i * width, c_, width, color="#1f77b4")
    right.xticks([])
    right.yticks([])
    # Main: scatter (or hex) of (x, y).
    main = pt.chart(data_width=panel_size, data_height=panel_size)
    if kind == "hex":
        main.hexbin(xs, ys, gridsize=30)
    else:
        main.scatter(xs, ys, s=10, alpha=0.6)
    # Spacer (top-right, blank).
    spacer = pt.chart(data_width=marg_size, data_height=marg_size)
    spacer.xticks([]); spacer.yticks([])
    return pt.grid([[top, spacer], [main, right]])


if __name__ == "__main__":
    import random
    random.seed(0)
    n = 600
    xs = [random.gauss(0, 1) for _ in range(n)]
    ys = [x + random.gauss(0, 0.7) for x in xs]
    fig = jointplot(xs, ys)
    out = Path(__file__).with_suffix(".svg")
    fig.save_svg(out)
    print(f"wrote {out}")
