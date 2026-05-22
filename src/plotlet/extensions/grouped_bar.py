"""Custom artist: grouped (a.k.a. dodged) bar chart.

Multiple series side-by-side within each category, like matplotlib's
"width-shifted" recipe or seaborn's `barplot(hue=...)`. Each call adds
one *group member* — the user passes which slot (0..n-1) and the total
number of slots so widths and offsets work out.

API:
    c.grouped_bar(cats, vals, slot=0, n_slots=3, label="A")
    c.grouped_bar(cats, vals, slot=1, n_slots=3, label="B")
    c.grouped_bar(cats, vals, slot=2, n_slots=3, label="C")

For typical use, the `grouped_bars` helper below covers it in one call.
"""

SUMMARY = 'Dodged side-by-side bars per category (seaborn `barplot(hue=)` analogue).'
from pathlib import Path

import plotlet as pt
from plotlet.draw import rect
from plotlet.utils import to_list
from plotlet._spec import _D


def grouped_bar_record(args, kw):
    return {"type": "grouped_bar",
            "cats": to_list(args[0]),
            "vals": to_list(args[1]),
            "opts": kw}


def grouped_bar_xdomain(a): return a["cats"]
def grouped_bar_ydomain(a): return list(a["vals"]) + [0]


def grouped_bar_draw(a, ctx):
    col = ctx.color
    slot = a["opts"].get("slot", 0)
    n_slots = a["opts"].get("n_slots", 1)
    group_pad = a["opts"].get("group_pad", 0.15)
    alpha = a["opts"].get("alpha", _D["bar_alpha"])
    band = getattr(ctx.x_scale, "bandwidth", 1.0)
    inner = band * (1 - group_pad)
    bar_w = inner / n_slots
    # Offset of the *left edge* of slot 0 from the band center.
    left_edge = -inner / 2
    y0 = ctx.y_scale(0)
    out = []
    for cat, v in zip(a["cats"], a["vals"]):
        cx = ctx.x_scale(cat)
        x0 = cx + left_edge + slot * bar_w
        y_top = ctx.y_scale(v)
        out.append(rect(x0, min(y0, y_top), bar_w, abs(y_top - y0),
                        fill=col, alpha=alpha))
    return "".join(out)


def grouped_bar_legend_entries(a):
    label = a["opts"].get("label")
    if not label:
        return []
    def paint(a, ctx, x0, y_mid):
        return rect(x0, y_mid - 5, 22, 10, fill=a["_color"])
    return [{"label": label, "color": a.get("_color"), "paint": paint}]


def grouped_bars(c, cats, series_vals, labels=None, colors=None, **opts):
    labels = labels or [f"series {i}" for i in range(len(series_vals))]
    n = len(series_vals)
    for i, vals in enumerate(series_vals):
        kw = {"slot": i, "n_slots": n, "label": labels[i], **opts}
        if colors:
            kw["color"] = colors[i]
        c.grouped_bar(cats, vals, **kw)
    return c


pt.add_artist(pt.ArtistSpec(
    name="grouped_bar",
    record=grouped_bar_record,
    xdomain=grouped_bar_xdomain,
    ydomain=grouped_bar_ydomain,
    draw=grouped_bar_draw,
    legend_entries=grouped_bar_legend_entries,
    force_zero_y=True,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    cats = ["A", "B", "C", "D"]
    a_vals = [4, 7, 5, 8]
    b_vals = [3, 5, 8, 6]
    c_vals = [5, 4, 6, 9]
    c = pt.chart()
    grouped_bars(c, cats, [a_vals, b_vals, c_vals],
                 labels=["before", "during", "after"])
    c.title("Group comparison").ylabel("score").legend(True)
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
