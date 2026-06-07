"""Custom artist: Bland-Altman agreement plot.

Scatter of (a + b) / 2 vs (a - b), with reference lines for the mean
difference (bias) and the 95 % limits of agreement (bias ± 1.96 σ). The
canonical "do two measurement methods agree?" plot in clinical and
analytical-chem literature.

API: c.bland_altman(data=df, a="col", b="col").
"""

SUMMARY = 'Agreement plot: (a + b) / 2 vs (a − b) with bias and ±1.96 SD limits.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import circle, segment, text_path


def ba_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "bland_altman requires long-form input: "
            "c.bland_altman(data=df, a='col', b='col')."
        )
    data = kw.pop("data", None)
    a_col = kw.pop("a", None)
    b_col = kw.pop("b", None)
    if data is None or a_col is None or b_col is None:
        raise TypeError("bland_altman requires data=, a=, b=.")
    a = to_list(data[a_col])
    b = to_list(data[b_col])
    means = [(x + y) / 2 for x, y in zip(a, b)]
    diffs = [(x - y) for x, y in zip(a, b)]
    n = len(diffs)
    if n == 0:
        bias = 0; sd = 0
    else:
        bias = sum(diffs) / n
        sd = math.sqrt(sum((d - bias) ** 2 for d in diffs) / max(n - 1, 1))
    return {"type": "bland_altman", "means": means, "diffs": diffs,
            "_bias": bias, "_sd": sd, "opts": kw}


def ba_xdomain(a): return a["means"]


def ba_ydomain(a):
    return a["diffs"] + [a["_bias"] + 1.96 * a["_sd"], a["_bias"] - 1.96 * a["_sd"]]


def ba_draw(a, ctx):
    col = ctx.color
    r = a["opts"].get("size", 3)
    out = []
    for x, y in zip(a["means"], a["diffs"]):
        out.append(circle(ctx.x_scale(x), ctx.y_scale(y), r,
                          fill=col, alpha=0.7))
    x_lo = ctx.x_scale(min(a["means"]))
    x_hi = ctx.x_scale(max(a["means"]))
    for y_data, label, dash in (
        (a["_bias"], f"bias = {a['_bias']:+.2f}", None),
        (a["_bias"] + 1.96 * a["_sd"], f"+1.96 SD = {a['_bias'] + 1.96 * a['_sd']:+.2f}", "5,3"),
        (a["_bias"] - 1.96 * a["_sd"], f"−1.96 SD = {a['_bias'] - 1.96 * a['_sd']:+.2f}", "5,3"),
    ):
        py = ctx.y_scale(y_data)
        out.append(segment(x_lo, py, x_hi, py,
                           color="#444", width=0.8, dash=dash))
        out.append(text_path(label, x_hi - 4, py - 4, 10, anchor="end"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="bland_altman",
    record=ba_record,
    xdomain=ba_xdomain,
    ydomain=ba_ydomain,
    draw=ba_draw,
    uses_color_cycle=False,
    default_color="#1f77b4",
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(7)
    # Two methods that mostly agree but have a small bias and growing
    # disagreement at higher values.
    a = [random.uniform(20, 100) for _ in range(80)]
    b = [v + random.gauss(2, 0.05 * v) for v in a]
    c = pt.chart()
    c.bland_altman({"a": a, "b": b}, a="a", b="b")
    c.title("Bland–Altman agreement").xlabel("mean of methods").ylabel("difference (A − B)")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
