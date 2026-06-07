"""Custom artist: data-anchored text labels.

Add labels to specific data points — a stripped-down `text` variant
with a pixel-offset (`dx`, `dy`) from each anchor point. Renders text
as paths via plotlet's bundled DejaVu Sans, so output stays font-
independent and reproducible.

API: c.text_label(data=df, x="col", y="col", label="col",
                   fontsize=11, anchor="middle", dx=0, dy=-6).
- `dx`, `dy` — pixel offset from each (xs[i], ys[i]) point.
- `anchor`   — SVG text-anchor: "start" | "middle" | "end".
"""

SUMMARY = "Data-anchored text via plotlet's bundled DejaVu Sans, on the foreground layer."
from pathlib import Path

import plotlet as pt
from plotlet.utils import to_list
from plotlet.draw import text_path


def text_label_record(args, kw):
    kw = dict(kw)
    if args:
        raise TypeError(
            "text_label requires long-form input: "
            "c.text_label(data=df, x='col', y='col', label='col')."
        )
    data = kw.pop("data", None)
    x_col = kw.pop("x", None)
    y_col = kw.pop("y", None)
    label_col = kw.pop("label", None)
    if data is None or x_col is None or y_col is None or label_col is None:
        raise TypeError("text_label requires data=, x=, y=, label=.")
    return {"type": "text_label",
            "xs": to_list(data[x_col]),
            "ys": to_list(data[y_col]),
            "labels": [str(v) for v in to_list(data[label_col])],
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
        out.append(text_path(str(label), px, py, fontsize, anchor=anchor, color=col))
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


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    df = {"x": [1, 2, 3, 4, 5], "y": [3, 7, 4, 9, 5],
          "label": ["A", "B", "C", "D", "E"]}
    c = pt.chart()
    c.scatter(df, x="x", y="y")
    c.text_label(df, x="x", y="y", label="label", dy=-10, fontsize=11)
    c.title("Scatter with point labels").xlabel("x").ylabel("y")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
