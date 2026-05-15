"""Custom artist: swarm (bee-swarm) plot.

Categorical scatter with deterministic horizontal offset so points don't
overlap — seaborn's `swarmplot`. Algorithm: walk points by y, place each
at the smallest |dx| from the category center that doesn't collide with
any already-placed point.

API: c.swarm(cats, values_per_cat, size=3).
"""

SUMMARY = 'Bee-swarm: categorical scatter with greedy non-overlapping placement.'
import math
from pathlib import Path

import plotlet as pt
from plotlet.draw import circle
from plotlet.utils import to_list


def swarm_record(args, kw):
    cats = to_list(args[0])
    groups = [list(to_list(g)) for g in args[1]]
    return {"type": "swarm", "cats": cats, "groups": groups, "opts": kw}


def swarm_xdomain(a): return a["cats"]
def swarm_ydomain(a): return [v for g in a["groups"] for v in g]


def _place_swarm(ys_pixel, r):
    """Return per-point x offset (in pixels) such that no two circles of
    radius r overlap. Greedy: process in y order, try dx=0 first, then
    expand outward until a non-colliding slot is found."""
    diam = 2 * r + 0.5
    placed = []  # list of (x_off, y_pixel)
    out = [None] * len(ys_pixel)
    for idx in sorted(range(len(ys_pixel)), key=lambda i: ys_pixel[i]):
        y = ys_pixel[idx]
        # Candidate offsets: 0, ±diam/2, ±diam, ±3*diam/2, ...
        for k in range(200):
            for sign in (1, -1) if k > 0 else (1,):
                cand = sign * k * (diam / 2)
                # Check collision against placed neighbors within 2r in y.
                ok = True
                for xo, yo in placed:
                    if abs(yo - y) >= diam:
                        continue
                    if (xo - cand) ** 2 + (yo - y) ** 2 < diam * diam:
                        ok = False; break
                if ok:
                    out[idx] = cand
                    placed.append((cand, y))
                    break
            if out[idx] is not None:
                break
        if out[idx] is None:
            out[idx] = 0  # fallback; shouldn't happen for normal n
    return out


def swarm_draw(a, ctx):
    col = ctx.color
    r = a["opts"].get("size", 3)
    alpha = a["opts"].get("alpha", 0.9)
    out = []
    for cat, vals in zip(a["cats"], a["groups"]):
        if not vals:
            continue
        ys_px = [ctx.y_scale(v) for v in vals]
        dxs = _place_swarm(ys_px, r)
        cx = ctx.x_scale(cat)
        for dy, dx in zip(ys_px, dxs):
            out.append(circle(cx + dx, dy, r, fill=col, alpha=alpha))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="swarm",
    record=swarm_record,
    xdomain=swarm_xdomain,
    ydomain=swarm_ydomain,
    draw=swarm_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    import random
    random.seed(1)
    cats = ["A", "B", "C", "D"]
    groups = [
        [random.gauss(3, 0.6) for _ in range(40)],
        [random.gauss(4.5, 0.7) for _ in range(40)],
        [random.gauss(5.2, 0.5) for _ in range(40)],
        [random.gauss(6.0, 0.9) for _ in range(40)],
    ]
    c = pt.chart()
    c.xscale("category", order=cats)
    c.swarm(cats, groups)
    c.title("Bee-swarm plot").xlabel("group").ylabel("value")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
