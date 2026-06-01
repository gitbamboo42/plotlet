"""Custom artist: sales / conversion funnel chart.

Successive horizontal bars centered on x=0, narrowing from top to bottom,
to show conversion / drop-off through a sequence of stages. Each stage's
bar width is proportional to its value relative to the maximum.

Renamed from `funnel` to free that name up for the meta-analysis funnel
plot (see `cookbook/funnel_plot/`). The two are entirely different
charts that happen to share a one-word name.

API: c.sales_funnel(labels, values, color="C0", show_values=True).
The bars are categorical on y; the x-axis is purely visual (no ticks).
"""

SUMMARY = 'Conversion funnel: centered horizontal bars narrowing top-to-bottom with auto-percent labels.'

from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import rect, text_path


def sales_funnel_record(args, kw):
    labels = to_list(args[0])
    values = to_list(args[1])
    return {"type": "sales_funnel", "labels": labels, "values": values, "opts": kw}


def sales_funnel_xdomain(a): return [-1, 1]
def sales_funnel_ydomain(a): return list(a["labels"])


def sales_funnel_draw(a, ctx):
    col = ctx.color
    band = getattr(ctx.y_scale, "bandwidth", 1.0)
    bar_h = band * a["opts"].get("height", 0.7)
    show_values = a["opts"].get("show_values", True)
    show_pct = a["opts"].get("show_pct", True)
    vmax = max(a["values"]) or 1
    first = a["values"][0] if a["values"] else 1
    out = []
    for label, v in zip(a["labels"], a["values"]):
        cy = ctx.y_scale(label)
        frac = v / vmax
        x_l = ctx.x_scale(-frac); x_r = ctx.x_scale(frac)
        out.append(rect(x_l, cy - bar_h / 2, x_r - x_l, bar_h, fill=col))
        if show_values:
            txt = f"{v:g}"
            if show_pct and v != first and first:
                txt += f"  ({v / first * 100:.0f}%)"
            out.append(text_path(txt, (x_l + x_r) / 2, cy + 3, 11,
                                  anchor="middle", color="#ffffff"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="sales_funnel",
    record=sales_funnel_record,
    xdomain=sales_funnel_xdomain,
    ydomain=sales_funnel_ydomain,
    draw=sales_funnel_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    labels = ["Visited", "Signed up", "Activated", "Purchased", "Returned"]
    values = [10000, 3200, 1800, 600, 220]
    c = pt.chart(data_height=260)
    # Plotlet's category scale places the first entry at the *top* of
    # the y axis, so passing `labels` directly puts the top-of-funnel
    # stage at the visual top.
    c.yscale("category", order=labels)
    c.sales_funnel(labels, values)
    c.title("Onboarding funnel")
    c.xticks([])
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
