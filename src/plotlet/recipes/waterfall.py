"""Custom artist: waterfall chart.

Each bar represents an additive (+) or subtractive (-) contribution to a
running total, with the final bar showing the cumulative result. Bars are
colored differently for positive / negative contributions, with an
optional total bar in a third color.

API: c.waterfall(labels, deltas, total_label="Total",
                 pos_color="#2ca02c", neg_color="#d62728", total_color="#7f7f7f").
The chart is categorical: each `label` becomes an x category.
"""

SUMMARY = 'Successive ± contributions to a running total, with dashed connectors and final total bar.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path


def waterfall_record(args, kw):
    labels = to_list(args[0])
    deltas = to_list(args[1])
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
        out.append(
            f'<rect x="{x0:.2f}" y="{py_top:.2f}" '
            f'width="{bar_w:.2f}" height="{abs(py_bot - py_top):.2f}" '
            f'fill="{col}"/>'
        )
        if show_values:
            anchor_y = py_top - 3 if d >= 0 else py_bot + 11
            out.append(text_path(f"{d:+g}", cx, anchor_y, 10, anchor="middle"))
        # Dashed connector to the next bar's baseline.
        if last_x is not None:
            ly = ctx.y_scale(cum)
            out.append(
                f'<line x1="{last_x + bar_w / 2:.2f}" x2="{x0:.2f}" '
                f'y1="{ly:.2f}" y2="{ly:.2f}" '
                f'stroke="#888" stroke-width="0.7" stroke-dasharray="2,2"/>'
            )
        last_x = cx
        cum = y_hi
    if show_total:
        label = a["opts"].get("total_label", "Total")
        cx = ctx.x_scale(label)
        x0 = cx - bar_w / 2
        y_top = ctx.y_scale(max(0, cum))
        y_bot = ctx.y_scale(min(0, cum))
        out.append(
            f'<rect x="{x0:.2f}" y="{y_top:.2f}" '
            f'width="{bar_w:.2f}" height="{abs(y_bot - y_top):.2f}" '
            f'fill="{tot}"/>'
        )
        if show_values:
            out.append(text_path(f"{cum:g}", cx, y_top - 3, 10, anchor="middle"))
        if last_x is not None:
            ly = ctx.y_scale(cum)
            out.append(
                f'<line x1="{last_x + bar_w / 2:.2f}" x2="{x0:.2f}" '
                f'y1="{ly:.2f}" y2="{ly:.2f}" '
                f'stroke="#888" stroke-width="0.7" stroke-dasharray="2,2"/>'
            )
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="waterfall",
    record=waterfall_record,
    xdomain=waterfall_xdomain,
    ydomain=waterfall_ydomain,
    draw=waterfall_draw,
    uses_color_cycle=False,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    labels = ["Revenue", "COGS", "Op-Ex", "Tax", "Other"]
    deltas = [120, -45, -25, -12, 8]
    c = pt.chart()
    c.xscale("category", order=labels + ["Total"])
    c.waterfall(labels, deltas)
    c.title("Net income breakdown").ylabel("$M")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
