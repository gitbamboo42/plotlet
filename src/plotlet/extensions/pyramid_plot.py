"""Custom artist: population pyramid.

Two paired horizontal-bar series mirrored around x=0: typically male
counts to the left (drawn as -value) and female to the right. y is
categorical (age band). The demography classic — also useful for any
"group A vs group B by category" comparison where the two groups
deserve symmetric visual emphasis.

API:
    c.pyramid(data=df, y="cat_col", left="col", right="col",
              left_color="#1f77b4", right_color="#e377c2",
              left_label="left", right_label="right",
              height=0.8)

Both `left` and `right` columns should be *positive*; the artist
flips the left side to the negative x half internally and labels the
x-axis ticks with absolute values via the `xticks_labels` helper
returned alongside.
"""

SUMMARY = 'Population pyramid: paired horizontal bars mirrored around x = 0 (left vs right group).'

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import rect, text_path


def pyramid_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "pyramid requires long-form input: "
            "c.pyramid(data=df, y='cat_col', left='col', right='col')."
        )
    data = kw.pop("data", None)
    y_col = kw.pop("y", None)
    left_col = kw.pop("left", None)
    right_col = kw.pop("right", None)
    if data is None or y_col is None or left_col is None or right_col is None:
        raise TypeError("pyramid requires data=, y=, left=, right=.")
    labels = to_list(data[y_col])
    left = to_list(data[left_col])
    right = to_list(data[right_col])
    return {"type": "pyramid", "labels": labels, "left": left, "right": right,
            "opts": kw}


def pyramid_xdomain(a):
    return [-max(a["left"], default=0), max(a["right"], default=0), 0]


def pyramid_ydomain(a): return a["labels"]


def pyramid_draw(a, ctx):
    l_col = a["opts"].get("left_color", "#1f77b4")
    r_col = a["opts"].get("right_color", "#e377c2")
    l_lab = a["opts"].get("left_label", "left")
    r_lab = a["opts"].get("right_label", "right")
    band = getattr(ctx.y_scale, "bandwidth", 1.0)
    bar_h = band * a["opts"].get("height", 0.8)
    x0 = ctx.x_scale(0)
    out = []
    for label, lv, rv in zip(a["labels"], a["left"], a["right"]):
        cy = ctx.y_scale(label)
        # Left bar: from -lv to 0
        x_l = ctx.x_scale(-lv)
        out.append(rect(x_l, cy - bar_h / 2, x0 - x_l, bar_h, fill=l_col))
        # Right bar: from 0 to rv
        x_r = ctx.x_scale(rv)
        out.append(rect(x0, cy - bar_h / 2, x_r - x0, bar_h, fill=r_col))
    # Top-of-plot legend labels.
    y_top = ctx.y_scale(a["labels"][0]) - band * 0.7
    out.append(text_path(l_lab, x0 - 6, y_top, 11, anchor="end", color=l_col))
    out.append(text_path(r_lab, x0 + 6, y_top, 11, anchor="start", color=r_col))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="pyramid",
    record=pyramid_record,
    xdomain=pyramid_xdomain,
    ydomain=pyramid_ydomain,
    draw=pyramid_draw,
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    bands = ["0–9", "10–19", "20–29", "30–39", "40–49",
             "50–59", "60–69", "70–79", "80+"]
    male   = [110, 125, 130, 128, 120, 105,  85,  60, 30]
    female = [105, 120, 128, 130, 125, 112,  95,  78, 55]
    df = {"band": bands, "male": male, "female": female}
    c = pt.chart(data_width=480, data_height=320)
    c.yscale("category", order=bands)
    c.pyramid(df, y="band", left="male", right="female",
              left_label="male", right_label="female")
    c.title("Population pyramid").xlabel("count (thousands)")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
