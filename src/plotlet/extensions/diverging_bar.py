"""Custom artist: diverging horizontal bar.

Bars extending left or right of zero, colored by sign. The standard for
likert-scale summaries (negative responses to the left, positive to the
right, neutral straddling zero) and for any "score relative to baseline"
comparison.

API:
    c.diverging_bar(data=df, x="value_col", y="category_col",
                    pos_color="#1f77b4", neg_color="#d62728",
                    height=0.7)

Pair with `c.yscale("category", order=...)` so rows stay in submission
order (plotlet puts the first category at the *top* of the y axis).
"""

SUMMARY = 'Likert / score-vs-baseline bars going left or right of zero, colored by sign.'

from pathlib import Path

import plotlet as pt
from plotlet.draw import rect, segment
from plotlet.utils import to_list


def diverging_bar_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "diverging_bar requires long-form input: "
            "c.diverging_bar(data=df, x='value_col', y='category_col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    if data is None or x_col is None or y_col is None:
        raise TypeError("diverging_bar requires data=, x= (values), y= (categories).")
    return {"type": "diverging_bar",
            "labels": to_list(data[y_col]),
            "values": to_list(data[x_col]),
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
        out.append(rect(x_l, cy - bar_h / 2, w, bar_h, fill=col))
    # Zero reference line drawn on top of the bars (so it stays visible).
    y_top = ctx.y_scale(a["labels"][0]) - band / 2
    y_bot = ctx.y_scale(a["labels"][-1]) + band / 2
    out.append(segment(x0, y_top, x0, y_bot, color="#444", width=0.8))
    return "".join(out)


def diverging_bar_legend_entries(a):
    opts = a["opts"]
    return [
        {"label": opts.get("pos_label", "positive"),
         "color": opts.get("pos_color", "#1f77b4")},
        {"label": opts.get("neg_label", "negative"),
         "color": opts.get("neg_color", "#d62728")},
    ]


pt.add_artist(pt.ArtistSpec(
    name="diverging_bar",
    record=diverging_bar_record,
    xdomain=diverging_bar_xdomain,
    ydomain=diverging_bar_ydomain,
    draw=diverging_bar_draw,
    uses_color_cycle=False,
    legend_entries=diverging_bar_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    items = ["Quality", "Speed", "Support", "Price", "Onboarding",
             "Docs", "Reliability", "Mobile UX"]
    nps = [40, 25, 10, -5, -20, 15, 35, -30]  # net promoter per category
    c = pt.chart(data_width=420)
    c.yscale("category", order=items)
    c.diverging_bar({"item": items, "nps": nps}, x="nps", y="item")
    c.title("Net promoter by area").xlabel("NPS").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
