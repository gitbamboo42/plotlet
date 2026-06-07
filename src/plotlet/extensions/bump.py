"""Custom artist: bump chart.

A bump chart tracks each series' *rank* over a sequence of periods.
Y is inverted-rank (1 at the top), x is the period. Each entry's line
connects its rank from period to period, with a dot at each step.

API:
    c.bump(data=df, x="period_col", y="value_col", group="series_col")

Tidy input: one row per (period, series) observation. The artist groups
by series, computes ranks across series within each period (highest
value at each period gets rank 1), and emits one line per series.
Plotlet's color cycle assigns each series its own color and the
auto-labels populate the legend.
"""

SUMMARY = 'Ranked categorical lines over a sequence of periods (rank 1 at the top).'
from pathlib import Path

import plotlet as pt
from plotlet.draw import circle, polyline
from plotlet.utils import to_list


def _ranks_descending(values):
    """Return ranks 1..n where rank 1 = largest value (ties broken by index)."""
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))
    ranks = [0] * len(values)
    for r, i in enumerate(order):
        ranks[i] = r + 1
    return ranks


def bump_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "bump requires long-form input: "
            "c.bump(data=df, x='period_col', y='value_col', group='series_col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    group_col = kw.pop("group", None)
    if data is None or x_col is None or y_col is None or group_col is None:
        raise TypeError("bump requires data=, x=, y=, group=.")
    xs_all = to_list(data[x_col])
    ys_all = to_list(data[y_col])
    gs_all = to_list(data[group_col])

    periods: list = []
    for p in xs_all:
        if p not in periods:
            periods.append(p)
    series_list: list = []
    for s in gs_all:
        if s not in series_list:
            series_list.append(s)
    n_series = len(series_list)
    series_idx = {s: i for i, s in enumerate(series_list)}

    # Pivot: by_period[i] holds values for each series at periods[i].
    by_period: dict = {p: [None] * n_series for p in periods}
    for p, y, s in zip(xs_all, ys_all, gs_all):
        by_period[p][series_idx[s]] = y

    # Ranks per period, then per-series trajectory.
    ranks_at = {}
    for p in periods:
        ranks_at[p] = _ranks_descending(by_period[p])

    kw.pop("label", None)  # auto-labels per series; ignore call-level label
    records = []
    for s_name in series_list:
        i = series_idx[s_name]
        trace = [ranks_at[p][i] for p in periods]
        records.append({"type": "bump", "periods": periods, "ranks": trace,
                        "n_series": n_series,
                        "opts": dict(kw, label=str(s_name))})
    return records


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
        out.append(polyline(pts, color=col, width=lw))
    for x, y in pts:
        out.append(circle(x, y, r, fill=col))
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
    matrix = [
        [10, 20, 15, 18],   # Q1
        [22, 18, 14, 19],   # Q2
        [25, 14, 21, 19],   # Q3
        [20, 12, 28, 22],   # Q4
    ]
    series_names = ["alpha", "beta", "gamma", "delta"]
    # Tidy: one row per (period, series).
    rows = []
    for p_i, period in enumerate(periods):
        for s_i, name in enumerate(series_names):
            rows.append({"period": period, "series": name,
                         "value": matrix[p_i][s_i]})
    df = {k: [r[k] for r in rows] for k in rows[0]}
    c = pt.chart()
    c.bump(df, x="period", y="value", group="series")
    n = len(series_names)
    c.yticks(list(range(1, n + 1)), [str(n + 1 - r) for r in range(1, n + 1)])
    c.title("Quarterly rank").ylabel("rank").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
