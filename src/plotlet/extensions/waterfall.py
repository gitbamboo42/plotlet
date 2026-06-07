"""Custom artist: waterfall chart.

Each bar represents an additive (+) or subtractive (-) contribution to a
running total, with the final bar showing the cumulative result. Bars are
colored differently for positive / negative contributions, with an
optional total bar in a third color.

API: c.waterfall(data=df, label="col", delta="col", total_label="Total",
                 pos_color="#2ca02c", neg_color="#d62728", total_color="#7f7f7f").
The chart is categorical: each `label` becomes an x category.
"""

SUMMARY = 'Successive ± contributions to a running total, with dashed connectors and final total bar.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path, rect, segment


def waterfall_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "waterfall requires long-form input: "
            "c.waterfall(data=df, label='col', delta='col')."
        )
    data = kw.pop("data", None)
    label_col = kw.pop("label", None)
    delta_col = kw.pop("delta", None)
    if data is None or label_col is None or delta_col is None:
        raise TypeError("waterfall requires data=, label=, delta=.")
    labels = to_list(data[label_col])
    deltas = to_list(data[delta_col])
    return {"type": "waterfall", "labels": labels, "deltas": deltas, "opts": kw}


def waterfall_xdomain(a):
    labels = list(a["labels"])
    if a["opts"].get("show_total", True):
        labels = labels + [a["opts"].get("total_label", "Total")]
    return labels


def waterfall_ydomain(a):
    cum = 0
    edges = [0]
    for d in a["deltas"]:
        cum += d
        edges.append(cum)
    return edges


def waterfall_draw(a, ctx):
    pos = a["opts"].get("pos_color", "#2ca02c")
    neg = a["opts"].get("neg_color", "#d62728")
    tot = a["opts"].get("total_color", "#7f7f7f")
    show_total = a["opts"].get("show_total", True)
    show_values = a["opts"].get("show_values", True)
    bw_frac = a["opts"].get("width", 0.7)
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    bar_w = band * bw_frac
    out = []
    cum = 0
    last_x = None; last_y_top = None
    for label, d in zip(a["labels"], a["deltas"]):
        y_lo = cum
        y_hi = cum + d
        cx = ctx.x_scale(label)
        x0 = cx - bar_w / 2
        py_top = ctx.y_scale(max(y_lo, y_hi))
        py_bot = ctx.y_scale(min(y_lo, y_hi))
        col = pos if d >= 0 else neg
        out.append(rect(x0, py_top, bar_w, abs(py_bot - py_top), fill=col))
        if show_values:
            anchor_y = py_top - 3 if d >= 0 else py_bot + 11
            out.append(text_path(f"{d:+g}", cx, anchor_y, 10, anchor="middle"))
        # Dashed connector to the next bar's baseline.
        if last_x is not None:
            ly = ctx.y_scale(cum)
            out.append(segment(last_x + bar_w / 2, ly, x0, ly,
                               color="#888", width=0.7, dash="2,2"))
        last_x = cx
        cum = y_hi
    if show_total:
        label = a["opts"].get("total_label", "Total")
        cx = ctx.x_scale(label)
        x0 = cx - bar_w / 2
        y_top = ctx.y_scale(max(0, cum))
        y_bot = ctx.y_scale(min(0, cum))
        out.append(rect(x0, y_top, bar_w, abs(y_bot - y_top), fill=tot))
        if show_values:
            out.append(text_path(f"{cum:g}", cx, y_top - 3, 10, anchor="middle"))
        if last_x is not None:
            ly = ctx.y_scale(cum)
            out.append(segment(last_x + bar_w / 2, ly, x0, ly,
                               color="#888", width=0.7, dash="2,2"))
    return "".join(out)


def waterfall_legend_entries(a):
    opts = a["opts"]
    entries = [
        {"label": opts.get("pos_label", "increase"),
         "color": opts.get("pos_color", "#2ca02c")},
        {"label": opts.get("neg_label", "decrease"),
         "color": opts.get("neg_color", "#d62728")},
    ]
    if opts.get("show_total", True):
        entries.append({"label": opts.get("total_label", "Total"),
                        "color": opts.get("total_color", "#7f7f7f")})
    return entries


pt.add_artist(pt.ArtistSpec(
    name="waterfall",
    record=waterfall_record,
    xdomain=waterfall_xdomain,
    ydomain=waterfall_ydomain,
    draw=waterfall_draw,
    uses_color_cycle=False,
    legend_entries=waterfall_legend_entries,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    labels = ["Revenue", "COGS", "Op-Ex", "Tax", "Other"]
    deltas = [120, -45, -25, -12, 8]
    c = pt.chart()
    c.xscale("category", order=labels + ["Total"])
    c.waterfall({"label": labels, "delta": deltas}, label="label", delta="delta")
    c.title("Net income breakdown").ylabel("$M").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
