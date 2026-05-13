"""Custom artist: population pyramid.

Two paired horizontal-bar series mirrored around x=0: typically male
counts to the left (drawn as -value) and female to the right. y is
categorical (age band). The demography classic — also useful for any
"group A vs group B by category" comparison where the two groups
deserve symmetric visual emphasis.

API:
    c.pyramid(labels, left_vals, right_vals,
              left_color="#1f77b4", right_color="#e377c2",
              left_label="left", right_label="right",
              height=0.8)

Both `left_vals` and `right_vals` should be *positive*; the artist
flips the left side to the negative x half internally and labels the
x-axis ticks with absolute values via the `xticks_labels` helper
returned alongside.
"""

SUMMARY = 'Population pyramid: paired horizontal bars mirrored around x = 0 (left vs right group).'

from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from plotlet.font import _text_path


def pyramid_record(args, kw):
    labels = _to_pylist(args[0])
    left = _to_pylist(args[1])
    right = _to_pylist(args[2])
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
        out.append(
            f'<rect x="{x_l:.2f}" y="{cy - bar_h / 2:.2f}" '
            f'width="{x0 - x_l:.2f}" height="{bar_h:.2f}" fill="{l_col}"/>'
        )
        # Right bar: from 0 to rv
        x_r = ctx.x_scale(rv)
        out.append(
            f'<rect x="{x0:.2f}" y="{cy - bar_h / 2:.2f}" '
            f'width="{x_r - x0:.2f}" height="{bar_h:.2f}" fill="{r_col}"/>'
        )
    # Top-of-plot legend labels.
    y_top = ctx.y_scale(a["labels"][0]) - band * 0.7
    out.append(_text_path(l_lab, x0 - 6, y_top, 11, anchor="end", color=l_col))
    out.append(_text_path(r_lab, x0 + 6, y_top, 11, anchor="start", color=r_col))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="pyramid",
    record=pyramid_record,
    xdomain=pyramid_xdomain,
    ydomain=pyramid_ydomain,
    draw=pyramid_draw,
    uses_color_cycle=False,
))


if __name__ == "__main__":
    bands = ["0–9", "10–19", "20–29", "30–39", "40–49",
             "50–59", "60–69", "70–79", "80+"]
    male   = [110, 125, 130, 128, 120, 105,  85,  60, 30]
    female = [105, 120, 128, 130, 125, 112,  95,  78, 55]
    c = pt.chart(data_width=480, data_height=320)
    c.yscale("category", order=bands)
    c.pyramid(bands, male, female, left_label="male", right_label="female")
    c.title("Population pyramid").xlabel("count (thousands)")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
