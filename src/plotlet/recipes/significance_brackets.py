"""Custom artist: significance brackets (* p < .05) over a categorical plot.

The "[ ___|___ ]\\n*" brackets you see overlayed on boxplots / violins
in biology / clinical papers. Each comparison is a pair of categories
and an annotation; the bracket is drawn at the appropriate height
above the data, and the annotation text (typically "ns" or "*", "**",
"***") sits centered above the bracket.

Stacks neatly: each call adds one bracket layer above the previous, so
multiple `significance_brackets(...)` calls produce a tidy "ladder".

API:
    c.significance_brackets(comparisons, y_top=None, y_step=0.06,
                            offset=0.0)

`comparisons` is a list of `(cat_a, cat_b, annotation)` triples.
- `y_top`  — data y at which to draw the lowest bracket (defaults to
  just above the current ymax of the chart, but we can't introspect it
  cleanly from inside an artist; pass an explicit value if you care).
- `y_step` — vertical spacing between stacked brackets in *data* units.
- `offset` — vertical offset from y_top for this layer (set 1, 2, … to
  stack multiple `significance_brackets` calls).
"""

SUMMARY = "Significance brackets over a boxplot/violin: '*'/'**'/'ns' annotations with bracket lines."

from pathlib import Path

import plotlet as pt
from plotlet.draw import text_path


def sig_record(args, kw):
    comparisons = list(args[0])
    return {"type": "significance_brackets",
            "comparisons": comparisons, "opts": kw}


def sig_xdomain(a):
    # Cats from both sides of each comparison so axis stays valid.
    out = []
    for a_, b, _ in a["comparisons"]:
        out.append(a_); out.append(b)
    return out


def sig_ydomain(a):
    yt = a["opts"].get("y_top")
    step = a["opts"].get("y_step", 0.06)
    offset = a["opts"].get("offset", 0.0)
    if yt is None:
        return None
    n = len(a["comparisons"])
    return [yt + (offset + n) * step]


def sig_draw(a, ctx):
    y_top = a["opts"].get("y_top")
    step = a["opts"].get("y_step", 0.06)
    offset = a["opts"].get("offset", 0.0)
    if y_top is None:
        # Fall back: place near the top of the data area using the y range.
        # We need to read ylim somehow; the simplest robust path is to use
        # the y_scale's inverse for the top of the data area.
        # ctx.ih is the data-area height in px; the visual top is at SVG y=0
        # inside the panel, which maps to the y_data of the panel's ymax.
        # Without a direct ymax accessor we approximate using `y_top` defaults
        # of 0 (user is expected to pass an explicit y_top for tight plots).
        y_top = 0.0
    out = []
    for i, (cat_a, cat_b, text) in enumerate(a["comparisons"]):
        y_data = y_top + (offset + i) * step
        py = ctx.y_scale(y_data)
        px_a = ctx.x_scale(cat_a); px_b = ctx.x_scale(cat_b)
        x_lo = min(px_a, px_b); x_hi = max(px_a, px_b)
        drop = 4  # bracket tick length in px
        out.append(
            f'<path d="M{x_lo:.2f},{py + drop:.2f} L{x_lo:.2f},{py:.2f} '
            f'L{x_hi:.2f},{py:.2f} L{x_hi:.2f},{py + drop:.2f}" '
            f'fill="none" stroke="#222" stroke-width="0.8"/>'
        )
        out.append(text_path(text, (x_lo + x_hi) / 2, py - 4,
                              11, anchor="middle"))
    return "".join(out)


pt.add_artist(pt.ArtistSpec(
    name="significance_brackets",
    record=sig_record,
    xdomain=sig_xdomain,
    ydomain=sig_ydomain,
    draw=sig_draw,
    uses_color_cycle=False,
    layer="foreground",
))


def demo():
    """Build the demonstration chart with synthetic data.

    Returns a `pt.Chart` ready for `.save_svg()` or further composition."""
    # Stand-alone demo: synthetic per-group data + brackets above.
    import random
    random.seed(0)
    cats = ["control", "drug A", "drug B", "drug C"]
    groups = [
        [random.gauss(5, 1) for _ in range(40)],
        [random.gauss(6.5, 1.1) for _ in range(40)],
        [random.gauss(6.7, 1.0) for _ in range(40)],
        [random.gauss(8.2, 1.4) for _ in range(40)],
    ]
    # We'll need the boxplot recipe registered too; the demo just uses the
    # built-in bar(mean) for simplicity so this file runs standalone.
    means = [sum(g) / len(g) for g in groups]
    c = pt.chart(data_height=320)
    c.xscale("category", order=cats)
    c.bar(cats, means)
    # Brackets above bars: comparisons + annotations.
    c.significance_brackets(
        [("control", "drug A", "**"),
         ("control", "drug C", "***"),
         ("drug B",  "drug C", "*")],
        y_top=max(means) + 0.5,
        y_step=0.7,
    )
    c.title("Mean response with significance").ylabel("score")
    return c


if __name__ == "__main__":
    out = Path(__file__).with_suffix(".svg")
    demo().save_svg(out)
    print(f"wrote {out}")
