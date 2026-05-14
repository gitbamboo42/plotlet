"""Custom artist: strip / jitter plot.

A categorical scatter: each sample is a small dot near its category's x,
with a deterministic horizontal jitter so overlapping points stay
distinguishable. Useful alongside (or instead of) a boxplot for showing
the actual sample, seaborn-style.

API: c.strip(cats, values_per_cat, jitter=0.2, size=3).
Jitter is in band-fractions: 0.2 means +/- 10 % of bandwidth.
"""

SUMMARY = 'Categorical scatter with deterministic jitter (no per-render RNG).'
import math
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list


def _hash01(i, j):
    """Deterministic pseudo-random in [-0.5, 0.5] from two ints. No RNG state."""
    h = (i * 2654435761 ^ j * 40503) & 0xFFFFFFFF
    return ((h / 0xFFFFFFFF) - 0.5)


def strip_record(args, kw):
    cats = to_list(args[0])
    groups = [list(to_list(g)) for g in args[1]]
    return {"type": "strip", "cats": cats, "groups": groups, "opts": kw}


def strip_xdomain(a): return a["cats"]
def strip_ydomain(a): return [v for g in a["groups"] for v in g]


def strip_draw(a, ctx):
    col = ctx.color
    jitter = a["opts"].get("jitter", 0.2)
    r = a["opts"].get("size", 3)
    alpha = a["opts"].get("alpha", 0.7)
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    out = []
    for i, (cat, vals) in enumerate(zip(a["cats"], a["groups"])):
        cx = ctx.x_scale(cat)
        for j, v in enumerate(vals):
            if v != v:  # NaN
                continue
            dx = _hash01(i, j) * band * jitter
            px = cx + dx
            py = ctx.y_scale(v)
            out.append(
                f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{r}" '
                f'fill="{col}" opacity="{alpha}"/>'
            )
    return "".join(out)


def strip_legend_swatch(a, ctx, x0, y_mid):
    col = a["_color"]
    alpha = a["opts"].get("alpha", 0.7)
    return (
        f'<circle cx="{x0 + 6}" cy="{y_mid}" r="2.5" fill="{col}" opacity="{alpha}"/>'
        f'<circle cx="{x0 + 14}" cy="{y_mid - 2}" r="2.5" fill="{col}" opacity="{alpha}"/>'
        f'<circle cx="{x0 + 18}" cy="{y_mid + 2}" r="2.5" fill="{col}" opacity="{alpha}"/>'
    )


pt.add_artist(pt.ArtistSpec(
    name="strip",
    record=strip_record,
    xdomain=strip_xdomain,
    ydomain=strip_ydomain,
    draw=strip_draw,
    legend_swatch=strip_legend_swatch,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(1)
    cats = ["A", "B", "C", "D"]
    groups = [
        [random.gauss(3, 0.8) for _ in range(30)],
        [random.gauss(4.5, 1.0) for _ in range(30)],
        [random.gauss(5.2, 0.6) for _ in range(30)],
        [random.gauss(6.1, 1.2) for _ in range(30)],
    ]
    c = pt.chart()
    c.strip(cats, groups)
    c.title("Strip plot").xlabel("condition").ylabel("value")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
