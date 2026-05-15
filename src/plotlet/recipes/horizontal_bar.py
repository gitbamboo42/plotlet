"""Custom artist: horizontal bar (a.k.a. `barh`).

matplotlib calls this `barh`. Categorical y, numeric x. Useful when the
category names are long — horizontal labels read more easily than rotated
vertical ones.

API: c.barh(cats, vals, width=0.8). Mirrors plt.barh.
"""

SUMMARY = '`barh` for long category labels.'
from pathlib import Path

import plotlet as pt
from plotlet.draw import rect
from plotlet.utils import to_list
from plotlet._spec import _D


def barh_record(args, kw):
    return {"type": "barh", "cats": to_list(args[0]),
            "vals": to_list(args[1]), "opts": kw}


def barh_xdomain(a): return list(a["vals"]) + [0]
def barh_ydomain(a): return a["cats"]


def barh_draw(a, ctx):
    col = ctx.color
    alpha = a["opts"].get("alpha", _D["bar_alpha"])
    band = getattr(ctx.y_scale, "bandwidth", 1.0)
    bar_h = band * a["opts"].get("width", 0.8)
    x0 = ctx.x_scale(0)
    out = []
    for cat, v in zip(a["cats"], a["vals"]):
        cy = ctx.y_scale(cat)
        x_v = ctx.x_scale(v)
        x_l = min(x0, x_v); w = abs(x_v - x0)
        out.append(rect(x_l, cy - bar_h / 2, w, bar_h, fill=col, alpha=alpha))
    return "".join(out)


def barh_legend_swatch(a, ctx, x0, y_mid):
    return rect(x0, y_mid - 5, 22, 10, fill=a["_color"])


pt.add_artist(pt.ArtistSpec(
    name="barh",
    record=barh_record,
    xdomain=barh_xdomain,
    ydomain=barh_ydomain,
    draw=barh_draw,
    legend_swatch=barh_legend_swatch,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    cats = ["Python", "JavaScript", "TypeScript", "Rust", "Go", "C++"]
    vals = [42, 38, 27, 18, 14, 11]
    c = pt.chart()
    # Plotlet places the first category at the *top* of the y axis, so
    # passing `cats` directly puts the largest bar at the top.
    c.yscale("category", order=cats)
    c.barh(cats, vals)
    c.title("Stack share").xlabel("% respondents")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
