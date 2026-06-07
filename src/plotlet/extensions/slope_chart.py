"""Custom artist: slope chart.

Two-column "before / after" comparison: each row is a paired observation
drawn as a single line connecting `(0, before)` and `(1, after)`, with a
dot at each endpoint and an optional label near the right endpoint.
Tufte's preferred chart for highlighting rank shuffles or per-item deltas.

API: c.slope_chart(data=df, label="col", a="col", b="col",
                   left_label="before", right_label="after").
Each labeled series gets its own color via the normal cycle by calling
slope_chart per-row, but the common case is a single call with all rows
sharing a color — pass `color="gray"` for the "many faint lines, highlight
one" style and overlay a second call for the highlighted row.
"""

SUMMARY = 'Paired before / after lines with end-point dots and optional row labels.'
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path, segment, circle


def slope_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "slope_chart requires long-form input: "
            "c.slope_chart(data=df, label='col', a='col', b='col')."
        )
    data = kw.pop("data", None)
    label_col = kw.pop("label", None)
    a_col = kw.pop("a", None)
    b_col = kw.pop("b", None)
    if data is None or label_col is None or a_col is None or b_col is None:
        raise TypeError("slope_chart requires data=, label=, a=, b=.")
    labels = to_list(data[label_col])
    a = to_list(data[a_col])
    b = to_list(data[b_col])
    return {"type": "slope_chart", "labels": labels, "a": a, "b": b, "opts": kw}


def slope_xdomain(a):
    # Always two columns at x=0 and x=1, no matter the data.
    return [-0.1, 1.1]


def slope_ydomain(a):
    return list(a["a"]) + list(a["b"])


def slope_draw(a, ctx):
    col = ctx.color
    lw = a["opts"].get("linewidth", 1.4)
    alpha = a["opts"].get("alpha", 0.85)
    r = a["opts"].get("size", 3)
    show_labels = a["opts"].get("show_labels", True)
    out = []
    x0 = ctx.x_scale(0); x1 = ctx.x_scale(1)
    for label, av, bv in zip(a["labels"], a["a"], a["b"]):
        y0 = ctx.y_scale(av); y1 = ctx.y_scale(bv)
        out.append(
            segment(x0, y0, x1, y1, color=col, width=lw, alpha=alpha)
            + circle(x0, y0, r, fill=col, alpha=alpha)
            + circle(x1, y1, r, fill=col, alpha=alpha)
        )
        if show_labels:
            out.append(text_path(f"{label}", x1 + 6, y1 + 3, 10, anchor="start"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="slope_chart",
    record=slope_record,
    xdomain=slope_xdomain,
    ydomain=slope_ydomain,
    draw=slope_draw,
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    labels = ["alpha", "beta", "gamma", "delta", "epsilon"]
    before = [62, 71, 55, 80, 48]
    after  = [70, 65, 73, 78, 60]
    df = {"label": labels, "before": before, "after": after}
    c = pt.chart()
    # Background lines in gray, highlight one in C0.
    c.slope_chart(df, label="label", a="before", b="after",
                  color="#999999", show_labels=True)
    c.slope_chart({"label": ["gamma"], "before": [55], "after": [73]},
                  label="label", a="before", b="after",
                  color="C0", linewidth=2.4, show_labels=False)
    c.xticks([0, 1], ["before", "after"])
    c.title("Score before/after").ylabel("score")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
