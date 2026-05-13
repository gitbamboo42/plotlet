"""Custom artist: data-anchored text labels.

Add labels to specific data points — equivalent to a stripped-down
matplotlib `ax.annotate(..., xy=(...))` or `ax.text(...)`. Renders text
as paths via plotlet's bundled DejaVu Sans, so output stays font-
independent and reproducible.

API: c.text_label(xs, ys, labels, fontsize=11, anchor="middle",
                   dx=0, dy=-6).
- `dx`, `dy` — pixel offset from each (xs[i], ys[i]) point.
- `anchor`   — SVG text-anchor: "start" | "middle" | "end".
"""

SUMMARY = "Data-anchored text via plotlet's bundled DejaVu Sans, on the foreground layer."
from pathlib import Path

import plotlet as pt
from plotlet.artists import _to_pylist
from plotlet.font import _text_path


def text_label_record(args, kw):
    return {"type": "text_label",
            "xs": _to_pylist(args[0]),
            "ys": _to_pylist(args[1]),
            "labels": list(args[2]),
            "opts": kw}


def text_label_xdomain(a): return a["xs"]
def text_label_ydomain(a): return a["ys"]


def text_label_draw(a, ctx):
    opts = a["opts"]
    fontsize = opts.get("fontsize", 11)
    anchor = opts.get("anchor", "middle")
    dx = opts.get("dx", 0); dy = opts.get("dy", -6)
    col = opts.get("color") or "#222"
    out = []
    for x, y, label in zip(a["xs"], a["ys"], a["labels"]):
        if label is None or label == "":
            continue
        px = ctx.x_scale(x) + dx
        py = ctx.y_scale(y) + dy
        out.append(_text_path(str(label), px, py, fontsize, anchor=anchor, color=col))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="text_label",
    record=text_label_record,
    xdomain=text_label_xdomain,
    ydomain=text_label_ydomain,
    draw=text_label_draw,
    layer="foreground",
    uses_color_cycle=False,
))


if __name__ == "__main__":
    xs = [1, 2, 3, 4, 5]
    ys = [3, 7, 4, 9, 5]
    labels = ["A", "B", "C", "D", "E"]
    c = pt.chart()
    c.scatter(xs, ys)
    c.text_label(xs, ys, labels, dy=-10, fontsize=11)
    c.title("Scatter with point labels").xlabel("x").ylabel("y")
    out = Path(__file__).with_suffix(".svg")
    c.save_svg(out)
    print(f"wrote {out}")
