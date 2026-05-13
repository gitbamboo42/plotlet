"""Custom artist: diverging horizontal bar.

Bars extending left or right of zero, colored by sign. The standard for
likert-scale summaries (negative responses to the left, positive to the
right, neutral straddling zero) and for any "score relative to baseline"
comparison.

API:
    c.diverging_bar(labels, values,
                    pos_color="#1f77b4", neg_color="#d62728",
                    height=0.7)

Pair with `c.yscale("category", order=labels)` so rows stay in submission
order (plotlet puts the first category at the *top* of the y axis).
"""

SUMMARY = 'Likert / score-vs-baseline bars going left or right of zero, colored by sign.'

from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist


def diverging_bar_record(args, kw):
    labels = _to_pylist(args[0])
    values = _to_pylist(args[1])
    return {"type": "diverging_bar", "labels": labels, "values": values,
            "opts": kw}


def diverging_bar_xdomain(a):
    return list(a["values"]) + [0]


def diverging_bar_ydomain(a):
    return a["labels"]


def diverging_bar_draw(a, ctx):
    pos = a["opts"].get("pos_color", "#1f77b4")
    neg = a["opts"].get("neg_color", "#d62728")
    band = getattr(ctx.y_scale, "bandwidth", 1.0)
    bar_h = band * a["opts"].get("height", 0.7)
    x0 = ctx.x_scale(0)
    out = []
    for label, v in zip(a["labels"], a["values"]):
        col = pos if v >= 0 else neg
        cy = ctx.y_scale(label)
        xv = ctx.x_scale(v)
        x_l = min(x0, xv); w = abs(xv - x0)
        out.append(
            f'<rect x="{x_l:.2f}" y="{cy - bar_h / 2:.2f}" '
            f'width="{w:.2f}" height="{bar_h:.2f}" fill="{col}"/>'
        )
    # Zero reference line drawn on top of the bars (so it stays visible).
    y_top = ctx.y_scale(a["labels"][0]) - band / 2
    y_bot = ctx.y_scale(a["labels"][-1]) + band / 2
    out.append(
        f'<line x1="{x0:.2f}" x2="{x0:.2f}" y1="{y_top:.2f}" y2="{y_bot:.2f}" '
        f'stroke="#444" stroke-width="0.8"/>'
    )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="diverging_bar",
    record=diverging_bar_record,
    xdomain=diverging_bar_xdomain,
    ydomain=diverging_bar_ydomain,
    draw=diverging_bar_draw,
    uses_color_cycle=False,
))


if __name__ == "__main__":
    items = ["Quality", "Speed", "Support", "Price", "Onboarding",
             "Docs", "Reliability", "Mobile UX"]
    nps = [40, 25, 10, -5, -20, 15, 35, -30]  # net promoter per category
    c = pt.chart(data_width=420)
    c.yscale("category", order=items)
    c.diverging_bar(items, nps)
    c.title("Net promoter by area").xlabel("NPS")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
