"""Custom artist: slope chart.

Two-column "before / after" comparison: each row is a paired observation
drawn as a single line connecting `(0, before)` and `(1, after)`, with a
dot at each endpoint and an optional label near the right endpoint.
Tufte's preferred chart for highlighting rank shuffles or per-item deltas.

API: c.slope_chart(labels, before_vals, after_vals,
                   left_label="before", right_label="after").
Each labeled series gets its own color via the normal cycle by calling
slope_chart per-row, but the common case is a single call with all rows
sharing a color — pass `color="gray"` for the "many faint lines, highlight
one" style and overlay a second call for the highlighted row.
"""

SUMMARY = 'Paired before / after lines with end-point dots and optional row labels.'
from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from plotlet.font import _text_path


def slope_record(args, kw):
    labels = _to_pylist(args[0])
    a = _to_pylist(args[1])
    b = _to_pylist(args[2])
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
            f'<line x1="{x0:.2f}" x2="{x1:.2f}" y1="{y0:.2f}" y2="{y1:.2f}" '
            f'stroke="{col}" stroke-width="{lw}" opacity="{alpha}"/>'
            f'<circle cx="{x0:.2f}" cy="{y0:.2f}" r="{r}" fill="{col}" opacity="{alpha}"/>'
            f'<circle cx="{x1:.2f}" cy="{y1:.2f}" r="{r}" fill="{col}" opacity="{alpha}"/>'
        )
        if show_labels:
            out.append(_text_path(f"{label}", x1 + 6, y1 + 3, 10, anchor="start"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="slope_chart",
    record=slope_record,
    xdomain=slope_xdomain,
    ydomain=slope_ydomain,
    draw=slope_draw,
))


if __name__ == "__main__":
    labels = ["alpha", "beta", "gamma", "delta", "epsilon"]
    before = [62, 71, 55, 80, 48]
    after  = [70, 65, 73, 78, 60]
    c = pt.chart()
    # Background lines in gray, highlight one in C0.
    c.slope_chart(labels, before, after, color="#999999", show_labels=True)
    c.slope_chart(["gamma"], [55], [73], color="C0", linewidth=2.4, show_labels=False)
    c.xticks([0, 1], ["before", "after"])
    c.title("Score before/after").ylabel("score")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
